# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A cash box never goes below zero (owner, 21 Oct 2026; imederp/cash_balance.py): an expense, a transfer, a payout,
# any payment of more than the box holds is refused, on any day from its date to today; cancelling cash that came in
# is checked too; money coming in is always accepted. Every check is against what the box holds now, so it holds on
# any site. Rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_cash_balance

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement

COMPANY = "Mohamed Mamdouh group"
AZARITA = "مكتبة الأزاريطة - MMG"
AZARITA_BOX = "خزينة مكتبة الأزاريطة - MMG"
HALLS = "قاعات Imed - MMG"
HALLS_BOX = "خزينة سنتر Imed - MMG"


def balance(box, on=None):
	return flt(
		frappe.db.sql(
			"select sum(debit - credit) from `tabGL Entry` where account=%s and is_cancelled=0 and posting_date <= %s",
			(box, on or today()),
		)[0][0],
		2,
	)


class IntegrationTestCashBalance(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("cash_balance")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="cash_balance")

	def refused(self, fn, *args, **kwargs):
		"""The call is refused and what it wrote is undone, as a failed request would be."""
		frappe.db.savepoint("refused")
		with self.assertRaisesRegex(frappe.ValidationError, "does not hold enough cash"):
			fn(*args, **kwargs)
		frappe.db.rollback(save_point="refused")

	def capital(self):
		return frappe.get_all("Account", filters={"company": COMPANY, "root_type": "Equity", "is_group": 0}, pluck="name", limit=1)[0]

	def move(self, amount, date=None, box=AZARITA_BOX, submit=True):
		"""Cash into (or, below zero, out of) the box, against capital."""
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": COMPANY,
				"posting_date": date or today(),
				"accounts": [
					{"account": box, "debit_in_account_currency": max(amount, 0), "credit_in_account_currency": max(-amount, 0), "cost_center": AZARITA},
					{"account": self.capital(), "debit_in_account_currency": max(-amount, 0), "credit_in_account_currency": max(amount, 0), "cost_center": AZARITA},
				],
			}
		).insert()
		if submit:
			entry.submit()
		return entry

	def start_at(self, amount):
		"""The box holds exactly `amount` today: what is missing comes in on the fiscal year's first day, what is over
		goes out today."""
		held = balance(AZARITA_BOX)
		if held < amount:
			self.move(amount - held, date="2026-09-01")
		elif held > amount:
			self.move(amount - held)
		self.assertEqual(balance(AZARITA_BOX), amount)

	def test_no_more_out_than_the_box_holds(self):
		self.start_at(500)
		self.refused(self.move, -500.01)
		self.assertEqual(balance(AZARITA_BOX), 500)
		# All of it is fine; nothing left after it.
		self.move(-500)
		self.assertEqual(balance(AZARITA_BOX), 0)
		self.refused(self.move, -1)

	def test_money_coming_in_is_always_accepted(self):
		self.start_at(0)
		self.move(10)
		self.assertEqual(balance(AZARITA_BOX), 10)

	def test_a_payment_dated_back_cannot_leave_an_earlier_day_short(self):
		# 300 came in yesterday and was paid out today; a payment dated yesterday has nothing left to take.
		self.start_at(0)
		self.move(300, date=add_days(today(), -1))
		self.move(-300)
		self.refused(self.move, -100, add_days(today(), -1))

	def test_an_expense_a_transfer_and_a_payout_are_refused_beyond_the_box(self):
		self.start_at(100)
		term = frappe.get_all("Academic Period", filters={"period_type": "Term", "is_closed": 0}, pluck="name", limit=1)[0]
		transfer = frappe.get_doc(
			{
				"doctype": "Inter Business Transfer", "posting_date": today(), "from_business": AZARITA, "from_treasury": AZARITA_BOX,
				"to_business": HALLS, "to_treasury": HALLS_BOX, "amount": 150, "reason": "_Test", "period": term,
			}
		).insert()
		self.refused(transfer.submit)
		# A payout to a doctor out of the same box.
		agreement = make_agreement("Books")
		frappe.get_doc({"doctype": "Doctor Ledger Entry", "agreement": agreement, "entry_type": "Accrual", "amount": 1000, "entry_date": today()}).insert().submit()
		payout = frappe.get_doc(
			{"doctype": "Doctor Ledger Entry", "agreement": agreement, "entry_type": "Payout", "amount": 150, "entry_date": today(), "treasury": AZARITA_BOX}
		).insert()
		self.refused(payout.submit)
		self.assertEqual(balance(AZARITA_BOX), 100)

	def test_cancelling_cash_that_came_in_and_was_spent_is_refused(self):
		self.start_at(0)
		came_in = self.move(200)
		self.move(-150)
		came_in.reload()
		self.refused(came_in.cancel)

	def test_the_box_is_locked_before_its_balance_is_read(self):
		# Two sessions cannot run here; tests/concurrency_check.py runs two payments at once on a copy of the site.
		self.start_at(100)
		reads = []
		original = frappe.db.get_value

		def spy(doctype, name=None, *args, **kwargs):
			if doctype == "Account" and kwargs.get("for_update"):
				reads.append(("lock", name))
			return original(doctype, name, *args, **kwargs)

		with patch("imed_erp.imederp.cash_balance.frappe.db.get_value", side_effect=spy):
			self.move(-10)
		self.assertIn(("lock", AZARITA_BOX), reads)
