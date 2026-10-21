# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Shortages and surpluses found at the daily closes (owner, 21 Oct 2026), by branch, cash box and day, with their
# status and who was found responsible; Still Open Only lists those waiting for the accountant. A branch manager
# sees her own branch's (the discrepancy's permissions).
#
# Payroll Review: one row per employee and approved recovery, for the accountant to take to payroll by hand. The
# accountant and the owner only. It lists what was approved after an investigation, the employee told and the
# recovery checked against the contract and the law; the system deducts nothing from a salary.

import frappe
from frappe import _
from frappe.utils import flt

from imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy import ACCOUNTS_ROLES, OPEN


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if filters.view == "Payroll Review":
		frappe.only_for(ACCOUNTS_ROLES)
		return payroll_columns(), payroll_rows(filters)
	return columns(), rows(filters)


def where(filters):
	conditions = {"close_date": ("between", (filters.from_date, filters.to_date))}
	if filters.business:
		conditions["business"] = filters.business
	return conditions


def columns():
	return [
		{"label": _("Date"), "fieldname": "close_date", "fieldtype": "Date", "width": 100},
		{"label": _("Business"), "fieldname": "business", "fieldtype": "Link", "options": "Cost Center", "width": 160},
		{"label": _("Cash Box"), "fieldname": "treasury", "fieldtype": "Link", "options": "Account", "width": 200},
		{"label": _("Shift"), "fieldname": "shift", "fieldtype": "Data", "width": 90},
		{"label": _("Shortage"), "fieldname": "shortage", "fieldtype": "Currency", "width": 110},
		{"label": _("Surplus"), "fieldname": "surplus", "fieldtype": "Currency", "width": 110},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 160},
		{"label": _("Responsible"), "fieldname": "responsible", "fieldtype": "Data", "width": 200},
		{"label": _("Recovery Approved"), "fieldname": "recovery_total", "fieldtype": "Currency", "width": 130},
		{"label": _("Cash Discrepancy"), "fieldname": "name", "fieldtype": "Link", "options": "Cash Discrepancy", "width": 140},
		{"label": _("Treasury Close"), "fieldname": "treasury_close", "fieldtype": "Link", "options": "Treasury Close", "width": 140},
	]


def rows(filters):
	conditions = where(filters)
	conditions["status"] = ("in", OPEN) if filters.unresolved else ("!=", "Withdrawn")
	data = []
	for d in frappe.get_list(
		"Cash Discrepancy",
		filters=conditions,
		fields=["name", "close_date", "business", "treasury", "shift", "kind", "amount", "status", "recovery_total", "treasury_close"],
		order_by="close_date asc, business asc",
	):
		responsible = frappe.get_all(
			"Cash Discrepancy Employee", filters={"parent": d.name, "parenttype": "Cash Discrepancy", "responsible": 1}, pluck="user"
		)
		data.append(
			{
				**d,
				"shortage": flt(d.amount) if d.kind == "Shortage" else 0,
				"surplus": flt(d.amount) if d.kind == "Surplus" else 0,
				"status": _(d.status),
				"responsible": ", ".join(responsible),
			}
		)
	return data


def payroll_columns():
	return [
		{"label": _("Employee"), "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 200},
		{"label": _("Recovery Amount"), "fieldname": "recovery_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Date"), "fieldname": "close_date", "fieldtype": "Date", "width": 100},
		{"label": _("Business"), "fieldname": "business", "fieldtype": "Link", "options": "Cost Center", "width": 160},
		{"label": _("Shortage"), "fieldname": "amount", "fieldtype": "Currency", "width": 110},
		{"label": _("Told On"), "fieldname": "notified_on", "fieldtype": "Date", "width": 100},
		{"label": _("Approved By"), "fieldname": "approved_by", "fieldtype": "Link", "options": "User", "width": 160},
		{"label": _("Approved On"), "fieldname": "approved_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Cash Discrepancy"), "fieldname": "name", "fieldtype": "Link", "options": "Cash Discrepancy", "width": 140},
	]


def payroll_rows(filters):
	conditions = where(filters)
	conditions["status"] = "Recovery Approved"
	conditions["payroll_status"] = "Ready for Payroll Review"
	data = []
	for d in frappe.get_all(
		"Cash Discrepancy",
		filters=conditions,
		fields=["name", "close_date", "business", "amount", "approved_by", "approved_on"],
		order_by="close_date asc",
	):
		for row in frappe.get_all(
			"Cash Discrepancy Employee",
			filters={"parent": d.name, "parenttype": "Cash Discrepancy", "responsible": 1, "recovery_amount": (">", 0)},
			fields=["user", "recovery_amount", "notified_on"],
			order_by="idx asc",
		):
			data.append({**d, **row})
	return data
