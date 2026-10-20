# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Treasury Balances (ACC-03, first half): each cash box and wallet from the ledger, as the day began, its money in
# and out that day, and its balance; a branch manager sees her own box and the group's wallets. Rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_treasury_balances

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from imed_erp.imederp.report.treasury_balances.treasury_balances import execute

COMPANY = "Mohamed Mamdouh group"
AZARITA = "مكتبة الأزاريطة - MMG"
AZARITA_BOX = "خزينة مكتبة الأزاريطة - MMG"
MAWASAH_BOX = "خزينة مكتبة المواساة - MMG"
INSTAPAY = "محفظة InstaPay - MMG"
SARA = "sara@imed.local"


class IntegrationTestTreasuryBalances(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("treasury_balances")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="treasury_balances")

	def rows(self, date=None):
		return {r["treasury"]: r for r in execute({"date": date or today()})[1]}

	def move(self, amount, box=AZARITA_BOX, date=None):
		"""Money into (or, below zero, out of) a cash box against the owner's capital, as a journal entry."""
		capital = frappe.get_all("Account", filters={"company": COMPANY, "root_type": "Equity", "is_group": 0}, pluck="name", limit=1)[0]
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": COMPANY,
				"posting_date": date or today(),
				"accounts": [
					{"account": box, "debit_in_account_currency": max(amount, 0), "credit_in_account_currency": max(-amount, 0), "cost_center": AZARITA},
					{"account": capital, "debit_in_account_currency": max(-amount, 0), "credit_in_account_currency": max(amount, 0), "cost_center": AZARITA},
				],
			}
		).insert()
		entry.submit()

	def test_the_day_from_its_opening_to_its_balance(self):
		before, yesterday = self.rows()[AZARITA_BOX], self.rows(add_days(today(), -1))[AZARITA_BOX]
		self.move(1000, date=add_days(today(), -3))
		self.move(400)
		self.move(-150)
		row = self.rows()[AZARITA_BOX]
		self.assertEqual(
			(row["opening"], row["money_in"], row["money_out"], row["balance"]),
			(before["opening"] + 1000, before["money_in"] + 400, before["money_out"] + 150, before["balance"] + 1250),
		)
		ledger = flt(frappe.db.sql("select sum(debit - credit) from `tabGL Entry` where account=%s and is_cancelled=0", AZARITA_BOX)[0][0])
		self.assertAlmostEqual(row["balance"], ledger, places=2)
		# A day in the past shows the balance as it was then.
		self.assertEqual(self.rows(add_days(today(), -1))[AZARITA_BOX]["balance"], yesterday["balance"] + 1000)

	def test_a_branch_manager_sees_her_box_and_the_wallets(self):
		frappe.set_user(SARA)
		shown = set(self.rows())
		self.assertIn(AZARITA_BOX, shown)
		self.assertIn(INSTAPAY, shown)
		self.assertNotIn(MAWASAH_BOX, shown)
