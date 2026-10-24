# A cash box never goes below zero (owner, 21 Oct 2026: under normal operations a cash box cannot hold less than
# nothing). Whatever takes money out of one, an expense, a transfer, a payout to a doctor, a cash refund or any other
# payment, is refused when the box does not hold it.
#
# Checked once the document has posted its ledger lines (hooks.py: on_submit and on_cancel of the documents that post
# to the ledger), so every way of paying is covered by one check: the app's documents post through a Journal Entry
# or a Payment Entry. The box's account is locked first and its ledger read with a locking read, which sees what
# other sessions have committed: two payments at once from the same box wait for each other, or the second is
# refused by the database; neither can spend the same money twice.
#
# The box must not go below zero on any day from the document's date to today, so a payment dated back cannot leave
# an earlier day short. Cancelling money that came in (a cash sale cancelled) is checked the same way.
#
# Only cash boxes (account type Cash). The wallets are bank accounts, reconciled with their statements (ACC-10).

import frappe
from frappe import _
from frappe.utils import flt, getdate

CASH = "Cash"


def check_on_submit(doc, method=None):
	check(doc, taking_out=lambda moved: moved < 0)


def remember_before_cancel(doc, method=None):
	# Once cancelled, the document's lines and their reversals add up to nothing: what it moved is read before.
	doc.flags.cash_moved = moved_by(doc)


def check_on_cancel(doc, method=None):
	# What the document brought in has just been reversed.
	check(doc, taking_out=lambda moved: moved > 0, movements=doc.flags.cash_moved)


def check(doc, taking_out, movements=None):
	for account, moved, first_date in movements if movements is not None else moved_by(doc):
		if not taking_out(moved) or frappe.db.get_value("Account", account, "account_type") != CASH:
			continue
		lowest_on, lowest = lowest_balance(account, first_date)
		if lowest < -0.005:
			frappe.throw(
				_("{0} does not hold enough cash: it would be {1} on {2}. Record the money that came in first, or pay from another treasury.").format(
					account.rsplit(" - ", 1)[0],
					frappe.format_value(lowest, {"fieldtype": "Currency"}),
					frappe.format_value(lowest_on, {"fieldtype": "Date"}),
				),
				title=_("Not Enough Cash"),
			)


def moved_by(doc):
	"""(account, what the document moved on it, its first date) for each account the document posted to."""
	return [
		(r.account, flt(r.moved), r.first_date)
		for r in frappe.db.sql(
			"""select account, sum(debit - credit) as moved, min(posting_date) as first_date
			from `tabGL Entry` where voucher_type = %s and voucher_no = %s and is_cancelled = 0
			group by account""",
			(doc.doctype, doc.name),
			as_dict=True,
		)
	]


def lowest_balance(account, from_date):
	"""(date, balance) where the box's live balance is lowest, from `from_date` on. The account is locked and its
	ledger read with locking reads, so another session's payment is seen, or waited for."""
	frappe.db.get_value("Account", account, "name", for_update=True)
	before = flt(
		frappe.db.sql(
			"""select sum(debit - credit) from `tabGL Entry`
			where account = %s and is_cancelled = 0 and posting_date < %s for update""",
			(account, from_date),
		)[0][0]
	)
	balance, lowest, lowest_on = before, None, from_date
	for day, moved in frappe.db.sql(
		"""select posting_date, sum(debit - credit) from `tabGL Entry`
		where account = %s and is_cancelled = 0 and posting_date >= %s
		group by posting_date order by posting_date for update""",
		(account, from_date),
	):
		balance += flt(moved)
		if lowest is None or balance < lowest:
			lowest, lowest_on = balance, getdate(day)
	return lowest_on, flt(lowest if lowest is not None else before, 2)
