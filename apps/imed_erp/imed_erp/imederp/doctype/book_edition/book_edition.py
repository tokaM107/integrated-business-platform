import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, now_datetime, today

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import check_active, get_amount_per_copy
from imed_erp.imederp.doctype.printer_reading.printer_reading import LIBRARIES
from imed_erp.imederp.doctype.printing_cost_settings.printing_cost_settings import get_rates

# The paper in a copy is costed at the moving average price paid for it, read from the library's raw
# materials store, plus the waste rate in Printing Cost Settings (owner's decision).
PAPER = "A4-PAPER"
LIBRARY_PAPER_STORE = {"مكتبة المواساة": "خامات المواساة", "مكتبة الأزاريطة": "خامات الأزاريطة"}

# No rounding (owner's decision of 8 Oct 2026, instead of DOC-28): the price is the calculated price, unless
# another one is set by hand. A higher price adds to the library's profit; a lower one, to sell more, comes
# out of it. The doctor's amount never changes.

# DOC-15, DOC-17: an edition is Active once approved; Carry Forward and Cancel: Curriculum Changed are the only
# ways its status changes, each recording when and by whom (carry_forward, cancel_for_curriculum_change below).
ACTIVE, CARRIED_FORWARD, CANCELLED = "Active", "Carried Forward", "Cancelled"
# Copies of these can still be sold (DOC-15: carried copies stay on sale).
SELLABLE = (ACTIVE, CARRIED_FORWARD)
# Set only by those two actions or by the edition's sales (imederp/edition_sales.py), never typed or sent
# through the API.
HISTORY_FIELDS = (
    "status",
    "sold_qty",
    "remaining_qty",
    "carried_to_period",
    "carried_forward_on",
    "carried_forward_by",
    "notice_date",
    "notice_received_by",
    "cancellation_recorded_on",
)
COUNTED_FIELDS = ("sold_qty", "remaining_qty")

# Rate on the edition <- rate in Printing Cost Settings, filled in when left empty.
DEFAULT_RATES = {
    "ink_cost": "ink_per_sheet",
    "overhead_cost": "overheads_per_sheet",
    "owner_share": "profit_per_sheet",
    "binding_cost": "binding_per_copy",
}


