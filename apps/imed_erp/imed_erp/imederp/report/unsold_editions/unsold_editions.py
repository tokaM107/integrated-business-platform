# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Old editions not fully sold (DOC-21), to review before each module: approved editions still on sale whose
# period (or the period they were carried to, DOC-15) ended before the date chosen, with copies left. The copies
# left are split between the doctor's (sales count against his first) and the library's extra ones (DOC-14), since
# the doctor's are charged to him when the period closes (DOC-18). get_list applies User Permissions, so a branch
# manager sees her own library's.

import frappe
from frappe import _
from frappe.utils import cint, getdate

from imed_erp.imederp.doctype.book_edition.book_edition import SELLABLE


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Edition"), "fieldname": "edition", "fieldtype": "Link", "options": "Book Edition", "width": 200},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Agreement"), "fieldname": "agreement", "fieldtype": "Link", "options": "Doctor Agreement", "width": 160},
		{"label": _("Library"), "fieldname": "library", "fieldtype": "Link", "options": "Cost Center", "width": 150},
		{"label": _("Period"), "fieldname": "period", "fieldtype": "Link", "options": "Academic Period", "width": 150},
		{"label": _("Period Ended"), "fieldname": "period_end", "fieldtype": "Date", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Total Qty"), "fieldname": "total_qty", "fieldtype": "Int", "width": 80},
		{"label": _("Sold Qty"), "fieldname": "sold_qty", "fieldtype": "Int", "width": 80},
		{"label": _("Remaining Qty"), "fieldname": "remaining_qty", "fieldtype": "Int", "width": 100},
		{"label": _("Doctor's Copies Left"), "fieldname": "doctor_left", "fieldtype": "Int", "width": 120},
		{"label": _("Library's Copies Left"), "fieldname": "library_left", "fieldtype": "Int", "width": 120},
	]


def get_data(filters):
	conditions = {"docstatus": 1, "status": ["in", SELLABLE], "remaining_qty": [">", 0]}
	if filters.library:
		conditions["cost_center"] = ["in", [filters.library, *frappe.db.get_descendants("Cost Center", filters.library)]]
	before = getdate(filters.before)
	rows = []
	for edition in frappe.get_list(
		"Book Edition",
		filters=conditions,
		fields=["name", "item_code", "agreement", "cost_center", "period", "carried_to_period", "status",
			"doctor_qty", "total_qty", "sold_qty", "remaining_qty"],
		order_by="edition_date",
	):
		period = edition.carried_to_period or edition.period
		end = frappe.db.get_value("Academic Period", period, "end_date")
		if not end or getdate(end) >= before:
			continue
		doctor_left = max(cint(edition.doctor_qty) - cint(edition.sold_qty), 0)
		rows.append(
			{
				"edition": edition.name,
				"item_code": edition.item_code,
				"agreement": edition.agreement,
				"library": edition.cost_center,
				"period": period,
				"period_end": end,
				"status": _(edition.status),
				"total_qty": edition.total_qty,
				"sold_qty": edition.sold_qty,
				"remaining_qty": edition.remaining_qty,
				"doctor_left": doctor_left,
				"library_left": cint(edition.remaining_qty) - doctor_left,
			}
		)
	return rows
