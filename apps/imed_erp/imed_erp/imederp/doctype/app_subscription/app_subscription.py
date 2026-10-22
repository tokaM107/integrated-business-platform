import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import check_active
from imed_erp.imederp.import_source import check_source
from imed_erp.imederp.platform_fee_posting import app_cost_center

# Worked out by the system, never typed, so an imported subscription keeps them as the ERP set them.
OWN_FIELDS = ("doctor", "agreement", "period", "platform_fee", "cost_center", "amended_from")


class AppSubscription(Document):
    # APP-04/05 (requirements v1.2): a student's subscription is the basis of the platform fee the group
    # earns from the doctor. No course money is recorded here: since 22 Oct 2026 a student may pay BA Plus, in cash
    # at a branch or electronically, and each payment is an App Payment, held for the doctor (app_payment.py).
    def validate(self):
        check_source(self, OWN_FIELDS)
        self.set_cost_center()
        # APP-01/04: the agreement, the doctor and the term are the course's, whatever an import or an old draft says.
        if not self.course:
            frappe.throw(_("Choose the student's course."))
        course = frappe.db.get_value("App Course", self.course, ["agreement", "doctor", "period", "status"], as_dict=True)
        self.agreement, self.doctor, self.period = course.agreement, course.doctor, course.period
        # QA-07: checked on submit too (validate runs on save and submit only; on submit docstatus is already 1),
        # so a draft saved while the course was open is not submitted, and charged, after it closed.
        if course.status != "Active":
            frappe.throw(_("Course {0} is closed. It takes no new subscriptions.").format(self.course))
        self.check_date_in_term()
        # A student counts once in a course: twice would raise the count, maybe to another tier, and charge
        # the doctor for him twice (APP-03). A draft may wait beside it; only one is submitted. Cancel the old
        # subscription to subscribe him again.
        twin = frappe.db.exists(
            "App Subscription", {"student": self.student, "course": self.course, "docstatus": 1, "name": ("!=", self.name)}
        )
        if twin:
            frappe.throw(_("{0} is already subscribed to course {1}: {2}.").format(self.student, self.course, twin))
        # DOC-02: a subscription belongs to an app agreement, not to a books one.
        if frappe.db.get_value("Doctor Agreement", self.agreement, "agreement_type") != "App":
            frappe.throw(_("Agreement {0} is not an app agreement.").format(self.agreement))
        check_active(self.agreement)

    def set_cost_center(self):
        # QA-16, INT-05: a subscription is BA Plus's, whoever subscribed the student or whatever a file said: the
        # platform fee is posted on the app's cost center (platform_fee_posting.py).
        self.cost_center = app_cost_center(frappe.db.get_value("Cost Center", self.cost_center, "company") if self.cost_center else None)
        if not frappe.db.exists("Cost Center", {"name": self.cost_center, "is_group": 0}):
            frappe.throw(_("The app's cost center {0} is missing. Run setup_core.py.").format(self.cost_center))

    def check_date_in_term(self):
        # QA-17: the fee is posted on the subscription's term; a date outside it would put it in another month.
        term = frappe.db.get_value("Academic Period", self.period, ["start_date", "end_date"], as_dict=True)
        if term and self.subscription_date and not (getdate(term.start_date) <= getdate(self.subscription_date) <= getdate(term.end_date)):
            frappe.throw(
                _("The subscription date must be in the course's term {0}: from {1} to {2}.").format(
                    self.period,
                    frappe.format_value(term.start_date, {"fieldtype": "Date"}),
                    frappe.format_value(term.end_date, {"fieldtype": "Date"}),
                ),
                title=_("Date Outside the Term"),
            )

    def before_update_after_submit(self):
        # The fee is worked out for the course (APP-03), not typed: a form opened before the course was
        # counted again still carries the old one, and saving it (ticking Withdrew) must not undo the count.
        self.platform_fee = frappe.db.get_value("App Subscription", self.name, "platform_fee")
        # INT-01: an imported student withdraws in BA Plus, not here.
        check_source(self, OWN_FIELDS)
