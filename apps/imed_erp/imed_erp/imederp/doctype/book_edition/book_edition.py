import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from imed_erp.imederp.doctype.printing_cost_settings.printing_cost_settings import get_rates

# The paper in a copy is costed at the moving average price paid for it, read from the library's raw
# materials store, plus the waste rate in Printing Cost Settings (owner's decision).
PAPER = "A4-PAPER"
LIBRARY_PAPER_STORE = {"مكتبة المواساة": "خامات المواساة", "مكتبة الأزاريطة": "خامات الأزاريطة"}

# No rounding (owner's decision of 8 Oct 2026, instead of DOC-28): the price is the calculated price, unless
# a higher one is set by hand, and the difference goes to the library.

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
            frappe.throw(f"Cost Center {self.cost_center} is a group. Choose a branch under it.")
        self.validate_agreement()
        # DOC-25: the rates are taken while the edition is a draft and kept once it is submitted.
        if self.docstatus == 0:
            self.set_rates()
        self.set_price()

    def before_submit(self):
        if not flt(self.paper_cost):
            frappe.throw(_("A4 paper has no price yet in {0}; receive paper before approving the edition.").format(self.cost_center))

    def validate_agreement(self):
        # DOC-02: an edition belongs to a books agreement, not to an app one.
        agreement = frappe.db.get_value(
            "Doctor Agreement", self.agreement, ["agreement_type", "share_type", "share_value"], as_dict=True
        )
        if agreement and agreement.agreement_type != "Books":
            frappe.throw(_("Agreement {0} is not a books agreement.").format(self.agreement))
        # The doctor names his amount per copy; the library prices the rest on top of it.
        if agreement and agreement.share_type == "Fixed" and not self.doctor_share:
            self.doctor_share = agreement.share_value

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
        self.calculated_price = flt(per_sheet * cint(self.pages) + per_copy, 2)
        if not self.selling_price:
            self.selling_price = self.calculated_price
        if flt(self.selling_price) < self.calculated_price:
            frappe.throw(
                _("Final Selling Price {0} is below the calculated price {1}; the difference would come out of the shares.").format(
                    self.selling_price, self.calculated_price
                )
            )
        self.rounding_diff = flt(self.selling_price) - self.calculated_price


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
