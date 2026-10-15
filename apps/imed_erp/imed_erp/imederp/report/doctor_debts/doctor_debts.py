# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Doctor debts (RPT-10, APP-08): what doctors owe the group on To Date, with how old it is.
#
#   Books agreements whose balance is below zero (DOC-20): the doctor was charged or paid more than his copies
#   earned. A standing debt, kept until settled, not an error.
#   App agreements: the platform fees of the students' subscriptions not collected yet (APP-05/08).
#
# Read from the doctor's ledger and, for the platform fees, which the ledger does not hold, from the submitted App
# Subscriptions (imederp/doctor_balances.py). Nothing is posted here.
#
# Age: what pays a debt settles its oldest part first (age_debt), so each part still owed keeps the date it arose:
# the subscription's date for a fee, the entry's date for a charge. Ranges in days, 30, 60, 90 unless set.

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from imed_erp.imederp.doctor_balances import (
	age_debt,
	ageing_buckets,
	app_fees_in_ledger,
	check_permission,
	get_agreements,
	get_entries,
	get_subscription_fees,
	parse_ranges,
)

NEGATIVE_BALANCE, PLATFORM_FEES = "Negative Balance", "Uncollected Platform Fees"


def execute(filters=None):
	check_permission()
	filters = frappe._dict(filters or {})
	filters.to_date = getdate(filters.to_date or today())
	ranges = parse_ranges(filters.range)
	data = get_data(filters, ranges)
	return get_columns(ranges), data, None, None, get_summary(data)


def get_columns(ranges):
	currency = {"fieldtype": "Currency", "width": 115}
	columns = [
		{"label": _("Doctor"), "fieldname": "doctor", "fieldtype": "Link", "options": "Customer", "width": 170},
		{"label": _("Agreement"), "fieldname": "agreement", "fieldtype": "Link", "options": "Doctor Agreement", "width": 170},
		{"label": _("Agreement Type"), "fieldname": "agreement_type", "fieldtype": "Data", "width": 90},
		{"label": _("Debt"), "fieldname": "debt_type", "fieldtype": "Data", "width": 170},
		{"label": _("Owed"), "fieldname": "raised", **currency},
		{"label": _("Collected or Offset"), "fieldname": "paid", **currency},
		{"label": _("Outstanding Debt"), "fieldname": "outstanding", **currency},
		{"label": _("Oldest Debt Date"), "fieldname": "oldest", "fieldtype": "Date", "width": 110},
	]
	lower = 0
	for i, limit in enumerate(ranges):
		columns.append({"label": f"{lower}-{limit}", "fieldname": f"range{i + 1}", **currency})
		lower = limit + 1
	columns.append({"label": f"{lower}+", "fieldname": f"range{len(ranges) + 1}", **currency})
	columns.append({"label": _("Last Settlement"), "fieldname": "last_settlement_date", "fieldtype": "Date", "width": 110})
	return columns


def get_data(filters, ranges):
	agreements = {a.name: a for a in get_agreements(filters)}
	entries = get_entries(list(agreements), to_date=filters.to_date)
	app_agreements = [name for name, a in agreements.items() if a.agreement_type == "App"]
	fees = get_subscription_fees(app_agreements, to_date=filters.to_date)
	fees_in_ledger = app_fees_in_ledger(app_agreements)

	movements = {}
	for entry in entries:
		agreement = agreements[entry.agreement]
		# In debt terms: books entries count against the doctor when they lower what he is owed; app entries
		# (owed by the doctor) as they are.
		amount = -entry.signed if agreement.agreement_type == "Books" else entry.signed
		movements.setdefault(entry.agreement, []).append((entry.entry_date, amount))
	for name, rows in fees.items():
		if name not in fees_in_ledger:
			movements.setdefault(name, []).extend((date, fee) for date, fee, _branch, _sub in rows)

	data = []
	for name, rows in movements.items():
		agreement = agreements[name]
		open_debts = age_debt(rows)
		outstanding = flt(sum(amount for _date, amount in open_debts), 2)
		if outstanding <= 0:
			continue
		raised = flt(sum(amount for _date, amount in rows if amount > 0), 2)
		buckets = ageing_buckets(open_debts, filters.to_date, ranges)
		data.append(
			{
				"doctor": agreement.doctor,
				"agreement": name,
				"agreement_type": _(agreement.agreement_type),
				"debt_type": _(NEGATIVE_BALANCE if agreement.agreement_type == "Books" else PLATFORM_FEES),
				"raised": raised,
				"paid": flt(raised - outstanding, 2),
				"outstanding": outstanding,
				"oldest": min(date for date, _amount in open_debts),
				"last_settlement_date": agreement.last_settlement_date,
				**{f"range{i + 1}": flt(amount, 2) for i, amount in enumerate(buckets)},
			}
		)
	return sorted(data, key=lambda row: (row["oldest"], row["agreement"]))


def get_summary(data):
	return [
		{"label": _("Doctors"), "value": len({row["doctor"] for row in data}), "datatype": "Int"},
		{
			"label": _(NEGATIVE_BALANCE),
			"value": sum(row["outstanding"] for row in data if row["debt_type"] == _(NEGATIVE_BALANCE)),
			"datatype": "Currency",
			"indicator": "red",
		},
		{
			"label": _(PLATFORM_FEES),
			"value": sum(row["outstanding"] for row in data if row["debt_type"] == _(PLATFORM_FEES)),
			"datatype": "Currency",
			"indicator": "blue",
		},
	]
