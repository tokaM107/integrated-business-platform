# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The daily close of a treasury (ACC-03): the day as the books show it, the cash counted, the difference; once a day
# per cash box; a branch manager closes her own box or a group wallet; nothing is posted. Rolled back.
#
# Run:
#   bench --site frontend run-tests --doctype "Treasury Close"

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from imed_erp.imederp.report.treasury_balances.treasury_balances import execute as balances

IGNORE_TEST_RECORD_DEPENDENCIES = ["Account", "Cost Center", "User", "Treasury Close"]

COMPANY = "Mohamed Mamdouh group"
AZARITA = "مكتبة الأزاريطة - MMG"
AZARITA_BOX = "خزينة مكتبة الأزاريطة - MMG"
MAWASAH = "مكتبة المواساة - MMG"
MAWASAH_BOX = "خزينة مكتبة المواساة - MMG"
INSTAPAY = "محفظة InstaPay - MMG"
SARA = "sara@imed.local"


class IntegrationTestTreasuryClose(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("treasury_close")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="treasury_close")

	def move(self, amount, box=AZARITA_BOX, business=AZARITA):
		capital = frappe.get_all("Account", filters={"company": COMPANY, "root_type": "Equity", "is_group": 0}, pluck="name", limit=1)[0]
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": COMPANY,
				"posting_date": today(),
				"accounts": [
					{"account": box, "debit_in_account_currency": max(amount, 0), "credit_in_account_currency": max(-amount, 0), "cost_center": business},
					{"account": capital, "debit_in_account_currency": max(-amount, 0), "credit_in_account_currency": max(amount, 0), "cost_center": business},
				],
			}
		).insert()
		entry.submit()

	def close(self, counted, treasury=AZARITA_BOX, business=AZARITA, date=None, user=None):
		if user:
			frappe.set_user(user)
		try:
			return frappe.get_doc(
				{"doctype": "Treasury Close", "treasury": treasury, "business": business, "close_date": date or today(), "counted": counted}
			).insert()
		finally:
			frappe.set_user("Administrator")

	def test_the_day_as_the_books_show_it_and_the_difference(self):
		self.move(1000)
		self.move(-200)
		close = self.close(0)
		row = {r["treasury"]: r for r in balances({"date": today()})[1]}[AZARITA_BOX]
		self.assertEqual(
			(close.opening, close.money_in, close.money_out, close.expected),
			(row["opening"], row["money_in"], row["money_out"], row["balance"]),
		)
		# 50 short.
		close.counted = close.expected - 50
		close.save()
		self.assertEqual((close.difference, close.counted_by), (-50, "Administrator"))
		close.submit()
		# Recorded only: nothing is posted for the difference.
		self.assertFalse(frappe.db.exists("GL Entry", {"voucher_no": close.name}))

	def test_entries_after_it_was_saved_are_in_it_when_submitted(self):
		close = self.close(0)
		expected = close.expected
		self.move(300)
		close.submit()
		self.assertEqual(flt(close.expected), flt(expected) + 300)

	def test_once_a_day_per_cash_box(self):
		self.close(0)
		self.assertRaisesRegex(frappe.ValidationError, "already closed", self.close, 0)
		self.close(0, date=add_days(today(), -1))
		self.close(0, treasury=INSTAPAY)

	def test_sara_closes_her_own_box_or_a_wallet(self):
		self.close(0, user=SARA)
		self.close(0, treasury=INSTAPAY, user=SARA)
		# Mawasah's box under her own business: refused by the treasury check; under Mawasah's: not her business.
		self.assertRaisesRegex(frappe.ValidationError, "is not a treasury of", self.close, 0, MAWASAH_BOX, AZARITA, user=SARA)
		self.assertRaises(frappe.PermissionError, self.close, 0, MAWASAH_BOX, MAWASAH, user=SARA)

	def test_not_ahead_of_today_and_kept_once_submitted(self):
		self.assertRaisesRegex(frappe.ValidationError, "after today", self.close, 0, date=add_days(today(), 1))
		close = self.close(0)
		close.submit()
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Treasury Close", close.name)