class BookEdition(Document):
    def validate(self):
        # Records are posted to one business; group cost centers cannot hold transactions.
        if frappe.db.get_value("Cost Center", self.cost_center, "is_group"):
            frappe.throw(_("Cost Center {0} is a group. Choose a branch under it.").format(self.cost_center))
        # Editions are printed and sold by the libraries only.
        abbr = frappe.get_cached_value("Company", frappe.db.get_value("Cost Center", self.cost_center, "company"), "abbr")
        if frappe.db.get_value("Cost Center", self.cost_center, "parent_cost_center") != f"{LIBRARIES} - {abbr}":
            frappe.throw(_("{0} is not a library. Editions are printed and sold by a library.").format(self.cost_center))
        self.validate_agreement()
        self.validate_item()
        self.set_quantities()
        if self.docstatus == 0:
            # A draft is not on sale yet: Active whatever was sent, with nothing sold.
            self.status = ACTIVE
        # DOC-25: the rates are taken while the edition is a draft and kept once it is submitted.
        if self.docstatus == 0:
            self.set_rates()
        self.set_price()

    def before_submit(self):
        if cint(self.total_qty) <= 0:
            frappe.throw(_("Enter the copies to print: Doctor Requested Qty, Library Extra Qty or both."), title=_("No Quantity"))
        if not flt(self.paper_cost):
            frappe.throw(_("A4 paper has no price yet in {0}; receive paper before approving the edition.").format(self.cost_center))

    def before_update_after_submit(self):
        # Status and its history change only through the edition's actions, which set this flag.
        if self.flags.edition_action:
            return
        before = self.get_doc_before_save()
        if not before:
            return
        # Worked out from the sales, which may have changed them since this copy was opened: kept as they are.
        for field in COUNTED_FIELDS:
            self.set(field, before.get(field))
        changed = [f for f in HISTORY_FIELDS if before.get(f) != self.get(f)]
        if changed:
            frappe.throw(
                _("{0} change only through Carry Forward or Cancel: Curriculum Changed.").format(
                    ", ".join(_(self.meta.get_label(f)) for f in changed)
                )
            )

    def validate_item(self):
        if not self.item_code:
            return
        item = frappe.db.get_value("Item", self.item_code, ["is_stock_item", "disabled"], as_dict=True)
        if not item or not item.is_stock_item or item.disabled:
            frappe.throw(
                _("Item {0} is not an active stock item; an edition is sold as a book or memo kept in stock.").format(self.item_code)
            )

    def set_quantities(self):
        # DOC-14: the doctor's copies and the library's extra copies are kept apart; the total is their sum.
        for field in ("doctor_qty", "extra_qty"):
            if cint(self.get(field)) < 0:
                frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(field))))
        if self.docstatus == 0:
            # Sold copies come only from submitted invoices, which name a submitted edition.
            self.sold_qty = 0
        self.total_qty = cint(self.doctor_qty) + cint(self.extra_qty)
        self.remaining_qty = self.total_qty - cint(self.sold_qty)

    def validate_agreement(self):
        # DOC-02: an edition belongs to a books agreement, not to an app one.
        if frappe.db.get_value("Doctor Agreement", self.agreement, "agreement_type") != "Books":
            frappe.throw(_("Agreement {0} is not a books agreement.").format(self.agreement))
        if self.docstatus != 0 and self._action != "submit":
            # A submitted edition keeps the amount it was priced with; submitting checks the agreement again
            # (it may have been suspended since the draft was saved) and takes its term once more.
            return
        check_active(self.agreement)
        # The doctor names his amount per copy (the agreement's term in force on the edition's date); the
        # library prices the rest on top of it. A later term does not change this edition.
        amount = get_amount_per_copy(self.agreement, self.edition_date)
        if amount is None:
            frappe.throw(
                _("Agreement {0} has no amount per copy in force on {1}. Add a term from that date or earlier.").format(
                    self.agreement, frappe.format_value(self.edition_date, {"fieldtype": "Date"})
                ),
                title=_("No Agreement Term"),
            )
        self.doctor_share = amount

    def set_rates(self):
        rates = get_rates()
        self.paper_cost = get_paper_cost(self.cost_center, rates.waste_per_sheet)
        for field, rate in DEFAULT_RATES.items():
            if self.get(field) is None:
                self.set(field, rates[rate])

    def set_price(self):
        # DOC-24: per copy, (paper + ink + overheads + profit) per sheet x sheets, plus binding, marketing
        # and the doctor's amount.
        per_sheet = flt(self.paper_cost) + flt(self.ink_cost) + flt(self.overhead_cost) + flt(self.owner_share)
        per_copy = flt(self.binding_cost) + flt(self.marketing_cost) + flt(self.doctor_share)
        previous = flt(self.calculated_price)
        self.calculated_price = flt(per_sheet * cint(self.pages) + per_copy, 2)
        # A price still equal to the last calculated one was not set by hand, so it follows the new
        # calculation (sheets, rates or the doctor's amount changed on the draft, or an amended copy).
        if not self.selling_price or flt(self.selling_price) == previous:
            self.selling_price = self.calculated_price
        self.rounding_diff = flt(self.selling_price) - self.calculated_price

        # Below cost the library loses on every copy: allowed, but said plainly.
        cost = flt(per_sheet - flt(self.owner_share)) * cint(self.pages) + per_copy - flt(self.marketing_cost)
        if flt(self.selling_price) < flt(cost, 2):
            frappe.msgprint(
                _("Final Selling Price {0} is below the cost of a copy, {1}: the library loses {2} on each copy sold.").format(
                    self.selling_price, flt(cost, 2), flt(cost - flt(self.selling_price), 2)
                ),
                title=_("Selling at a Loss"),
                indicator="orange",
            )


def get_copy_cost(edition):
	"""What a copy costs to make (DOC-18): (paper + ink + overheads) per sheet x sheets, plus binding. Without the
	library's profit, its marketing, the doctor's own amount or a price set by hand. `edition` is the edition's
	document or a dict of its fields."""
	per_sheet = flt(edition.get("paper_cost")) + flt(edition.get("ink_cost")) + flt(edition.get("overhead_cost"))
	return flt(per_sheet * cint(edition.get("pages")) + flt(edition.get("binding_cost")), 2)


