# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The BA+ platform fees (APP-07): the students of each course of each doctor in a term, the tier applied and
# the fee due from the doctor, as the course was last counted (APP-03). A doctor's courses follow each other,
# each with its own tier (the tier is counted per course: TIER_COUNTED_PER in app_course.py).

import frappe
from frappe import _
from frappe.utils import flt

from imed_erp.imederp.doctype.platform_fee_schedule.platform_fee_schedule import get_tier


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Doctor"), "fieldname": "doctor", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("App Agreement"), "fieldname": "agreement", "fieldtype": "Link", "options": "Doctor Agreement", "width": 160},
		{"label": _("Course Name"), "fieldname": "course_name", "fieldtype": "Data", "width": 180},
		{"label": _("Term"), "fieldname": "period", "fieldtype": "Link", "options": "Academic Period", "width": 150},
		{"label": _("Students"), "fieldname": "subscriptions", "fieldtype": "Int", "width": 90},
		{"label": _("Tier"), "fieldname": "tier", "fieldtype": "Data", "width": 110},
		{"label": _("Fee per Student"), "fieldname": "fee_per_student", "fieldtype": "Currency", "width": 120},
		{"label": _("Platform Fee"), "fieldname": "platform_fee_total", "fieldtype": "Currency", "width": 130},
	]


def get_data(filters):
	conditions = {}
	for field in ("period", "doctor", "agreement"):
		if filters.get(field):
			conditions[field] = filters.get(field)
	rows = []
	for course in frappe.get_list(
		"App Course",
		filters=conditions,
		fields=["name", "course_name", "doctor", "agreement", "period", "subscriptions", "fee_per_student", "platform_fee_total"],
		order_by="period desc, doctor, course_name",
	):
		start = frappe.db.get_value("Academic Period", course.period, "start_date")
		tier = get_tier(course.subscriptions, start)
		rows.append(
			{
				**course,
				"tier": tier_label(tier),
				"fee_per_student": flt(course.fee_per_student),
				"platform_fee_total": flt(course.platform_fee_total),
			}
		)
	return rows


def tier_label(tier):
	if not tier:
		return ""
	if not tier.to_students:
		return _("{0}+").format(tier.from_students)
	return f"{tier.from_students}–{tier.to_students}"
