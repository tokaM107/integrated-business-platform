# Opening cash on a new site (ACC-03; production initialization, docs/production-hardening.md).
#
# A cash box never goes below zero (cash_balance.py), so on the first day each box must already hold the cash that is
# really in it, or the first expense or payout out of it is refused. The cash is counted in each branch on the
# go-live morning, the counts signed, and the accountant enters them as one opening journal entry against
# حقوق ملكية الأرصدة الافتتاحية.
#
# Run from bench console:
#   from imed_erp.imederp import opening_cash
#   opening_cash.check()                                  # read-only: every treasury, its business and balance
#   opening_cash.prepare({"خزينة مكتبة الأزاريطة - MMG": 1500, ...}, "2026-10-28")
#                                                         # a DRAFT entry, for the accountant to check and submit
#
# prepare() writes a draft only, refuses a box that already has ledger entries (its opening would count twice), a
# wallet or any account that is not a cash box, and an amount below zero. The first close of each box then starts
# from this balance (Treasury Close: the ledger's balance before the day, for a box's first close).

import frappe
from frappe import _
from frappe.utils import flt, today

from imed_erp.imederp.treasuries import BUSINESS_TREASURY, WALLETS

COMPANY = "Mohamed Mamdouh group"
OPENING_EQUITY = "حقوق ملكية الأرصدة الافتتاحية"


def abbr(company=COMPANY):
	return frappe.get_cached_value("Company", company, "abbr")


def treasuries(company=COMPANY):
	"""Every cash box and wallet of the company: its type, the business it belongs to, its entries and balance, and
	what is wrong with it for the daily close."""
	suffix = abbr(company)
	business_of = {f"{box} - {suffix}": f"{business} - {suffix}" for business, box in BUSINESS_TREASURY.items()}
	wallets = {f"{w} - {suffix}" for w in WALLETS}
	rows = []
	for account in frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "account_type": ("in", ("Cash", "Bank"))},
		fields=["name", "account_type", "disabled"],
		order_by="account_type desc, name asc",
	):
		entries, balance = frappe.db.sql(
			"select count(*), sum(debit - credit) from `tabGL Entry` where account = %s and is_cancelled = 0", account.name
		)[0]
		problems = []
		business = business_of.get(account.name)
		if account.account_type == "Cash" and not business:
			problems.append(_("no business: nobody closes it"))
		if business and account.account_type != "Cash":
			problems.append(_("a business's treasury, but not a cash box: no daily close, no check below zero"))
		if account.name not in business_of and account.name not in wallets and account.account_type == "Bank":
			problems.append(_("not a known wallet"))
		if account.disabled:
			problems.append(_("disabled"))
		if flt(balance) < 0:
			problems.append(_("below zero"))
		rows.append(
			frappe._dict(
				treasury=account.name, type=account.account_type, business=business, entries=entries,
				balance=flt(balance, 2), problems=problems,
			)
		)
	return rows


def check(company=COMPANY):
	"""Print treasuries(); read-only."""
	for row in treasuries(company):
		print(
			f"{row.type:5} {row.treasury}  business: {row.business or '-'}  entries: {row.entries}  balance: {row.balance}"
			+ (f"  !! {'; '.join(row.problems)}" if row.problems else "")
		)


def prepare(amounts, posting_date=None, company=COMPANY):
	"""A draft opening journal entry putting the counted cash in each box; its name. Submitting it is the
	accountant's, after checking it against the signed counts."""
	suffix = abbr(company)
	lines, total = [], 0
	for box, amount in amounts.items():
		amount = flt(amount, 2)
		account = frappe.db.get_value("Account", box, ["company", "account_type", "is_group"], as_dict=True)
		if not account or account.company != company or account.is_group or account.account_type != "Cash":
			frappe.throw(_("{0} is not a cash box of {1}.").format(box, company))
		if amount < 0:
			frappe.throw(_("The cash counted in {0} cannot be below zero.").format(box))
		if frappe.db.exists("GL Entry", {"account": box, "is_cancelled": 0}):
			frappe.throw(_("{0} already has entries: its opening would count twice.").format(box))
		if amount:
			business = next(
				(f"{b} - {suffix}" for b, cash in BUSINESS_TREASURY.items() if f"{cash} - {suffix}" == box), None
			) or frappe.get_cached_value("Company", company, "cost_center")
			lines.append({"account": box, "debit_in_account_currency": amount, "cost_center": business})
			total += amount
	if not lines:
		frappe.throw(_("No cash to enter."))
	lines.append(
		{
			"account": f"{OPENING_EQUITY} - {suffix}",
			"credit_in_account_currency": flt(total, 2),
			"cost_center": frappe.get_cached_value("Company", company, "cost_center"),
		}
	)
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Opening Entry",
			"is_opening": "Yes",
			"company": company,
			"posting_date": posting_date or today(),
			"user_remark": _("Opening cash, counted in each branch"),
			"accounts": lines,
		}
	).insert()
	return entry.name
