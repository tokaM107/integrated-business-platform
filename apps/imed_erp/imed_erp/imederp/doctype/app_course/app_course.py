# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from imed_erp.imederp.doctype.platform_fee_schedule.platform_fee_schedule import get_fee_per_student

# ---------------------------------------------------------------------------------------------------------
# The owner's answers on counting students for the platform fee tier (requirements v1.2 §4.10). Change them
# here, and only here, when the owner answers or changes his mind; open terms are counted again with the next
# subscription (or run recalculate_open_courses() from platform_fee_schedule.py at once).
#
# Question 31: which students choose the tier?
#   "course": each course's own students (80 + 80 in two courses: 250 each, 40,000).
#   "doctor": all the doctor's courses in the term together, i.e. the same agreement and term (160: 200
#             each, 32,000). Every course of the doctor then takes the same fee per student.
# Answered by the owner on 18 Oct 2026: per course.
TIER_COUNTED_PER = "course"
#
# A student who withdraws after the term starts (the "Withdrew" box on the submitted subscription):
#   True:  still counted and still charged.
#   False: left out of the count, and the doctor is charged nothing for him.
# Not answered yet (docs/known-issues.md): assumed True.
COUNT_WITHDRAWN = True
# ---------------------------------------------------------------------------------------------------------


class AppCourse(Document):
	# APP-01 (requirements v1.2): a course on the BA+ app, of one doctor's app agreement, in one term. Its
	# students' subscriptions (App Subscription) are what the platform fee tier is counted on.
	def validate(self):
		# DOC-02: a course belongs to an app agreement, not to a books one.
		if frappe.db.get_value("Doctor Agreement", self.agreement, "agreement_type") != "App":
			frappe.throw(_("Agreement {0} is not an app agreement.").format(self.agreement))
		if frappe.db.get_value("Academic Period", self.period, "period_type") != "Term":
			frappe.throw(_("{0} is not a term. A course runs in a term.").format(self.period))
		# The same course twice in a term would split its students, and so its tier, in two.
		twin = frappe.db.exists(
			"App Course",
			{"course_name": self.course_name, "agreement": self.agreement, "period": self.period, "name": ("!=", self.name)},
		)
		if twin:
			frappe.throw(
				_("Course {0} already exists for this agreement in {1}: {2}.").format(self.course_name, self.period, twin)
			)
		# Its subscriptions took the agreement and the term from it, and were charged for them.
		if not self.is_new() and self.subscriptions and (
			self.has_value_changed("agreement") or self.has_value_changed("period")
		):
			frappe.throw(_("Course {0} has subscriptions. Its agreement and term cannot change.").format(self.course_name))


def recalculate_course(course, date=None):
	"""APP-03: count the students, take the tier for that count and charge every counted subscription the
	tier's fee, by TIER_COUNTED_PER and COUNT_WITHDRAWN above, and post the change to the doctor's account
	(APP-05). Nothing changes once the term is closed."""
	agreement, period = frappe.db.get_value("App Course", course, ["agreement", "period"])
	term = frappe.db.get_value("Academic Period", period, ["start_date", "is_closed"], as_dict=True)
	if term.is_closed:
		return
	courses = (
		frappe.get_all("App Course", filters={"agreement": agreement, "period": period}, pluck="name")
		if TIER_COUNTED_PER == "doctor"
		else [course]
	)
	counted = {"course": ("in", courses), "docstatus": 1}
	if not COUNT_WITHDRAWN:
		counted["withdrawn"] = 0
	fee = flt(get_fee_per_student(frappe.db.count("App Subscription", counted), term.start_date))

	# Not a change by the user: a course or a subscription open on someone's screen can still be saved.
	for name in courses:
		students = frappe.db.count("App Subscription", {**counted, "course": name})
		frappe.db.set_value(
			"App Course",
			name,
			{"subscriptions": students, "fee_per_student": fee, "platform_fee_total": fee * students},
			update_modified=False,
		)
	frappe.db.set_value("App Subscription", counted, "platform_fee", fee, update_modified=False)
	if not COUNT_WITHDRAWN:
		frappe.db.set_value(
			"App Subscription",
			{"course": ("in", courses), "docstatus": 1, "withdrawn": 1},
			"platform_fee",
			0,
			update_modified=False,
		)
	# APP-05: the doctor's account follows, on the date of the subscription that changed the count.
	from imed_erp.imederp.platform_fee_posting import post_fee_change

	for name in courses:
		post_fee_change(name, date)
	if not fee and frappe.db.count("App Subscription", counted):
		frappe.msgprint(
			_("No platform fee tiers are in force on {0}, so course {1} is charged nothing yet.").format(
				frappe.format_value(term.start_date, {"fieldtype": "Date"}), course
			),
			indicator="orange",
			alert=True,
		)


def on_subscription_change(doc, method=None):
	# hooks.py: App Subscription on_submit, on_cancel and on_update_after_submit (the Withdrew box).
	recalculate_course(doc.course, doc.subscription_date)
