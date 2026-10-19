import frappe
from frappe import _
from frappe.model.document import Document

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import check_active


class AppSubscription(Document):
    # APP-04/05 (requirements v1.2): a student's subscription is the basis of the platform fee the group
    # earns from the doctor. The course itself is paid by the student to the doctor directly, so no course
    # money is recorded here.
    def validate(self):
        # APP-01/04: the agreement, the doctor and the term are the course's, whatever an import or an old draft says.
        if not self.course:
            frappe.throw(_("Choose the student's course."))
        course = frappe.db.get_value("App Course", self.course, ["agreement", "doctor", "period", "status"], as_dict=True)
        self.agreement, self.doctor, self.period = course.agreement, course.doctor, course.period
        if self.docstatus == 0 and course.status != "Active":
            frappe.throw(_("Course {0} is closed. It takes no new subscriptions.").format(self.course))
        # A student counts once in a course: twice would raise the count, maybe to another tier, and charge
        # the doctor for him twice (APP-03). A draft may wait beside it; only one is submitted. Cancel the old
        # subscription to subscribe him again.
        twin = frappe.db.exists(
            "App Subscription", {"student": self.student, "course": self.course, "docstatus": 1, "name": ("!=", self.name)}
        )
        if twin:
            frappe.throw(_("{0} is already subscribed to course {1}: {2}.").format(self.student, self.course, twin))
        # Records are posted to one business; group cost centers cannot hold transactions.
        if frappe.db.get_value("Cost Center", self.cost_center, "is_group"):
            frappe.throw(_("Cost Center {0} is a group. Choose a branch under it.").format(self.cost_center))
        # DOC-02: a subscription belongs to an app agreement, not to a books one.
        if frappe.db.get_value("Doctor Agreement", self.agreement, "agreement_type") != "App":
            frappe.throw(_("Agreement {0} is not an app agreement.").format(self.agreement))
        if self.docstatus == 0:
            check_active(self.agreement)

    def before_update_after_submit(self):
        # The fee is worked out for the course (APP-03), not typed: a form opened before the course was
        # counted again still carries the old one, and saving it (ticking Withdrew) must not undo the count.
        self.platform_fee = frappe.db.get_value("App Subscription", self.name, "platform_fee")
