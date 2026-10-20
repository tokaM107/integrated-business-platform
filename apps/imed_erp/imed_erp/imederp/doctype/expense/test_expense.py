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
	"Recurring Expense",
	"Company",
	"Cost Center",
	"Expense",
	"Expense Category",
	"Journal Entry",
	"Supplier",
	"User",
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
		# Bytes after the end of the image keep it valid and make each upload its own file: Frappe gives identical
		# content one URL, and a receipt is filed under one expense only (SEC-03).
		content = content + frappe.generate_hash().encode()
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
				# Refused on save, or at the latest on submit.
				with self.assertRaises(frappe.ValidationError):
					self.new_expense(receipt=receipt).insert().submit()

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

	def test_entry_is_cancelled_only_through_the_expense(self):
		# Cancelling the entry alone would put the money back in the treasury while the report still counts it.
		expense = self.submit_expense(amount=300)
		journal_entry = frappe.get_doc("Journal Entry", expense.journal_entry)
		self.assertRaisesRegex(frappe.ValidationError, "Cancel the expense instead", journal_entry.cancel)
		self.assertEqual(frappe.db.get_value("Journal Entry", expense.journal_entry, "docstatus"), 1)

	def test_category_with_expenses_cannot_become_a_group(self):
		self.submit_expense(expense_category=self.rent, amount=50)
		rent = frappe.get_doc("Expense Category", self.rent)
		rent.is_group = 1
		self.assertRaises(frappe.ValidationError, rent.save)

	def test_supplier_is_optional(self):
		# Salaries and petty cash have no supplier.
		expense = self.submit_expense(supplier=None)
		self.assertEqual(expense.docstatus, 1)

	def test_new_monthly_expense_is_added_to_the_places_bills(self):
		expense = self.submit_expense(expense_type="Every Month")

		bill = frappe.get_doc("Recurring Expense", expense.recurring_expense)
		self.assertEqual(bill.activity, self.activity)
		self.assertEqual(bill.expense_category, self.electricity)
		self.assertEqual(bill.treasury, self.treasury)
		self.assertEqual(bill.day_of_month, 15)

		# Next month the same bill is picked up, not added again.
		again = self.submit_expense(expense_type="Every Month", posting_date="2026-10-15")
		self.assertEqual(again.recurring_expense, bill.name)

	def test_one_time_expense_is_not_a_monthly_bill(self):
		bills = frappe.db.count("Recurring Expense")
		expense = self.submit_expense(activity=self.other_activity, expense_category=self.water)
		self.assertEqual(expense.expense_type, "This Month Only")
		self.assertFalse(expense.recurring_expense)
		self.assertEqual(frappe.db.count("Recurring Expense"), bills)

	def test_monthly_bill_must_be_the_places_own(self):
		other_place = self.submit_expense(expense_type="Every Month", activity=self.other_activity)

		expense = self.new_expense(expense_type="Every Month", recurring_expense=other_place.recurring_expense)
		self.assertRaises(frappe.ValidationError, expense.insert)


	def test_branch_manager_pays_from_their_own_cash_box(self):
		# Sara runs Azarita's library: its cash box or the group's wallets, not another business's treasury.
		# Each expense has its own receipt, uploaded by her (SEC-03).
		frappe.set_user("sara@imed.local")
		try:
			azarita = "مكتبة الأزاريطة - MMG"
			for treasury in ("الخزينة الرئيسية - MMG", "خزينة مكتبة المواساة - MMG"):
				with self.subTest(treasury):
					expense = self.new_expense(activity=azarita, treasury=treasury, receipt=self.upload())
					self.assertRaisesRegex(frappe.ValidationError, "treasury", expense.insert)
			for treasury in ("خزينة مكتبة الأزاريطة - MMG", "محفظة InstaPay - MMG"):
				self.new_expense(activity=azarita, treasury=treasury, receipt=self.upload()).insert()
		finally:
			frappe.set_user("Administrator")

	def test_sec03_the_receipt_is_this_expense_s_own_private_file(self):
		# Another expense's receipt, a file someone else uploaded, and a public file are all refused: on save
		# Frappe would attach that file to this expense and open it to whoever can read the expense.
		filed = self.submit_expense()
		self.assertRaisesRegex(frappe.ValidationError, "already filed", self.new_expense(receipt=filed.receipt).insert)

		someone_else = self.upload()
		frappe.set_user("sara@imed.local")
		try:
			azarita = "مكتبة الأزاريطة - MMG"
			expense = self.new_expense(activity=azarita, treasury="خزينة مكتبة الأزاريطة - MMG", receipt=someone_else)
			self.assertRaisesRegex(frappe.ValidationError, "file from elsewhere", expense.insert)
			self.assertFalse(frappe.db.exists("File", {"file_url": someone_else, "attached_to_doctype": "Expense"}))
		finally:
			frappe.set_user("Administrator")

		public = frappe.get_doc({"doctype": "File", "file_name": "_test_public_receipt.png", "content": PNG, "is_private": 0}).insert()
		self.files.append(public.get_full_path())
		self.assertRaisesRegex(frappe.ValidationError, "private file", self.new_expense(receipt=public.file_url).insert)

		# Its own receipt stays accepted once it is attached to it, through approval and submit.
		own = self.new_expense(receipt=self.upload()).insert()
		self.assertTrue(frappe.db.exists("File", {"file_url": own.receipt, "attached_to_name": own.name}))
		own.reload()
		own.submit()

	def test_posted_expense_is_never_deleted(self):
		# ACC-07: a mistake is cancelled, which keeps it on record; only a draft can be deleted.
		expense = self.submit_expense()
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Expense", expense.name)
		expense.cancel()
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Expense", expense.name)

		# Only the owner deletes, even a draft.
		draft = self.new_expense().insert()
		frappe.set_user("accountant@imed.local")
		try:
			self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Expense", draft.name)
		finally:
			frappe.set_user("Administrator")
		frappe.set_user("owner@imed.local")
		try:
			frappe.delete_doc("Expense", draft.name)
		finally:
			frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists("Expense", draft.name))

	def test_every_financial_doctype_keeps_its_guards(self):
		# hooks.py lists each doctype once: a second entry for the same doctype would replace the first,
		# and the delete guard or the closed-period check would stop running without any error.
		from imed_erp.imederp.no_delete import FINANCIAL_DOCTYPES
		from imed_erp.imederp.period_lock import LOCKED_DOCTYPES

		events = frappe.get_hooks("doc_events", app_name="imed_erp")
		for doctype in FINANCIAL_DOCTYPES:
			with self.subTest(doctype):
				self.assertIn("imed_erp.imederp.no_delete.block_delete_of_posted", events[doctype]["on_trash"])
		for doctype in LOCKED_DOCTYPES:
			with self.subTest(doctype):
				self.assertIn("imed_erp.imederp.period_lock.validate_closed_period", events[doctype]["validate"])
				self.assertIn("imed_erp.imederp.period_lock.validate_closed_period", events[doctype]["before_cancel"])
		# The reorder alerts (LIB-04) are still there next to them.
		self.assertIn("imed_erp.imederp.stock_reorder.alert_on_reorder_level", events["Stock Entry"]["on_submit"])

	def test_no_expense_in_a_closed_month(self):
		period = frappe.get_doc(
			{
				"doctype": "Accounting Period",
				"period_name": "_Test Closed Month",
				"start_date": "2026-08-01",
				"end_date": "2026-08-31",
				"company": COMPANY,
				"closed_documents": [{"document_type": "Expense", "closed": 1}],
			}
		).insert()
		try:
			self.assertRaises(frappe.ValidationError, self.new_expense(posting_date="2026-08-15").insert)
			self.new_expense(posting_date="2026-09-15").insert()
		finally:
			frappe.delete_doc("Accounting Period", period.name)


