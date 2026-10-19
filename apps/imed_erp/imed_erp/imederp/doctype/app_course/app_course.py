# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


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
