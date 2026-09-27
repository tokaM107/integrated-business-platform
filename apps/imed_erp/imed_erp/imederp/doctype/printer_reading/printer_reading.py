import frappe
from frappe.model.document import Document


class PrinterReading(Document):
    def validate(self):
        self.consumed = (self.closing_reading or 0) - (self.opening_reading or 0)
        if self.consumed < 0:
            frappe.throw("Closing reading cannot be less than opening reading")
        self.variance = self.consumed - (self.sold_sheets or 0)

