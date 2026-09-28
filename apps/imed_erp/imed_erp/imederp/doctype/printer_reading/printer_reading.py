import frappe
from frappe.model.document import Document


class PrinterReading(Document):
    def validate(self):
        # Records are posted to one business; group cost centers cannot hold transactions.
        if frappe.db.get_value("Cost Center", self.branch, "is_group"):
            frappe.throw(f"Cost Center {self.branch} is a group. Choose a branch under it.")
        self.consumed = (self.closing_reading or 0) - (self.opening_reading or 0)
        if self.consumed < 0:
            frappe.throw("Closing reading cannot be less than opening reading")
        self.variance = self.consumed - (self.sold_sheets or 0)

