import frappe
from frappe.model.document import Document


class AppSubscription(Document):
    def validate(self):
        self.course_amount = (self.total_paid or 0) - (self.platform_fee or 0)
        if self.course_amount < 0:
            frappe.throw("Platform fee cannot exceed total paid")