OWNER = "owner@imed.local"
ACCOUNTANT = "accountant@imed.local"
# Sara runs Azarita's library: she records its expenses, from its cash box or the group's wallets.
SARA = "sara@imed.local"
AZARITA = "مكتبة الأزاريطة - MMG"
AZARITA_CASH = "خزينة مكتبة الأزاريطة - MMG"
INSTAPAY = "محفظة InstaPay - MMG"


class IntegrationTestExpenseApproval(ExpenseFixtures, IntegrationTestCase):
	"""Every expense is posted only once the accountant approves it, since the money is paid out of his cash
	(owner's decision of 12 Oct 2026); the owner can approve too."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()

	@classmethod
	def tearDownClass(cls):
		cls.remove_fixture_files()
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def draft(self, amount, user=SARA):
		# Uploaded by whoever records the expense, as from the form (SEC-03).
		frappe.set_user(user)
		receipt = self.upload()
		return self.new_expense(amount=amount, activity=AZARITA, treasury=AZARITA_CASH, receipt=receipt).insert()

	def as_user(self, user, expense):
		frappe.set_user(user)
		return frappe.get_doc("Expense", expense.name)

	def test_even_a_small_expense_needs_approval(self):
		expense = self.draft(50)
		self.assertRaises(frappe.ValidationError, expense.submit)

	def test_only_the_owner_changes_the_expense_settings(self):
		frappe.set_user(ACCOUNTANT)
		self.assertFalse(frappe.has_permission("Expense Settings", "write"))
		frappe.set_user(OWNER)
		self.assertTrue(frappe.has_permission("Expense Settings", "write"))

	def test_the_accountant_approves(self):
		expense = self.draft(46000)
		self.assertRaises(frappe.ValidationError, expense.submit)
		# A refused submit leaves the copy in memory marked as submitted; the form reloads it too.
		expense.reload()

		expense.request_approval()
		self.assertEqual(expense.approval_status, "Pending Approval")
		self.assertTrue(
			frappe.db.exists("Notification Log", {"document_name": expense.name, "for_user": ACCOUNTANT, "type": "Alert"})
		)
		# The owner can approve, but only the accountant is notified of each request.
		self.assertFalse(frappe.db.exists("Notification Log", {"document_name": expense.name, "for_user": OWNER}))
		# Sara cannot approve her own request.
		self.assertRaises(frappe.PermissionError, expense.approve)

		expense = self.as_user(ACCOUNTANT, expense)
		expense.approve()
		expense.reload()
		self.assertEqual(expense.docstatus, 1)
		self.assertEqual(expense.approval_status, "Approved")
		self.assertEqual(expense.approved_by, ACCOUNTANT)
		self.assertTrue(expense.journal_entry)

	def test_no_one_approves_by_writing_the_status(self):
		# The fields are read-only only on the form; written through the API they are refused.
		expense = self.draft(46000)
		for field, value in (("approval_status", "Approved"), ("approved_by", ACCOUNTANT)):
			with self.subTest(field):
				doc = frappe.get_doc("Expense", expense.name)
				doc.set(field, value)
				self.assertRaisesRegex(frappe.ValidationError, "only with Request Approval", doc.save)
		doc = frappe.get_doc("Expense", expense.name)
		doc.approval_status = "Approved"
		self.assertRaises(frappe.ValidationError, doc.submit)
		self.assertEqual(frappe.db.get_value("Expense", expense.name, ["docstatus", "approval_status"]), (0, None))

		# A pending request cannot be turned into an approval either.
		doc = frappe.get_doc("Expense", expense.name)
		doc.request_approval()
		doc = frappe.get_doc("Expense", expense.name)
		doc.approval_status = "Approved"
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_a_new_expense_starts_without_an_approval(self):
		# An expense made with an approval already on it (a copy, an amendment, the API) is approved afresh.
		frappe.set_user(SARA)
		receipt = self.upload()
		expense = self.new_expense(
			amount=100, activity=AZARITA, treasury=AZARITA_CASH, receipt=receipt,
			approval_status="Approved", approved_by=ACCOUNTANT,
		).insert()
		self.assertEqual((expense.approval_status, expense.approved_by), (None, None))
		self.assertRaises(frappe.ValidationError, expense.submit)

	def test_rejected_expense_is_closed(self):
		expense = self.draft(46000)
		expense.request_approval()

		expense = self.as_user(ACCOUNTANT, expense)
		expense.reject("الإيصال مش واضح")
		expense = self.as_user(SARA, expense)
		self.assertEqual(expense.approval_status, "Rejected")
		self.assertEqual(expense.rejection_reason, "الإيصال مش واضح")

		expense.amount = 40000
		self.assertRaises(frappe.ValidationError, expense.save)
		self.assertRaises(frappe.ValidationError, frappe.get_doc("Expense", expense.name).submit)

	def test_changing_the_amount_needs_approval_again(self):
		expense = self.draft(46000)
		expense.request_approval()
		expense.amount = 60000
		expense.save()
		self.assertFalse(expense.approval_status)
		self.assertRaises(frappe.ValidationError, expense.submit)

	def test_approvers_own_expense_needs_no_approval(self):
		# The accountant's and the owner's own expenses are approved as they submit them.
		for user in (ACCOUNTANT, OWNER):
			with self.subTest(user):
				frappe.set_user(user)
				receipt = self.upload()
				expense = self.new_expense(amount=46000, receipt=receipt).insert()
				expense.submit()
				self.assertEqual((expense.docstatus, expense.approval_status, expense.approved_by), (1, "Approved", user))

	def test_sec09_a_request_does_not_carry_a_forged_approval(self):
		expense = self.draft(46000)
		expense.approved_by, expense.rejection_reason = ACCOUNTANT, "<b>forged</b>"
		expense.request_approval()
		self.assertEqual(
			frappe.db.get_value("Expense", expense.name, ["approval_status", "approved_by", "rejection_reason"]),
			("Pending Approval", None, None),
		)

	def test_decision_goes_to_who_asked_for_approval(self):
		# A monthly draft is made by the scheduler, as Administrator; Sara asks for the approval.
		expense = self.new_expense(amount=46000, activity=AZARITA, treasury=AZARITA_CASH, receipt=self.upload()).insert()
		frappe.set_user(SARA)
		expense = frappe.get_doc("Expense", expense.name)
		expense.request_approval()
		self.assertEqual(expense.approval_requested_by, SARA)

		self.as_user(ACCOUNTANT, expense).approve()
		self.assertTrue(frappe.db.exists("Notification Log", {"document_name": expense.name, "for_user": SARA}))

	def test_rejection_reason_is_kept_as_typed(self):
		expense = self.draft(46000)
		expense.request_approval()
		self.as_user(ACCOUNTANT, expense).reject("المبلغ {0} غلط")
		self.assertEqual(frappe.db.get_value("Expense", expense.name, "rejection_reason"), "المبلغ {0} غلط")

	def test_changing_what_was_approved_needs_approval_again(self):
		for field, value in (
			("expense_category", self.water),
			("treasury", INSTAPAY),
			("posting_date", lambda expense: frappe.utils.add_days(expense.posting_date, -1)),
		):
			with self.subTest(field):
				expense = self.draft(46000)
				expense.request_approval()
				expense.set(field, value(expense) if callable(value) else value)
				expense.save()
				self.assertFalse(expense.approval_status)

	def test_a_request_sent_again_reaches_the_accountant(self):
		# The notification service skips one the approver already has; each request carries its own time.
		from unittest.mock import patch

		expense = self.draft(46000)
		expense.request_approval()
		expense.amount = 50000
		expense.save()
		with patch(
			"imed_erp.imederp.doctype.expense.expense.now_datetime",
			return_value=frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=5),
		):
			expense.request_approval()
		self.assertEqual(
			frappe.db.count("Notification Log", {"document_name": expense.name, "for_user": ACCOUNTANT, "type": "Alert"}), 2
		)

	def test_a_rejection_is_kept_in_the_history(self):
		from unittest.mock import patch

		expense = self.draft(46000)
		expense.request_approval()
		# Frappe keeps no change history while tests run; here it does, as on the site.
		with patch.object(frappe, "in_test", False):
			self.as_user(ACCOUNTANT, expense).reject("مش واضح")
		frappe.set_user("Administrator")
		versions = frappe.get_all("Version", filters={"ref_doctype": "Expense", "docname": expense.name}, pluck="data")
		self.assertTrue(any("Rejected" in data for data in versions))
