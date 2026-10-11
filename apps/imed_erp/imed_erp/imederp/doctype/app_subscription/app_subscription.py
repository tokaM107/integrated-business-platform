import frappe
from frappe import _
from frappe.model.document import Document


class AppSubscription(Document):
    # APP-04/05 (requirements v1.2): a student's subscription is the basis of the platform fee the group
    # earns from the doctor. The course itself is paid by the student to the doctor directly, so no course
    # money is recorded here.
    def validate(self):
        # Records are posted to one business; group cost centers cannot hold transactions.
        if frappe.db.get_value("Cost Center", self.cost_center, "is_group"):
            frappe.throw(f"Cost Center {self.cost_center} is a group. Choose a branch under it.")
        # DOC-02: a subscription belongs to an app agreement, not to a books one.
        if frappe.db.get_value("Doctor Agreement", self.agreement, "agreement_type") != "App":
            frappe.throw(_("Agreement {0} is not an app agreement.").format(self.agreement))
