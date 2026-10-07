import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

# DOC-28: the selling price is rounded up to a round amount and the difference goes to the owner.
# Rounding up keeps the difference positive, so it never comes out of the owner's or the doctor's share.
ROUND_TO = 5


class BookEdition(Document):
    def validate(self):
        # Records are posted to one business; group cost centers cannot hold transactions.
        if frappe.db.get_value("Cost Center", self.cost_center, "is_group"):
            frappe.throw(f"Cost Center {self.cost_center} is a group. Choose a branch under it.")
        self.validate_agreement()
        self.set_price()

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
        # DOC-24: sale price per copy = (manufacturing cost + owner share) per sheet x sheets + doctor share.
        self.calculated_price = flt(
            (flt(self.unit_cost) + flt(self.owner_share)) * cint(self.pages) + flt(self.doctor_share), 2
        )
        if not self.selling_price:
            self.selling_price = math.ceil(self.calculated_price / ROUND_TO) * ROUND_TO
        if flt(self.selling_price) < self.calculated_price:
            frappe.throw(
                _("Final Selling Price {0} is below the calculated price {1}; the difference would come out of the shares.").format(
                    self.selling_price, self.calculated_price
                )
            )
        self.rounding_diff = flt(self.selling_price) - self.calculated_price
