# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Runs against the real chart of accounts and cost centers made by setup/setup_coa.py and setup/setup_core.py.
# Every check compares balances before and after, so existing data on the site does not matter,
# and everything a test creates is rolled back when the tests finish.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.doctype.inter_business_transfer.test_inter_business_transfer

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from imed_erp.imederp.doctype.inter_business_transfer.inter_business_transfer import CURRENT_ACCOUNT

# The linked records already exist on the site; without this Frappe would generate its own
# "_Test ..." records for every linked doctype and commit them.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Academic Period",
	"Account",
	"Cost Center",
	"Inter Business Transfer",
	"Journal Entry",
	"User",
]

ABBR = "MMG"
LIBRARY = f"مكتبة الأزاريطة - {ABBR}"
CENTER = f"قاعات Imed - {ABBR}"
LIBRARY_CASH = f"خزينة مكتبة الأزاريطة - {ABBR}"
CENTER_CASH = f"خزينة سنتر Imed - {ABBR}"
CURRENT = f"{CURRENT_ACCOUNT} - {ABBR}"
BRANCH_USER = "test-branch-manager@imed.local"


def balance(account):
	"""Debit minus credit of all live GL entries on an account."""
	return flt(
		frappe.db.sql(
			"select sum(debit - credit) from `tabGL Entry` where account = %s and is_cancelled = 0", account
		)[0][0]
	)


def profit(cost_center):
	"""Income minus expenses booked to a business: what its P&L shows."""
	return flt(
		frappe.db.sql(
			"""select sum(gl.credit - gl.debit)
			from `tabGL Entry` gl join `tabAccount` acc on acc.name = gl.account
			where acc.root_type in ('Income', 'Expense') and gl.cost_center = %s and gl.is_cancelled = 0""",
			cost_center,
		)[0][0]
	)


class IntegrationTestInterBusinessTransfer(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.period = frappe.get_doc(
			{
				"doctype": "Academic Period",
				"period_name": "Test Term IBT",
				"period_type": "Term",
				"start_date": "2026-09-01",
				"end_date": "2027-08-31",
			}
		).insert().name

	def tearDown(self):
		frappe.set_user("Administrator")

	def new_transfer(self, **changes):
		"""An unsaved library-to-center transfer; pass fields to change the defaults."""
		return frappe.get_doc(
			{
				"doctype": "Inter Business Transfer",
				"posting_date": "2026-09-30",
				"from_business": LIBRARY,
				"from_treasury": LIBRARY_CASH,
				"to_business": CENTER,
				"to_treasury": CENTER_CASH,
				"amount": 10000,
				"reason": "Test transfer",
				"period": self.period,
				**changes,
			}
		)

	def make_transfer(self, amount=10000):
		return self.new_transfer(amount=amount).insert()

	def test_transfer_does_not_touch_pnl(self):
		# The task's acceptance test: 10,000 from the library to the center leaves the library's P&L as it was.
		library_profit, center_profit = profit(LIBRARY), profit(CENTER)
		library_cash, center_cash, current = balance(LIBRARY_CASH), balance(CENTER_CASH), balance(CURRENT)

		transfer = self.make_transfer(10000)
		transfer.submit()
		transfer.reload()

		self.assertEqual(transfer.status, "Sent")
		self.assertEqual(balance(LIBRARY_CASH), library_cash - 10000)
		self.assertEqual(balance(CURRENT), current + 10000, "The money waits in the current account")
		self.assertEqual(balance(CENTER_CASH), center_cash, "Nothing arrives before the receipt is confirmed")

		transfer.confirm_receipt()
		transfer.reload()

		self.assertEqual(transfer.status, "Received")
		self.assertEqual(transfer.received_by, "Administrator")
		self.assertEqual(balance(CENTER_CASH), center_cash + 10000)
		self.assertEqual(balance(CURRENT), current, "The current account is back to where it started")

		self.assertEqual(profit(LIBRARY), library_profit, "The library's P&L must not change")
		self.assertEqual(profit(CENTER), center_profit, "The center's P&L must not change")

	def test_cancel_reverses_everything(self):
		before = {account: balance(account) for account in (LIBRARY_CASH, CENTER_CASH, CURRENT)}

		transfer = self.make_transfer(2500)
		transfer.submit()
		transfer.confirm_receipt()
		transfer.reload()
		transfer.cancel()
		transfer.reload()

		self.assertEqual(transfer.status, "Cancelled")
		for account, amount in before.items():
			self.assertEqual(balance(account), amount, f"{account} is not back to its balance before the transfer")

	def test_receipt_cannot_be_confirmed_twice(self):
		transfer = self.make_transfer(100)
		transfer.submit()
		transfer.confirm_receipt()
		transfer.reload()

		self.assertRaises(frappe.ValidationError, transfer.confirm_receipt)

	def test_only_accounts_manager_confirms(self):
		if not frappe.db.exists("User", BRANCH_USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": BRANCH_USER,
					"first_name": "Test Branch Manager",
					"send_welcome_email": 0,
					"roles": [{"role": "Branch Manager"}],
				}
			).insert()

		transfer = self.make_transfer(100)
		transfer.submit()

		frappe.set_user(BRANCH_USER)
		self.assertRaises(frappe.PermissionError, transfer.confirm_receipt)

	def test_rejects_invalid_transfers(self):
		cases = {
			"zero amount": {"amount": 0},
			"same business": {"to_business": LIBRARY},
			"same treasury": {"to_treasury": LIBRARY_CASH},
			"group business": {"to_business": f"مكتبات 2Be Doctor - {ABBR}"},
			"expense account as treasury": {"to_treasury": f"حصة الأطباء - {ABBR}"},
		}
		for label, change in cases.items():
			with self.subTest(label):
				self.assertRaises(frappe.ValidationError, self.new_transfer(**change).insert)

	def test_manual_entry_on_current_account_blocked(self):
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": frappe.db.get_value("Account", CURRENT, "company"),
				"posting_date": "2026-09-30",
				"accounts": [
					{"account": CURRENT, "debit_in_account_currency": 100, "cost_center": LIBRARY},
					{"account": LIBRARY_CASH, "credit_in_account_currency": 100, "cost_center": LIBRARY},
				],
			}
		)
		self.assertRaises(frappe.ValidationError, entry.insert)
