# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# No completed transaction dated after today (QA-24; owner, 21 Oct 2026; imederp/dates.py): today and yesterday
# are accepted, tomorrow is refused, for a branch manager and for the accountant alike. What is planned keeps its
# future date. Rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_dates

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from imed_erp.imederp.dates import DATE_FIELD
from imed_erp.imederp.doctype.app_course.test_app_course import make_course, make_student
from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement
from imed_erp.imederp.doctype.expense.test_expense import ExpenseFixtures

COMPANY = "Mohamed Mamdouh group"
AZARITA = "مكتبة الأزاريطة - MMG"
AZARITA_BOX = "خزينة مكتبة الأزاريطة - MMG"
APP = "تطبيق BA Plus - MMG"
APP_BOX = "خزينة تطبيق BA Plus - MMG"
SARA = "sara@imed.local"
ACCOUNTANT = "accountant@imed.local"


class IntegrationTestDates(ExpenseFixtures, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()

	@classmethod
	def tearDownClass(cls):
		cls.remove_fixture_files()
		super().tearDownClass()

	def setUp(self):
		frappe.db.savepoint("dates_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="dates_test")

	def days(self):
		return {"yesterday": add_days(today(), -1), "today": today(), "tomorrow": add_days(today(), 1)}

	def assert_boundary(self, make):
		"""make(date) saves a document dated `date`: yesterday and today go through, tomorrow is refused."""
		for label, date in self.days().items():
			with self.subTest(label):
				if label == "tomorrow":
					self.assertRaisesRegex(frappe.ValidationError, "cannot be dated after today", make, date)
				else:
					make(date)

	def test_an_expense_for_a_branch_manager_and_for_the_accountant(self):
		def as_(user):
			def make(date):
				frappe.set_user(user)
				try:
					values = {"activity": AZARITA, "treasury": AZARITA_BOX} if user == SARA else {}
					return self.new_expense(posting_date=date, receipt=self.upload(), **values).insert()
				finally:
					frappe.set_user("Administrator")

			return make

		for user in (SARA, ACCOUNTANT):
			with self.subTest(user):
				self.assert_boundary(as_(user))

	def test_a_journal_entry(self):
		capital = frappe.get_all("Account", filters={"company": COMPANY, "root_type": "Equity", "is_group": 0}, pluck="name", limit=1)[0]

		def make(date):
			return frappe.get_doc(
				{
					"doctype": "Journal Entry",
					"company": COMPANY,
					"posting_date": date,
					"accounts": [
						{"account": AZARITA_BOX, "debit_in_account_currency": 10, "cost_center": AZARITA},
						{"account": capital, "credit_in_account_currency": 10, "cost_center": AZARITA},
					],
				}
			).insert()

		self.assert_boundary(make)

	def test_a_collection_from_a_doctor(self):
		agreement = make_agreement("App")
		frappe.get_doc(
			{"doctype": "Doctor Ledger Entry", "agreement": agreement, "entry_type": "Adjustment", "amount": 500, "entry_date": today()}
		).insert().submit()

		def make(date):
			return frappe.get_doc(
				{"doctype": "Doctor Ledger Entry", "agreement": agreement, "entry_type": "Collection", "amount": 10, "entry_date": date, "treasury": APP_BOX}
			).insert()

		self.assert_boundary(make)

	def test_a_subscription(self):
		course = make_course("_Test Dated Course")
		count = iter(range(900, 910))

		def make(date):
			return frappe.get_doc(
				{"doctype": "App Subscription", "student": make_student(next(count)), "course": course, "subscription_date": date, "cost_center": APP}
			).insert()

		self.assert_boundary(make)

	def test_what_is_planned_keeps_its_future_date(self):
		for doctype in ("Booking", "Recurring Expense", "Allocation Rule", "Platform Fee Schedule", "Academic Period"):
			with self.subTest(doctype):
				self.assertNotIn(doctype, DATE_FIELD)

	def test_qa37_a_date_outside_the_company_s_fiscal_years_is_refused(self):
		# The development site holds "_Test Fiscal Year"s that name no company, which ERPNext would apply to the
		# group too; the group posts only in its own (2026-2027 from 1 Sep 2026).
		capital = frappe.get_all("Account", filters={"company": COMPANY, "root_type": "Equity", "is_group": 0}, pluck="name", limit=1)[0]
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": COMPANY,
				"posting_date": "2026-08-31",
				"accounts": [
					{"account": AZARITA_BOX, "debit_in_account_currency": 10, "cost_center": AZARITA},
					{"account": capital, "credit_in_account_currency": 10, "cost_center": AZARITA},
				],
			}
		)
		self.assertRaisesRegex(frappe.ValidationError, "not in a fiscal year", entry.insert)
		entry.posting_date = "2026-09-01"
		entry.insert()
