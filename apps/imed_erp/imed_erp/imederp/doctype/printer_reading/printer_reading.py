import frappe
from frappe import _
from frappe.model.document import Document

# Printers are in the libraries only.
LIBRARIES = "مكتبات 2Be Doctor"


class PrinterReading(Document):
    def validate(self):
        # Records are posted to one business; group cost centers cannot hold transactions.
        if frappe.db.get_value("Cost Center", self.branch, "is_group"):
            frappe.throw(f"Cost Center {self.branch} is a group. Choose a branch under it.")
        abbr = frappe.get_cached_value("Company", frappe.db.get_value("Cost Center", self.branch, "company"), "abbr")
        if frappe.db.get_value("Cost Center", self.branch, "parent_cost_center") != f"{LIBRARIES} - {abbr}":
            frappe.throw(_("{0} is not a library. Printer readings are recorded for a library.").format(self.branch))
        self.consumed = (self.closing_reading or 0) - (self.opening_reading or 0)
        if self.consumed < 0:
            frappe.throw("Closing reading cannot be less than opening reading")
        self.variance = self.consumed - (self.sold_sheets or 0)

