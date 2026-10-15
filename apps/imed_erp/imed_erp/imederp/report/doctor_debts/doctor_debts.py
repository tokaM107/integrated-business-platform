# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# What the doctors owe the group (DOC-20, APP-05): a books agreement whose balance went below zero (charged more
# than he earned) and an app agreement's platform fees not collected yet, each with how long it has been owed.
# Worked out from the doctor's ledger up to the date chosen. A debt is never closed on its own: it stays until
# what comes next pays it off, oldest part first (the next amount the doctor earns goes to it before anything
# is paid to him, see Doctor Ledger Entry validate_payout), so its age is that of its oldest unpaid part.

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import open_amounts

BUCKETS = ((30, "0-30"), (60, "31-60"), (90, "61-90"), (None, "90+"))


def execute(filters=None):
	filters = frappe._dict(filters or {})
	as_of = getdate(filters.as_of)
	return get_columns(), get_data(filters, as_of)


def get_columns():
	columns = [
		{"label": _("Doctor"), "fieldname": "doctor", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("Agreement"), "fieldname": "agreement", "fieldtype": "Link", "options": "Doctor Agreement", "width": 180},
		{"label": _("Type"), "fieldname": "agreement_type", "fieldtype": "Data", "width": 80},
		{"label": _("Debt"), "fieldname": "debt", "fieldtype": "Currency", "width": 120},
		{"label": _("Owed Since"), "fieldname": "since", "fieldtype": "Date", "width": 110},
		{"label": _("Age (Days)"), "fieldname": "age", "fieldtype": "Int", "width": 90},
	]
	columns += [{"label": label, "fieldname": f"age_{label}", "fieldtype": "Currency", "width": 100} for _limit, label in BUCKETS]
	return columns


def get_data(filters, as_of):
	conditions = {"docstatus": 1}
	if filters.doctor:
		conditions["doctor"] = filters.doctor
	rows = []
	for agreement in frappe.get_all(
		"Doctor Agreement", filters=conditions, fields=["name", "doctor", "agreement_type"], order_by="doctor, name"
	):
		layers = [(part.date, part.amount) for part in open_amounts(agreement.name, as_of, owed_by_doctor=True)]
		debt = flt(sum(amount for _date, amount in layers), 2)
		if debt <= 0:
			continue
		row = {
			"doctor": agreement.doctor,
			"agreement": agreement.name,
			"agreement_type": _(agreement.agreement_type),
			"debt": debt,
			"since": layers[0][0],
			"age": date_diff(as_of, layers[0][0]),
		}
		for date, amount in layers:
			label = bucket(date_diff(as_of, date))
			row[f"age_{label}"] = flt(row.get(f"age_{label}")) + amount
		rows.append(row)
	return rows


def bucket(days):
	return next(label for limit, label in BUCKETS if limit is None or days <= limit)
