import frappe
from frappe.model.document import Document


class BookEdition(Document):
    def validate(self):
        base = (self.unit_cost or 0) + (self.owner_share or 0) + (self.doctor_share or 0)
        self.calculated_price = base
        if not self.selling_price:
            self.selling_price = base
        self.rounding_diff = (self.selling_price or 0) - base

