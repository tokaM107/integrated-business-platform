# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Runs against the company's real cost centers, treasuries and expense accounts, found by their type rather than
# their name, so it works before and after setup_arabic_names.py. Balances are compared before and after, so
# existing data on the site does not matter, and everything a test creates is rolled back when the tests finish.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.doctype.expense.test_expense

import base64
import io
import os

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

# The linked records already exist on the site; without this Frappe would generate its own
# "_Test ..." records for every linked doctype and commit them.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Account",
	"Company",
	"Cost Center",
	"Expense",
	"Expense Category",
	"Journal Entry",
	"Supplier",
]

COMPANY = "Mohamed Mamdouh group"

# A 1x1 PNG, so the receipt is a real image.
PNG = base64.b64decode(
	"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

# Accounts ERPNext posts to by itself; an expense never goes there.
SYSTEM_EXPENSE_TYPES = [
	"Cost of Goods Sold",
	"Stock Adjustment",
	"Expenses Included In Valuation",
	"Expenses Included In Asset Valuation",
	"Depreciation",
	"Round Off",
]


def blank_pdf():
	"""A real one-page PDF; Frappe scans uploaded PDFs and refuses broken ones."""
	from pypdf import PdfWriter

	writer, buffer = PdfWriter(), io.BytesIO()
	writer.add_blank_page(width=100, height=100)
	writer.write(buffer)
	return buffer.getvalue()


def balance(account, cost_center=None):
	"""Debit minus credit of all live GL entries on an account, optionally for one business."""
	condition = "and cost_center = %(cost_center)s" if cost_center else ""
	return flt(
		frappe.db.sql(
			f"""select sum(debit - credit) from `tabGL Entry`
			where account = %(account)s and is_cancelled = 0 {condition}""",
			{"account": account, "cost_center": cost_center},
		)[0][0]
	)


class ExpenseFixtures:
	"""Real accounts and businesses of the company, plus a test category tree and supplier."""

	@classmethod
	def make_fixtures(cls):
		company_cost_center = frappe.db.get_value("Company", COMPANY, "cost_center")
		leaves = frappe.get_all(
			"Cost Center",
			filters={"company": COMPANY, "is_group": 0, "name": ["!=", company_cost_center]},
			fields=["name", "parent_cost_center"],
			order_by="lft",
		)
		# Two businesses under the same group, so a group filter can be tested.
		by_parent = {}
		for leaf in leaves:
			by_parent.setdefault(leaf.parent_cost_center, []).append(leaf.name)
		cls.activity_group, (cls.activity, cls.other_activity, *_) = next(
			(parent, names) for parent, names in by_parent.items() if len(names) >= 2
		)
		cls.treasury = frappe.get_all(
			"Account",
			filters={"company": COMPANY, "is_group": 0, "account_type": "Cash"},
			order_by="lft",
			limit=1,
			pluck="name",
		)[0]
		cls.utilities_account, cls.rent_account = frappe.get_all(
			"Account",
			filters={
				"company": COMPANY,
				"is_group": 0,
				"root_type": "Expense",
				"account_type": ["not in", SYSTEM_EXPENSE_TYPES],
			},
			order_by="lft",
			limit=2,
			pluck="name",
		)

		# _Test Expenses
		# ├── _Test Utilities        (own account)
		# │   ├── _Test Electricity  (no account: posted to _Test Utilities')
		# │   └── _Test Water
		# └── _Test Rent             (own account)
		cls.root = cls.make_category("_Test Expenses", is_group=1)
		cls.utilities = cls.make_category("_Test Utilities", cls.root, is_group=1, account=cls.utilities_account)
		cls.electricity = cls.make_category("_Test Electricity", cls.utilities)
		cls.water = cls.make_category("_Test Water", cls.utilities)
		cls.rent = cls.make_category("_Test Rent", cls.root, account=cls.rent_account)

		cls.supplier = (
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": "_Test Expense Supplier",
					"supplier_group": frappe.get_all("Supplier Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				}
			)
			.insert()
			.name
		)
		cls.files = []

	@classmethod
	def remove_fixture_files(cls):
		# The database is rolled back, but uploaded files stay on disk.
		for path in cls.files:
			if os.path.exists(path):
				os.remove(path)

	@staticmethod
	def make_category(name, parent=None, is_group=0, account=None):
		return (
			frappe.get_doc(
				{
					"doctype": "Expense Category",
					"expense_category_name": name,
					"parent_expense_category": parent,
					"is_group": is_group,
					"expense_account": account,
				}
			)
			.insert()
			.name
		)

	@classmethod
	def upload(cls, file_name="_test_receipt.png", content=PNG):
		file = frappe.get_doc({"doctype": "File", "file_name": file_name, "content": content, "is_private": 1}).insert()
		cls.files.append(file.get_full_path())
		return file.file_url

	@classmethod
	def new_expense(cls, **changes):
		"""An unsaved electricity bill of 1,000 for the first business, without a receipt."""
		return frappe.get_doc(
			{
				"doctype": "Expense",
				"posting_date": "2026-09-15",
				"activity": cls.activity,
				"expense_category": cls.electricity,
				"amount": 1000,
				"treasury": cls.treasury,
				"supplier": cls.supplier,
				**changes,
			}
		)

	@classmethod
	def submit_expense(cls, **changes):
		expense = cls.new_expense(receipt=cls.upload(), **changes).insert()
		expense.submit()
		return expense


class IntegrationTestExpense(ExpenseFixtures, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()

	@classmethod
	def tearDownClass(cls):
		cls.remove_fixture_files()
		super().tearDownClass()

	def test_submit_without_receipt_fails_then_succeeds_with_it(self):
		# The task's acceptance test: no receipt, no submit; attach it, and the submit goes through.
		expense = self.new_expense().insert()
		self.assertEqual(expense.docstatus, 0, "A draft can be saved before the receipt is at hand")

		with self.assertRaisesRegex(frappe.ValidationError, "Receipt attachment is required before submitting this expense."):
			expense.submit()
		self.assertEqual(frappe.db.get_value("Expense", expense.name, "docstatus"), 0)
		self.assertFalse(frappe.db.get_value("Expense", expense.name, "journal_entry"), "Nothing was posted")

		expense.reload()
		expense.receipt = self.upload()
		expense.submit()
		self.assertEqual(frappe.db.get_value("Expense", expense.name, "docstatus"), 1)

	def test_receipt_required_through_the_api(self):
		# The check is on the server: a document inserted as submitted, or submitted through
		# frappe.client, is refused the same way as from the form.
		submitted = self.new_expense()
		submitted.docstatus = 1
		self.assertRaisesRegex(frappe.ValidationError, "Receipt attachment is required", submitted.insert)

		from frappe.client import submit

		draft = self.new_expense().insert()
		self.assertRaisesRegex(frappe.ValidationError, "Receipt attachment is required", submit, draft.as_dict())
		self.assertEqual(frappe.db.get_value("Expense", draft.name, "docstatus"), 0)

	def test_receipt_must_be_an_uploaded_image_or_pdf(self):
		cases = {
			"not uploaded": "/private/files/_test_no_such_receipt.png",
			"not an image": self.upload("_test_receipt.txt", b"not a receipt"),
		}
		for label, receipt in cases.items():
			with self.subTest(label):
				expense = self.new_expense(receipt=receipt).insert()
				self.assertRaises(frappe.ValidationError, expense.submit)

		pdf = self.new_expense(receipt=self.upload("_test_receipt.pdf", blank_pdf())).insert()
		pdf.submit()
		self.assertEqual(pdf.docstatus, 1)

	def test_submit_posts_to_the_category_account_and_business(self):
		expense_before = balance(self.utilities_account, self.activity)
		treasury_before = balance(self.treasury)

		expense = self.submit_expense(amount=1500)

		# Electricity has no account of its own, so it is posted to its parent's, Utilities.
		self.assertEqual(expense.expense_account, self.utilities_account)
		self.assertEqual(expense.company, COMPANY)
		self.assertEqual(frappe.db.get_value("Journal Entry", expense.journal_entry, "docstatus"), 1)
		self.assertEqual(balance(self.utilities_account, self.activity), expense_before + 1500)
		self.assertEqual(balance(self.treasury), treasury_before - 1500)

	def test_cancel_reverses_the_entry(self):
		expense_before = balance(self.rent_account, self.activity)
		treasury_before = balance(self.treasury)

		expense = self.submit_expense(expense_category=self.rent, amount=700)
		expense.cancel()

		self.assertEqual(frappe.db.get_value("Journal Entry", expense.journal_entry, "docstatus"), 2)
		self.assertEqual(balance(self.rent_account, self.activity), expense_before)
		self.assertEqual(balance(self.treasury), treasury_before)

	def test_rejects_invalid_expenses(self):
		cases = {
			"zero amount": {"amount": 0},
			"group category": {"expense_category": self.utilities},
			"group activity": {"activity": self.activity_group},
			"expense account as treasury": {"treasury": self.rent_account},
		}
		for label, change in cases.items():
			with self.subTest(label):
				self.assertRaises(frappe.ValidationError, self.new_expense(**change).insert)

	def test_supplier_is_optional(self):
		# Salaries and petty cash have no supplier.
		expense = self.submit_expense(supplier=None)
		self.assertEqual(expense.docstatus, 1)
