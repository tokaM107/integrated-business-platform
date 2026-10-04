# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Every query is limited to the test category tree, so expenses already on the site do not change the totals,
# and everything a test creates is rolled back when the tests finish.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.report.expense_report.test_expense_report

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.expense.test_expense import ExpenseFixtures
from imed_erp.imederp.report.expense_report.expense_report import execute


class IntegrationTestExpenseReport(ExpenseFixtures, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()

		# September 2026: business A pays 3,000 + 2,000 electricity and 400 water and 5,000 rent;
		# business B pays 1,200 electricity. October 2026: business A pays 800 electricity.
		# One more electricity bill for A is cancelled, and one is left as a draft: neither counts.
		cls.submit_expense(posting_date="2026-09-03", amount=3000)
		cls.submit_expense(posting_date="2026-09-20", amount=2000)
		cls.submit_expense(posting_date="2026-09-21", expense_category=cls.water, amount=400)
		cls.submit_expense(posting_date="2026-09-01", expense_category=cls.rent, amount=5000, supplier=None)
		cls.submit_expense(posting_date="2026-09-10", activity=cls.other_activity, amount=1200)
		cls.submit_expense(posting_date="2026-10-02", amount=800)
		cls.submit_expense(posting_date="2026-09-25", amount=999).cancel()
		cls.new_expense(posting_date="2026-09-26", amount=777).insert()

	@classmethod
	def tearDownClass(cls):
		cls.remove_fixture_files()
		super().tearDownClass()

	def run_report(self, **filters):
		result = execute({"expense_category": self.root, **filters})
		return result[0], result[1]

	def total(self, rows):
		return sum(row["amount"] for row in rows)

	def september(self, **filters):
		return self.run_report(from_date="2026-09-01", to_date="2026-09-30", **filters)

	def test_detail_rows_show_every_column(self):
		columns, rows = self.september(activity=self.activity, expense_category=self.rent)
		self.assertEqual(len(rows), 1)
		row = rows[0]
		for fieldname in ("name", "expense_category", "activity", "amount", "posting_date", "supplier", "treasury"):
			self.assertIn(fieldname, [column["fieldname"] for column in columns])
		self.assertEqual(row.expense_category, self.rent)
		self.assertEqual(row.activity, self.activity)
		self.assertEqual(row.amount, 5000)
		self.assertEqual(str(row.posting_date), "2026-09-01")
		self.assertEqual(row.treasury, self.treasury)

	def test_total_by_activity_category_and_period(self):
		# The task's example: one business, one month, one category.
		_columns, rows = self.september(activity=self.activity, expense_category=self.electricity)
		self.assertEqual(self.total(rows), 5000, "3,000 + 2,000; October, cancelled and draft bills are left out")

	def test_group_category_includes_its_children(self):
		_columns, rows = self.september(activity=self.activity, expense_category=self.utilities)
		self.assertEqual(self.total(rows), 5400, "Electricity 5,000 + water 400")

	def test_group_activity_includes_its_businesses(self):
		_columns, rows = self.september(activity=self.activity_group, expense_category=self.electricity)
		self.assertEqual(self.total(rows), 6200, "Business A 5,000 + business B 1,200")

	def test_date_range(self):
		_columns, rows = self.run_report(from_date="2026-10-01", to_date="2026-10-31")
		self.assertEqual(self.total(rows), 800)
		_columns, rows = self.run_report()
		self.assertEqual(self.total(rows), 12400, "Every submitted test expense, with no date filter")

	def test_supplier_filter(self):
		_columns, rows = self.september(supplier=self.supplier)
		self.assertEqual(self.total(rows), 6600, "Everything in September but the rent, which has no supplier")

	def test_group_by_category(self):
		columns, rows = self.september(group_by="Expense Category")
		self.assertEqual([column["fieldname"] for column in columns], ["expense_category", "count", "amount"])
		totals = {row.expense_category: (row.count, row.amount) for row in rows}
		self.assertEqual(
			totals,
			{self.electricity: (3, 6200), self.water: (1, 400), self.rent: (1, 5000)},
		)

	def test_group_by_activity_and_category(self):
		_columns, rows = self.september(group_by="Activity and Expense Category")
		totals = {(row.activity, row.expense_category): row.amount for row in rows}
		self.assertEqual(
			totals,
			{
				(self.activity, self.electricity): 5000,
				(self.activity, self.water): 400,
				(self.activity, self.rent): 5000,
				(self.other_activity, self.electricity): 1200,
			},
		)

	def test_group_by_month(self):
		result = execute({"expense_category": self.root, "group_by": "Month"})
		totals = {row.month: row.amount for row in result[1]}
		self.assertEqual(totals, {"2026-09": 11600, "2026-10": 800})
		chart = result[3]
		self.assertEqual(chart["data"]["labels"], ["2026-09", "2026-10"])
