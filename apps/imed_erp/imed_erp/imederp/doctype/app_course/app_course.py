# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from imed_erp.imederp.doctype.platform_fee_schedule.platform_fee_schedule import get_fee_per_student


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


def recalculate_course(course):
	"""APP-03: count the course's submitted subscriptions, take the tier for that count and charge every
	subscription the tier's fee. The tier is counted per course, not across the doctor's courses (owner's
	answer to question 31). Nothing changes once the term is closed."""
	period = frappe.db.get_value("App Course", course, "period")
	term = frappe.db.get_value("Academic Period", period, ["start_date", "is_closed"], as_dict=True)
	if term.is_closed:
		return
	# A student who withdraws still counts: assumed until the owner decides (docs/known-issues.md).
	students = frappe.db.count("App Subscription", {"course": course, "docstatus": 1})
	fee = flt(get_fee_per_student(students, term.start_date))
	# Not a change by the user: a course or a subscription open on someone's screen can still be saved.
	frappe.db.set_value(
		"App Course",
		course,
		{"subscriptions": students, "fee_per_student": fee, "platform_fee_total": fee * students},
		update_modified=False,
	)
	frappe.db.set_value(
		"App Subscription", {"course": course, "docstatus": 1}, "platform_fee", fee, update_modified=False
	)
	if students and not fee:
		frappe.msgprint(
			_("No platform fee tiers are in force on {0}, so course {1} is charged nothing yet.").format(
				frappe.format_value(term.start_date, {"fieldtype": "Date"}), course
			),
			indicator="orange",
			alert=True,
		)


def on_subscription_change(doc, method=None):
	# hooks.py: App Subscription on_submit and on_cancel.
	recalculate_course(doc.course)
