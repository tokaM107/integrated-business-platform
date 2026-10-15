# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# What the group owes the doctors and has not paid yet (DOC-10, RPT-08), by doctor, agreement, academic period and
# the branch that sold the copies, as of a date. From the doctor's ledger: what he earned less what was paid out or
# charged, the payouts settling the oldest dues first (Doctor Agreement open_amounts). A doctor who owes the group
# is on Doctor Debts instead.

import frappe
from frappe import _
from frappe.utils import getdate

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import open_amounts
from imed_erp.imederp.doctype.doctor_ledger_entry.doctor_ledger_entry import descendants


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters, getdate(filters.as_of))


def get_columns():
	return [
		{"label": _("Doctor"), "fieldname": "doctor", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("Agreement"), "fieldname": "agreement", "fieldtype": "Link", "options": "Doctor Agreement", "width": 180},
		{"label": _("Period"), "fieldname": "period", "fieldtype": "Link", "options": "Academic Period", "width": 160},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Cost Center", "width": 160},
		{"label": _("Owed to the Doctor"), "fieldname": "owed", "fieldtype": "Currency", "width": 140},
		{"label": _("Owed Since"), "fieldname": "since", "fieldtype": "Date", "width": 110},
	]


def get_data(filters, as_of):
	conditions = {"docstatus": 1}
	if filters.doctor:
		conditions["doctor"] = filters.doctor
	periods = {filters.period, *descendants(filters.period)} if filters.period else None
	branches = {filters.branch, *frappe.db.get_descendants("Cost Center", filters.branch)} if filters.branch else None
	rows = []
	for agreement in frappe.get_all("Doctor Agreement", filters=conditions, fields=["name", "doctor"], order_by="doctor, name"):
		grouped = {}
		for part in open_amounts(agreement.name, as_of):
			if periods is not None and part.period not in periods:
				continue
			if branches is not None and part.branch not in branches:
				continue
			row = grouped.setdefault(
				(part.period, part.branch),
				{"doctor": agreement.doctor, "agreement": agreement.name, "period": part.period, "branch": part.branch,
					"owed": 0, "since": part.date},
			)
			row["owed"] += part.amount
			row["since"] = min(row["since"], part.date)
		rows += sorted(grouped.values(), key=lambda row: row["since"])
	return rows
