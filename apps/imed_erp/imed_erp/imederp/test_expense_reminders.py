# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Reminders for recurring expenses (EXP-05) and the Expense Settings that drive them.
# Uses the real cost centers, accounts and expense categories (setup_coa.py, setup_expenses.py);
# everything made here is rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_expense_reminders

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from imed_erp.imederp.expense_reminders import get_recipients, send_recurring_expense_reminders

ABBR = "MMG"
SHARED = f"مصروفات المقر المشتركة - {ABBR}"
TREASURY = f"الخزينة الرئيسية - {ABBR}"


class IntegrationTestExpenseReminders(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		settings = frappe.get_single("Expense Settings")
		settings.reminder_days_before = 3
		settings.overdue_reminder_every_days = 2
		settings.save()
		cls.users = get_recipients()

	def make_recurring(self, due_in_days):
		recurring = frappe.get_doc(
			{
				"doctype": "Recurring Expense",
				"activity": SHARED,
				"expense_category": "الكهرباء",
				"treasury": TREASURY,
				"amount": 10000,
			}
		).insert()
		recurring.db_set("next_date", add_days(today(), due_in_days))
		return recurring

	def make_expense(self, recurring, posting_date):
		return frappe.get_doc(
			{
				"doctype": "Expense",
				"posting_date": posting_date,
				"activity": SHARED,
				"expense_type": "Every Month",
				"expense_category": "الكهرباء",
				"amount": 10000,
				"treasury": TREASURY,
				"recurring_expense": recurring.name,
			}
		).insert()

	def reminders_for(self, document_name):
		return frappe.get_all(
			"Notification Log",
			filters={"document_name": document_name, "type": "Alert"},
			pluck="for_user",
		)

	def test_owner_and_accountant_are_reminded(self):
		users = [frappe.db.get_value("User", user, "email") for user in self.users]
		self.assertIn("owner@imed.local", users)
		self.assertIn("accountant@imed.local", users)
		self.assertNotIn("Administrator", self.users)

	def test_reminded_days_before_due(self):
		recurring = self.make_recurring(due_in_days=3)
		send_recurring_expense_reminders()
		self.assertCountEqual(self.reminders_for(recurring.name), self.users)

	def test_second_run_same_day_adds_nothing(self):
		recurring = self.make_recurring(due_in_days=3)
		send_recurring_expense_reminders()
		send_recurring_expense_reminders()
		self.assertCountEqual(self.reminders_for(recurring.name), self.users)

	def test_not_reminded_on_other_days(self):
		recurring = self.make_recurring(due_in_days=5)
		send_recurring_expense_reminders()
		self.assertEqual(self.reminders_for(recurring.name), [])

	def test_bill_without_amount_is_reminded(self):
		recurring = self.make_recurring(due_in_days=3)
		recurring.db_set("amount", 0)
		send_recurring_expense_reminders()
		self.assertCountEqual(self.reminders_for(recurring.name), self.users)

	def test_disabled_is_not_reminded(self):
		recurring = self.make_recurring(due_in_days=3)
		recurring.db_set("enabled", 0)
		send_recurring_expense_reminders()
		self.assertEqual(self.reminders_for(recurring.name), [])

	def test_overdue_draft_reminded_every_few_days(self):
		recurring = self.make_recurring(due_in_days=10)
		two_days_late = self.make_expense(recurring, add_days(today(), -2))
		one_day_late = self.make_expense(recurring, add_days(today(), -1))

		send_recurring_expense_reminders()

		# Reminders repeat every 2 days, so day 2 reminds and day 1 does not.
		self.assertCountEqual(self.reminders_for(two_days_late.name), self.users)
		self.assertEqual(self.reminders_for(one_day_late.name), [])

	def test_submitted_expense_is_not_reminded(self):
		recurring = self.make_recurring(due_in_days=10)
		expense = self.make_expense(recurring, add_days(today(), -2))
		# Stands in for a submit; submitting for real needs an uploaded receipt, which is tested in test_expense.py.
		expense.db_set("docstatus", 1)

		send_recurring_expense_reminders()
		self.assertEqual(self.reminders_for(expense.name), [])

	def test_settings_reject_invalid_values(self):
		settings = frappe.get_single("Expense Settings")
		for fieldname, value in (
			("approval_threshold", -1),
			("reminder_days_before", 0),
			("overdue_reminder_every_days", 0),
		):
			with self.subTest(fieldname):
				settings.reload()
				settings.set(fieldname, value)
				self.assertRaises(frappe.ValidationError, settings.save)

	def test_late_draft_waiting_for_approval_reminds_the_owner(self):
		recurring = self.make_recurring(due_in_days=10)
		expense = self.make_expense(recurring, add_days(today(), -2))
		expense.db_set("approval_status", "Pending Approval")

		send_recurring_expense_reminders()
		reminded = self.reminders_for(expense.name)
		self.assertIn("owner@imed.local", reminded)
		self.assertNotIn("accountant@imed.local", reminded)
