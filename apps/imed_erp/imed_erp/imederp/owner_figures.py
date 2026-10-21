# The owner's money figures on the Owner Dashboard (owner's request of 21 Oct 2026: "the important financial
# accounts in front of the owner"), read from the ledger itself (GL Entry, cancelled entries left out), so they agree
# with ERPNext's own reports. Each is a "Custom" Number Card (setup/setup_dashboard.py).
#
#   cash in the cash boxes   every Cash and Bank account (the businesses' cash boxes, the main treasury, the wallets)
#   revenue, expenses, net   this calendar month, income and expense accounts
#   owed to us               the Receivable accounts: customers (deposits taken show as less owed), platform fees
#                            owed by doctors, doctors' debts on books
#   we owe                   everything under الذمم الدائنة: suppliers, staff, doctors (books), lecturers
#
# The company's figures as a whole: only the owner and the accountant read them (the same people the dashboard is
# for), whatever the caller sends.

import frappe
from frappe.utils import flt, get_first_day, get_last_day, today

READERS = ("Super Admin", "System Manager", "Accounts Manager", "Accountant")
PAYABLES_GROUP = "الذمم الدائنة"


# The group's company, by name, as in setup_coa.py: the site's default company is another one ("imed").
COMPANY = "Mohamed Mamdouh group"


def company():
	return COMPANY


def check_reader():
	if not set(READERS) & set(frappe.get_roles()):
		frappe.throw(
			frappe._("Only the owner and the accountant see the company's figures."), frappe.PermissionError
		)


def balance(accounts, sign=1, from_date=None, to_date=None):
	"""Debit minus credit of `accounts` (times `sign`), optionally between two dates."""
	if not accounts:
		return 0.0
	conditions, values = (
		["company = %(company)s", "is_cancelled = 0", "account in %(accounts)s"],
		{
			"company": company(),
			"accounts": tuple(accounts),
		},
	)
	if from_date:
		conditions.append("posting_date >= %(from_date)s")
		values["from_date"] = from_date
	if to_date:
		conditions.append("posting_date <= %(to_date)s")
		values["to_date"] = to_date
	value = frappe.db.sql(
		f"select coalesce(sum(debit - credit), 0) from `tabGL Entry` where {' and '.join(conditions)}", values
	)[0][0]
	return flt(sign * flt(value), 2)


def leaf_accounts(**filters):
	return frappe.get_all("Account", filters={"company": company(), "is_group": 0, **filters}, pluck="name")


def under(group):
	"""The leaf accounts under a group of the chart of accounts."""
	abbr = frappe.get_cached_value("Company", company(), "abbr")
	lft, rgt = frappe.db.get_value("Account", f"{group} - {abbr}", ["lft", "rgt"]) or (0, 0)
	return leaf_accounts(lft=[">", lft], rgt=["<", rgt]) if lft else []


def card(value):
	return {"value": flt(value, 2), "fieldtype": "Currency"}


def month():
	return get_first_day(today()), get_last_day(today())


def revenue_and_expenses():
	start, end = month()
	revenue = balance(leaf_accounts(root_type="Income"), -1, start, end)
	expenses = balance(leaf_accounts(root_type="Expense"), 1, start, end)
	return revenue, expenses


@frappe.whitelist()
def cash_in_boxes(filters=None):
	check_reader()
	return card(balance(leaf_accounts(account_type=["in", ["Cash", "Bank"]])))


@frappe.whitelist()
def revenue_this_month(filters=None):
	check_reader()
	return card(revenue_and_expenses()[0])


@frappe.whitelist()
def expenses_this_month(filters=None):
	check_reader()
	return card(revenue_and_expenses()[1])


@frappe.whitelist()
def net_this_month(filters=None):
	check_reader()
	revenue, expenses = revenue_and_expenses()
	return card(revenue - expenses)


@frappe.whitelist()
def owed_to_us(filters=None):
	check_reader()
	return card(balance(leaf_accounts(account_type="Receivable")))


@frappe.whitelist()
def we_owe(filters=None):
	check_reader()
	return card(balance(under(PAYABLES_GROUP), -1))


def cash_box_balances():
	"""(cash box, balance) for every Cash and Bank account, for the Cash Box Balances report."""
	return [(account, balance([account])) for account in leaf_accounts(account_type=["in", ["Cash", "Bank"]])]
