# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class PlatformFeeSchedule(Document):
	# APP-02 (requirements v1.2): the platform fee tiers by the number of students in a course in a term, as
	# data the owner keeps, with the date each set of tiers is in force from. Submitted, it stays as it was:
	# courses were charged by it. New prices are a new schedule from a later date.
	def before_insert(self):
		# Before it is named after its date, or a second schedule for that date fails on the name.
		self.check_one_per_date()

	def validate(self):
		self.check_one_per_date()
		self.check_tiers()

	def check_one_per_date(self):
		twin = frappe.db.exists(
			"Platform Fee Schedule", {"valid_from": self.valid_from, "docstatus": ("<", 2), "name": ("!=", self.name)}
		)
		if twin:
			frappe.throw(_("Tiers from {0} already exist: {1}. Amend that one instead.").format(self.valid_from, twin))

	def check_tiers(self):
		# From 1 student up, each tier starting right after the one before, and only the last one open-ended,
		# so every count falls in exactly one tier.
		self.tiers = sorted(self.tiers, key=lambda tier: cint(tier.from_students))
		expected_from = 1
		for idx, tier in enumerate(self.tiers, start=1):
			tier.idx = idx
			if cint(tier.from_students) != expected_from:
				frappe.throw(
					_("Row #{0}: the tier should start from {1} students, right after the one before.").format(idx, expected_from)
				)
			if flt(tier.fee_per_student) <= 0:
				frappe.throw(_("Row #{0}: the fee per student must be more than zero.").format(idx))
			if not tier.to_students:
				if idx != len(self.tiers):
					frappe.throw(_("Row #{0}: only the last tier can have no upper limit.").format(idx))
				return
			if cint(tier.to_students) < cint(tier.from_students):
				frappe.throw(_("Row #{0}: To is less than From.").format(idx))
			expected_from = cint(tier.to_students) + 1
		frappe.throw(_("Leave To empty on the last tier, so a course with more students still has a fee."))

	def on_submit(self):
		recalculate_open_courses()

	def on_cancel(self):
		recalculate_open_courses()


def recalculate_open_courses():
	"""New or withdrawn tiers change the fee of the courses whose term is still open."""
	from imed_erp.imederp.doctype.app_course.app_course import recalculate_course

	for course in frappe.get_all("App Course", filters={"period": ("in", open_terms())}, pluck="name"):
		recalculate_course(course)


def open_terms():
	return frappe.get_all("Academic Period", filters={"period_type": "Term", "is_closed": 0}, pluck="name") or [""]


def get_fee_per_student(students, date):
	"""The fee for one student of a course with `students` students, by the tiers in force on `date`: the
	latest submitted schedule from on or before it. None when no schedule is in force yet."""
	schedule = frappe.get_all(
		"Platform Fee Schedule",
		filters={"docstatus": 1, "valid_from": ("<=", date)},
		order_by="valid_from desc",
		limit=1,
		pluck="name",
	)
	if not schedule or cint(students) < 1:
		return None
	for tier in frappe.get_all(
		"Platform Fee Tier",
		filters={"parent": schedule[0], "parenttype": "Platform Fee Schedule"},
		fields=["from_students", "to_students", "fee_per_student"],
		order_by="from_students",
	):
		if cint(students) >= tier.from_students and (not tier.to_students or cint(students) <= tier.to_students):
			return flt(tier.fee_per_student)
	return None
