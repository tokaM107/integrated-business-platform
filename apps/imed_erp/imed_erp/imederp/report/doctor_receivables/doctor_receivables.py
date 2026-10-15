# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Doctor receivables (RPT-08): what the group still owes each doctor on his books agreements, by doctor,
# agreement and library. Read from the doctor's ledger (imederp/doctor_balances.py), the same entries the
# agreement's balance is made of; nothing is posted here.
#
# For each agreement, over the period: the balance at its start (Opening), what the copies sold accrued, the
# adjustments, the charges for unsold copies, what was paid out, and the balance at its end (Outstanding). An
# agreement shows while it owes the doctor something; a books balance below zero is the doctor's debt and is in
# Doctor Debts (RPT-10). Under each agreement, a row per library its entries belong to; a payout made for the
# agreement as a whole belongs to none ("Not by branch"), so only the agreement's own row is its balance.

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from imed_erp.imederp.doctor_balances import check_permission, get_agreements, get_entries

# Ledger kind -> column. Adjustments keep their own sign.
COLUMN_OF = {"Accrual": "accrued", "Adjustment": "adjustments", "Unsold Copies Charge": "charges", "Payout": "paid", "Collection": "paid"}
AMOUNTS = ("opening", "accrued", "adjustments", "charges", "paid", "outstanding")


def execute(filters=None):
	check_permission()
	filters = frappe._dict(filters or {})
	filters.to_date = getdate(filters.to_date or today())
	if filters.from_date and getdate(filters.from_date) > filters.to_date:
		frappe.throw(_("From Date is after To Date."))
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	currency = {"fieldtype": "Currency", "width": 120}
	return [
		{"label": _("Doctor"), "fieldname": "doctor", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("Agreement"), "fieldname": "agreement", "fieldtype": "Link", "options": "Doctor Agreement", "width": 180},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Cost Center", "width": 170},
		{"label": _("Opening"), "fieldname": "opening", **currency},
		{"label": _("Accrued"), "fieldname": "accrued", **currency},
		{"label": _("Adjustments"), "fieldname": "adjustments", **currency},
		{"label": _("Unsold Copies Charges"), "fieldname": "charges", **currency},
		{"label": _("Paid"), "fieldname": "paid", **currency},
		{"label": _("Outstanding"), "fieldname": "outstanding", **currency},
		{"label": _("Last Settlement"), "fieldname": "last_settlement_date", "fieldtype": "Date", "width": 110},
		{"label": _("Entries"), "fieldname": "entries", "fieldtype": "Int", "width": 80},
	]


def get_data(filters):
	agreements = {a.name: a for a in get_agreements(filters, agreement_type="Books")}
	entries = get_entries(list(agreements), to_date=filters.to_date)
	from_date = getdate(filters.from_date) if filters.from_date else None

	totals, by_branch = {}, {}
	for entry in entries:
		if filters.branch and entry.branch != filters.branch:
			continue
		for target in (
			totals.setdefault(entry.agreement, new_row()),
			by_branch.setdefault(entry.agreement, {}).setdefault(entry.branch, new_row()),
		):
			if from_date and getdate(entry.entry_date) < from_date:
				target.opening += entry.signed
			else:
				# Shown as they move the balance: charges and payments as amounts taken off it. A kind of entry
				# added later counts with its own sign among the adjustments, so the outstanding stays right.
				column = COLUMN_OF.get(entry.entry_type, "adjustments")
				target[column] += entry.signed if column in ("adjustments", "accrued") else -entry.signed
				target.entries += 1
			target.outstanding += entry.signed

	data = []
	for name, total in totals.items():
		if flt(total.outstanding, 2) <= 0 and not filters.show_settled:
			continue
		agreement = agreements[name]
		data.append(
			{
				**total,
				"doctor": agreement.doctor,
				"agreement": name,
				"branch": filters.branch,
				"last_settlement_date": agreement.last_settlement_date,
				"indent": 0,
			}
		)
		if filters.branch:
			continue
		# The libraries first, then what belongs to none (the JS shows it as "Not by branch").
		for branch, row in sorted(by_branch[name].items(), key=lambda item: item[0] or "~"):
			data.append({**row, "doctor": agreement.doctor, "agreement": name, "branch": branch, "indent": 1})
	for row in data:
		for field in AMOUNTS:
			row[field] = flt(row[field], 2)
	return data


def new_row():
	return frappe._dict({field: 0.0 for field in AMOUNTS} | {"entries": 0})


def get_summary(data):
	agreements = [row for row in data if row["indent"] == 0]
	owed = sum(row["outstanding"] for row in agreements if row["outstanding"] > 0)
	return [
		{"label": _("Agreements"), "value": len(agreements), "datatype": "Int"},
		{"label": _("Doctors"), "value": len({row["doctor"] for row in agreements}), "datatype": "Int"},
		{"label": _("Owed to Doctors"), "value": owed, "datatype": "Currency", "indicator": "orange"},
	]
