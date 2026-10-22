# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# What students paid BA Plus (App Payment), by how and where: the cash a branch took, which its daily close counts,
# and the electronic payments with their reference numbers, to match against the bank's and wallets' statements.
# Matched means ERPNext's Bank Clearance gave the payment's entry its clearance date. Each doctor's total is what is
# held for him. Only the payments the user may read (a branch manager: her branch's).

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columns(), data(filters)


def columns():
	return [
		{"label": _("Payment"), "fieldname": "name", "fieldtype": "Link", "options": "App Payment", "width": 140},
		{"label": _("Payment Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Student"), "fieldname": "student", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Course"), "fieldname": "course", "fieldtype": "Link", "options": "App Course", "width": 150},
		{"label": _("Doctor"), "fieldname": "doctor", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": _("Collecting Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Cost Center", "width": 150},
		{"label": _("Payment Method"), "fieldname": "payment_method", "fieldtype": "Data", "width": 110},
		{"label": _("Paid Into"), "fieldname": "treasury", "fieldtype": "Link", "options": "Account", "width": 170},
		{"label": _("Reference No"), "fieldname": "reference_no", "fieldtype": "Data", "width": 120},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 110},
		{"label": _("Matched On"), "fieldname": "clearance_date", "fieldtype": "Date", "width": 100},
		{"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 80},
		{"label": _("Journal Entry"), "fieldname": "journal_entry", "fieldtype": "Link", "options": "Journal Entry", "width": 140},
	]


def data(filters):
	conditions = {"docstatus": 1, "posting_date": ("between", (filters.from_date, filters.to_date))}
	for field in ("treasury", "branch", "doctor"):
		if filters.get(field):
			conditions[field] = filters.get(field)
	if filters.kind == "Cash":
		conditions["payment_method"] = "Cash"
	elif filters.kind == "Electronic":
		conditions["payment_method"] = ("!=", "Cash")
	rows = frappe.get_list(
		"App Payment",
		filters=conditions,
		fields=["name", "posting_date", "student", "course", "doctor", "branch", "payment_method", "treasury", "reference_no", "amount", "source", "journal_entry"],
		order_by="posting_date, name",
		limit_page_length=0,
	)
	cleared = dict(
		frappe.get_all(
			"Journal Entry", filters={"name": ("in", [r.journal_entry for r in rows] or [""])}, fields=["name", "clearance_date"], as_list=True
		)
	)
	out = []
	for row in rows:
		row.clearance_date = cleared.get(row.journal_entry) if row.payment_method != "Cash" else None
		if filters.not_cleared and (row.payment_method == "Cash" or row.clearance_date):
			continue
		row.payment_method = _(row.payment_method)
		row.source = _(row.source)
		row.amount = flt(row.amount, 2)
		out.append(row)
	return out
