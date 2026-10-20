# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Each treasury's balance (ACC-03, first half: the balance of every cash box and wallet as the books show it): what
# it held when the day began, what came in and went out that day, and what it holds at the day's end, from the
# general ledger. A branch manager sees their own business's cash box and the group's wallets (treasuries.py); the
# owner and the accountant see every treasury.
#
# The daily close itself (counting the cash and comparing it with this balance, ACC-03's second half) waits for the
# accountant's decision on how it is made and who approves it (docs/known-issues.md, Phase 2 #2).

import frappe
from frappe import _
from frappe.utils import flt, today

from imed_erp.imederp.treasuries import ANY_TREASURY_ROLE, user_treasuries


def execute(filters=None):
	filters = frappe._dict(filters or {})
	date = filters.date or today()
	return get_columns(), get_data(date)


def get_columns():
	return [
		{"label": _("Treasury"), "fieldname": "treasury", "fieldtype": "Link", "options": "Account", "width": 240},
		{"label": _("Opening Balance"), "fieldname": "opening", "fieldtype": "Currency", "width": 140},
		{"label": _("Money In"), "fieldname": "money_in", "fieldtype": "Currency", "width": 130},
		{"label": _("Money Out"), "fieldname": "money_out", "fieldtype": "Currency", "width": 130},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 140},
	]


def treasuries():
	company = frappe.defaults.get_global_default("company")
	every = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "account_type": ("in", ("Cash", "Bank")), "disabled": 0},
		pluck="name",
		order_by="name",
	)
	if ANY_TREASURY_ROLE in frappe.get_roles() or "System Manager" in frappe.get_roles():
		return every
	allowed = user_treasuries()
	return [name for name in every if name in allowed]


def get_data(date):
	names = treasuries()
	if not names:
		return []
	moves = {
		row.account: row
		for row in frappe.db.sql(
			"""select account,
				sum(case when posting_date < %(date)s then debit - credit else 0 end) as opening,
				sum(case when posting_date = %(date)s then debit else 0 end) as money_in,
				sum(case when posting_date = %(date)s then credit else 0 end) as money_out
			from `tabGL Entry`
			where is_cancelled = 0 and account in %(names)s and posting_date <= %(date)s
			group by account""",
			{"date": date, "names": names},
			as_dict=True,
		)
	}
	rows = []
	for name in names:
		row = moves.get(name) or frappe._dict(opening=0, money_in=0, money_out=0)
		opening, money_in, money_out = flt(row.opening, 2), flt(row.money_in, 2), flt(row.money_out, 2)
		rows.append(
			{
				"treasury": name,
				"opening": opening,
				"money_in": money_in,
				"money_out": money_out,
				"balance": flt(opening + money_in - money_out, 2),
			}
		)
	return rows
