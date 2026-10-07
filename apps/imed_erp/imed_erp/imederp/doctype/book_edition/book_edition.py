import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

# The paper in a copy is costed at the moving average price paid for it, plus a fixed allowance for waste
# (owner's decision of 7 Oct 2026). It is read from the library's raw materials store.
PAPER = "A4-PAPER"
PAPER_WASTE_PER_SHEET = 0.04
LIBRARY_PAPER_STORE = {"مكتبة المواساة": "خامات المواساة", "مكتبة الأزاريطة": "خامات الأزاريطة"}

# DOC-28: the selling price is rounded up to a round amount and the difference goes to the owner.
# Rounding up keeps the difference positive, so it never comes out of the owner's or the doctor's share.
ROUND_TO = 5


class BookEdition(Document):
    def validate(self):
        # Records are posted to one business; group cost centers cannot hold transactions.
        if frappe.db.get_value("Cost Center", self.cost_center, "is_group"):
            frappe.throw(f"Cost Center {self.cost_center} is a group. Choose a branch under it.")
        self.validate_agreement()
        # DOC-25: the costs are taken while the edition is a draft and fixed once it is submitted.
        if self.docstatus == 0:
            self.paper_cost = get_paper_cost(self.cost_center)
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
        if agreement and agreement.share_type == "Fixed" and not self.doctor_share:
            self.doctor_share = agreement.share_value

    def set_price(self):
        # DOC-24: sale price per copy = (paper + other manufacturing cost + owner share) per sheet x sheets
        # + doctor share.
        per_sheet = flt(self.paper_cost) + flt(self.unit_cost) + flt(self.owner_share)
        self.calculated_price = flt(per_sheet * cint(self.pages) + flt(self.doctor_share), 2)
        if not self.selling_price:
            self.selling_price = math.ceil(self.calculated_price / ROUND_TO) * ROUND_TO
        if flt(self.selling_price) < self.calculated_price:
            frappe.throw(
                _("Final Selling Price {0} is below the calculated price {1}; the difference would come out of the shares.").format(
                    self.selling_price, self.calculated_price
                )
            )
        self.rounding_diff = flt(self.selling_price) - self.calculated_price


def get_paper_cost(cost_center):
    """Moving average price of a sheet of A4 paper in the library's store, plus the waste allowance.

    0 when the library has no paper price yet (nothing received).
    """
    company = frappe.db.get_value("Cost Center", cost_center, "company")
    abbr = frappe.get_cached_value("Company", company, "abbr")
    library = cost_center[: -len(f" - {abbr}")] if cost_center.endswith(f" - {abbr}") else cost_center
    store = LIBRARY_PAPER_STORE.get(library)
    rate = flt(frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": f"{store} - {abbr}"}, "valuation_rate")) if store else 0
    return flt(rate + PAPER_WASTE_PER_SHEET, 4) if rate else 0
