import frappe
from frappe.model.document import Document


class BookEdition(Document):
    def validate(self):
        # Records are posted to one business; group cost centers cannot hold transactions.
        if frappe.db.get_value("Cost Center", self.cost_center, "is_group"):
            frappe.throw(f"Cost Center {self.cost_center} is a group. Choose a branch under it.")
        base = (self.unit_cost or 0) + (self.owner_share or 0) + (self.doctor_share or 0)
        self.calculated_price = base
        if not self.selling_price:
            self.selling_price = base
        self.rounding_diff = (self.selling_price or 0) - base

