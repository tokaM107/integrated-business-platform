import frappe
from frappe import _
from frappe.model.document import Document

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import check_active


class AppSubscription(Document):
    # APP-04/05 (requirements v1.2): a student's subscription is the basis of the platform fee the group
    # earns from the doctor. The course itself is paid by the student to the doctor directly, so no course
    # money is recorded here.
    def validate(self):
        # Records are posted to one business; group cost centers cannot hold transactions.
        if frappe.db.get_value("Cost Center", self.cost_center, "is_group"):
            frappe.throw(_("Cost Center {0} is a group. Choose a branch under it.").format(self.cost_center))
        # DOC-02: a subscription belongs to an app agreement, not to a books one.
        if frappe.db.get_value("Doctor Agreement", self.agreement, "agreement_type") != "App":
            frappe.throw(_("Agreement {0} is not an app agreement.").format(self.agreement))
        if self.docstatus == 0:
            check_active(self.agreement)
