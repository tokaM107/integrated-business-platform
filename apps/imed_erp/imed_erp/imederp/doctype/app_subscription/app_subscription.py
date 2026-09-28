import frappe
from frappe.model.document import Document


class AppSubscription(Document):
    def validate(self):
        # Records are posted to one business; group cost centers cannot hold transactions.
        if frappe.db.get_value("Cost Center", self.cost_center, "is_group"):
            frappe.throw(f"Cost Center {self.cost_center} is a group. Choose a branch under it.")
        self.course_amount = (self.total_paid or 0) - (self.platform_fee or 0)
        if self.course_amount < 0:
            frappe.throw("Platform fee cannot exceed total paid")