def get_paper_cost(cost_center, waste_per_sheet=None):
    """Moving average price of a sheet of A4 paper in the library's store, plus waste.

    0 when the library has no paper price yet (nothing received).
    """
    if waste_per_sheet is None:
        waste_per_sheet = get_rates().waste_per_sheet
    company = frappe.db.get_value("Cost Center", cost_center, "company")
    abbr = frappe.get_cached_value("Company", company, "abbr")
    library = cost_center[: -len(f" - {abbr}")] if cost_center.endswith(f" - {abbr}") else cost_center
    store = LIBRARY_PAPER_STORE.get(library)
    rate = flt(frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": f"{store} - {abbr}"}, "valuation_rate")) if store else 0
    return flt(rate + flt(waste_per_sheet), 4) if rate else 0


def get_sold_qty(edition, exclude_invoice=None, for_update=False):
    """Copies of the edition sold: the submitted sales invoice rows that name it, in the item's stock unit. A
    credit note's rows are negative and take theirs back; a cancelled invoice counts for nothing. Worked out from
    the invoices every time, never added to, so a sale is never counted twice.

    for_update: a locking read. A plain read inside a transaction sees the database as it was at the
    transaction's first read (REPEATABLE READ), so a sale another user committed meanwhile would be missed."""
    exclude = "and si.name != %(invoice)s" if exclude_invoice else ""
    lock = "for update" if for_update else ""
    return flt(
        frappe.db.sql(
            f"""select sum(sii.stock_qty) from `tabSales Invoice Item` sii
            join `tabSales Invoice` si on si.name = sii.parent
            where sii.book_edition = %(edition)s and si.docstatus = 1 {exclude} {lock}""",
            {"edition": edition, "invoice": exclude_invoice},
        )[0][0]
    )


def update_sold_qty(edition):
    sold = cint(get_sold_qty(edition))
    total = cint(frappe.db.get_value("Book Edition", edition, "total_qty"))
    frappe.db.set_value("Book Edition", edition, {"sold_qty": sold, "remaining_qty": total - sold}, update_modified=False)


def edition_for_action(name):
    """The submitted edition, for someone allowed to change it: the write right on Book Edition, for their own
    library only (User Permission on its cost center)."""
    doc = frappe.get_doc("Book Edition", name)
    doc.check_permission("write")
    if doc.docstatus != 1:
        frappe.throw(_("Edition {0} is not approved (submitted) yet.").format(doc.name))
    update_sold_qty(doc.name)
    doc.reload()
    return doc


def save_action(doc):
    doc.flags.edition_action = True
    # The right was checked in edition_for_action. Saving a submitted edition otherwise asks for the submit right,
    # which approves pricing and which branch managers do not have.
    doc.flags.ignore_permissions = True
    doc.save()


@frappe.whitelist(methods=["POST"])
def carry_forward(edition, period):
    """DOC-15: the unsold copies go on to a later academic period at their original cost (the edition's approved
    costs are not touched) and stay on sale. DOC-16: they are sold at the price in force when sold, ERPNext's
    Item Price."""
    doc = edition_for_action(edition)
    if doc.status not in SELLABLE:
        frappe.throw(_("Edition {0} is cancelled; it is not carried forward.").format(doc.name))
    if cint(doc.remaining_qty) <= 0:
        frappe.throw(_("Every copy of edition {0} is sold; there is nothing to carry forward.").format(doc.name))

    target = frappe.db.get_value("Academic Period", period, ["start_date", "is_closed"], as_dict=True)
    if not target:
        frappe.throw(_("Academic Period {0} not found.").format(period))
    if target.is_closed:
        frappe.throw(_("Academic Period {0} is closed.").format(period))
    current = doc.carried_to_period or doc.period
    if current:
        if period == current:
            frappe.throw(_("Edition {0} is already in {1}.").format(doc.name, period))
        current_end = frappe.db.get_value("Academic Period", current, "end_date")
        if current_end and (not target.start_date or getdate(target.start_date) <= getdate(current_end)):
            frappe.throw(_("{0} does not start after {1} ends. Carry the edition forward to a later period.").format(period, current))

    doc.status = CARRIED_FORWARD
    doc.carried_to_period = period
    doc.carried_forward_on = now_datetime()
    doc.carried_forward_by = frappe.session.user
    save_action(doc)
    return doc.name


@frappe.whitelist(methods=["POST"])
def cancel_for_curriculum_change(edition, notice_date):
    """DOC-17: the doctor said, by word of mouth, that the curriculum changed. The edition is marked Cancelled with
    the day of the notice, the employee who received it (the one recording it, from the login, never a typed
    name) and when it was recorded. Nothing posted changes: its sales, stock and approved costs stay as they are;
    no more copies are sold (imederp/edition_sales.py). What the remaining copies cost the doctor or the library
    (DOC-18, approved under DOC-22) belongs to the doctors' accounts and is not posted here."""
    doc = edition_for_action(edition)
    if doc.status not in SELLABLE:
        frappe.throw(_("Edition {0} is already cancelled.").format(doc.name))
    if not notice_date:
        frappe.throw(_("Enter the day the doctor gave the notice."), title=_("Notice Date Required"))
    notice_date = getdate(notice_date)
    if notice_date > getdate(today()):
        frappe.throw(_("The notice date cannot be in the future."))
    if notice_date < getdate(doc.edition_date):
        frappe.throw(
            _("The notice date cannot be before the edition date, {0}.").format(
                frappe.format_value(doc.edition_date, {"fieldtype": "Date"})
            )
        )

    doc.status = CANCELLED
    doc.notice_date = notice_date
    doc.notice_received_by = frappe.session.user
    doc.cancellation_recorded_on = now_datetime()
    save_action(doc)
    return doc.name
