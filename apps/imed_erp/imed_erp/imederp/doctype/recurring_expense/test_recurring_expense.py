# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Uses the real cost centers, accounts and expense categories (setup_coa.py, setup_expenses.py);
# everything made here is rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Recurring Expense"

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, getdate, today

from imed_erp.imederp.doctype.recurring_expense.recurring_expense import (
	due_date_in,
	make_due_expenses,
	next_due_date,
)

ABBR = "MMG"
SHARED = f"مصروفات المقر المشتركة - {ABBR}"
TREASURY = f"الخزينة الرئيسية - {ABBR}"

# The records above are real, not "_Test ..." ones.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Account", "Cost Center", "Expense Category"]


class IntegrationTestRecurringExpense(IntegrationTestCase):
	def make_recurring(self, **values):
		return frappe.get_doc(
			{
				"doctype": "Recurring Expense",
				"activity": SHARED,
				"expense_category": "الإيجار",
				"treasury": TREASURY,
				"amount": 46000,
				"description": "إيجار الشهر",
				**values,
			}
		).insert()

	def drafts_of(self, recurring):
		return frappe.get_all(
			"Expense",
			filters={"recurring_expense": recurring.name},
			fields=["posting_date", "amount", "docstatus", "receipt", "description"],
			order_by="posting_date",
		)

	def test_due_date_falls_back_to_the_months_last_day(self):
		self.assertEqual(due_date_in("2026-02-10", 31), getdate("2026-02-28"))
		self.assertEqual(due_date_in("2026-03-10", 31), getdate("2026-03-31"))
		self.assertEqual(next_due_date(5, "2026-10-04"), getdate("2026-10-05"))
		self.assertEqual(next_due_date(1, "2026-10-04"), getdate("2026-11-01"))
		self.assertEqual(next_due_date(4, "2026-10-04"), getdate("2026-10-04"))

	def test_next_date_filled_from_the_day(self):
		recurring = self.make_recurring(day_of_month=1)
		self.assertEqual(getdate(recurring.next_date), next_due_date(1, today()))

	def test_due_bill_makes_a_draft_and_moves_to_next_month(self):
		recurring = self.make_recurring(next_date=today())

		make_due_expenses()
		make_due_expenses()  # A second run the same day adds nothing.

		drafts = self.drafts_of(recurring)
		self.assertEqual(len(drafts), 1)
		self.assertEqual(drafts[0].docstatus, 0)
		self.assertEqual(str(drafts[0].posting_date), today())
		self.assertEqual(drafts[0].amount, 46000)
		self.assertEqual(drafts[0].description, "إيجار الشهر")
		self.assertFalse(drafts[0].receipt)
		recurring.reload()
		self.assertEqual(getdate(recurring.next_date), due_date_in(add_months(today(), 1), recurring.day_of_month))

	def test_changed_amount_used_from_then_on(self):
		recurring = self.make_recurring(next_date=today())
		recurring.amount = 50000
		recurring.save()

		make_due_expenses()
		self.assertEqual(self.drafts_of(recurring)[0].amount, 50000)

	def test_missed_months_each_get_a_draft(self):
		recurring = self.make_recurring(day_of_month=getdate(today()).day)
		recurring.db_set("next_date", add_months(today(), -2))

		make_due_expenses()
		self.assertEqual(len(self.drafts_of(recurring)), 3)

	def test_not_due_yet_or_disabled_makes_nothing(self):
		later = self.make_recurring(next_date=add_days(today(), 1))
		disabled = self.make_recurring(next_date=today(), enabled=0)

		make_due_expenses()
		self.assertEqual(self.drafts_of(later), [])
		self.assertEqual(self.drafts_of(disabled), [])

	def test_rejects_what_an_expense_would_reject(self):
		for values in (
			{"amount": -1},
			{"day_of_month": 32},
			{"treasury": f"الإيجار - {ABBR}"},
		):
			with self.subTest(values):
				self.assertRaises(frappe.ValidationError, self.make_recurring, **values)

	def test_without_amount_makes_no_draft_but_moves_on(self):
		recurring = self.make_recurring(next_date=today(), amount=None)

		make_due_expenses()
		self.assertEqual(self.drafts_of(recurring), [])
		recurring.reload()
		self.assertGreater(getdate(recurring.next_date), getdate(today()))

	def test_title_names_the_bill_and_the_place(self):
		self.assertEqual(self.make_recurring().title, "الإيجار - مصروفات المقر المشتركة")

	def test_switched_back_on_starts_this_month(self):
		# Off for three months: switching it back on makes this month's draft, not one per month it was off.
		recurring = self.make_recurring(day_of_month=1)
		recurring.db_set({"enabled": 0, "next_date": add_months(today(), -3)})
		recurring.reload()
		recurring.enabled = 1
		recurring.save()
		self.assertEqual(getdate(recurring.next_date), due_date_in(today(), 1))

		make_due_expenses()
		self.assertEqual(len(self.drafts_of(recurring)), 1)

	def test_new_day_does_not_repeat_a_recorded_month(self):
		recurring = self.make_recurring(next_date=today())
		make_due_expenses()
		recurring.reload()
		recurring.day_of_month = 28 if getdate(today()).day != 28 else 27
		recurring.save()

		# This month already has its draft, so the new day starts next month.
		self.assertEqual(getdate(recurring.next_date), due_date_in(add_months(today(), 1), recurring.day_of_month))

	def test_category_with_bills_cannot_become_a_group(self):
		self.make_recurring(expense_category="الكهرباء")
		category = frappe.get_doc("Expense Category", "الكهرباء")
		category.is_group = 1
		self.assertRaises(frappe.ValidationError, category.save)
