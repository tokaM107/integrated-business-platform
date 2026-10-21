# Helpers for the app's tests (not a test module itself).

import frappe

COMPANY = "Mohamed Mamdouh group"
# The first day of the company's fiscal year (2026-2027): opening money is put in from then.
FIRST_DAY = "2026-09-01"


def fund_cash_boxes(amount=1000000, date=FIRST_DAY, company=COMPANY):
	"""Opening cash in every cash box of the company, against the owner's capital, as on a real opening day: a cash
	box never goes below zero (cash_balance.py), so a test that pays out of a box puts the money in first. Rolled
	back with the test that calls it."""
	boxes = frappe.get_all("Account", filters={"company": company, "account_type": "Cash", "is_group": 0, "disabled": 0}, pluck="name")
	capital = frappe.get_all("Account", filters={"company": company, "root_type": "Equity", "is_group": 0}, pluck="name", limit=1)[0]
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"company": company,
			"posting_date": date,
			"user_remark": "_Test opening cash",
			"accounts": [{"account": box, "debit_in_account_currency": amount, "cost_center": cost_center} for box in boxes]
			+ [{"account": capital, "credit_in_account_currency": amount * len(boxes), "cost_center": cost_center}],
		}
	)
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	return entry.name
