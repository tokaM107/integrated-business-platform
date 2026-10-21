# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The daily close of a branch's cash box (ACC-03; owner, 21 Oct 2026): opening from the last count, the movements by
# kind, the shortage or surplus; once a day per box and in order; the branch manager closes her own box only; nothing
# is posted; a difference opens a Cash Discrepancy; reopening is the owner's and the accountant's, with a reason,
# and marks what it changes. Rolled back.
#
# Run:
#   bench --site frontend run-tests --doctype "Treasury Close"

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement
from imed_erp.imederp.doctype.treasury_close.treasury_close import reopen
from imed_erp.imederp.testing import fund_cash_boxes

IGNORE_TEST_RECORD_DEPENDENCIES = ["Account", "Cost Center", "Journal Entry", "User", "Treasury Close", "Cash Discrepancy", "Weekly Cash Reconciliation"]

COMPANY = "Mohamed Mamdouh group"
AZARITA = "مكتبة الأزاريطة - MMG"
AZARITA_BOX = "خزينة مكتبة الأزاريطة - MMG"
MAWASAH = "مكتبة المواساة - MMG"
MAWASAH_BOX = "خزينة مكتبة المواساة - MMG"
HALLS = "قاعات Imed - MMG"
HALLS_BOX = "خزينة سنتر Imed - MMG"
INSTAPAY = "محفظة InstaPay - MMG"
SARA = "sara@imed.local"
ACCOUNTANT = "accountant@imed.local"
OWNER = "owner@imed.local"

# Three days back, two, one: closes are made in order.
DAY1, DAY2, DAY3 = add_days(today(), -3), add_days(today(), -2), add_days(today(), -1)


def capital():
	return frappe.get_all("Account", filters={"company": COMPANY, "root_type": "Equity", "is_group": 0}, pluck="name", limit=1)[0]


def move(amount, date=None, box=AZARITA_BOX, business=AZARITA, submit=True):
	"""Cash into (or, below zero, out of) the box, against capital: a collection or another payment."""
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"company": COMPANY,
			"posting_date": date or today(),
			"accounts": [
				{"account": box, "debit_in_account_currency": max(amount, 0), "credit_in_account_currency": max(-amount, 0), "cost_center": business},
				{"account": capital(), "debit_in_account_currency": max(-amount, 0), "credit_in_account_currency": max(amount, 0), "cost_center": business},
			],
		}
	)
	entry.flags.ignore_permissions = True
	entry.insert()
	if submit:
		entry.submit()
	return entry


def close(counted, date=None, treasury=AZARITA_BOX, business=AZARITA, user=None, submit=False, **fields):
	if user:
		frappe.set_user(user)
	try:
		doc = frappe.get_doc(
			{"doctype": "Treasury Close", "treasury": treasury, "business": business, "close_date": date or today(), "counted": counted, **fields}
		).insert()
		if submit:
			doc.submit()
		return doc
	finally:
		frappe.set_user("Administrator")


def balance_before(date, box=AZARITA_BOX):
	return flt(
		frappe.db.sql(
			"select sum(debit - credit) from `tabGL Entry` where account=%s and is_cancelled=0 and posting_date < %s", (box, date)
		)[0][0],
		2,
	)


def gl_rows():
	return frappe.db.count("GL Entry")


class IntegrationTestTreasuryClose(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fund_cash_boxes()

	def setUp(self):
		frappe.db.savepoint("treasury_close")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="treasury_close")

	def refused(self, error, pattern, fn, *args, **kwargs):
		"""Refused, and what it wrote undone, as a failed request would be."""
		frappe.db.savepoint("refused")
		try:
			with self.assertRaisesRegex(error, pattern):
				fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")
			frappe.db.rollback(save_point="refused")

	def transfer_out(self, amount, date):
		term = frappe.get_all("Academic Period", filters={"period_type": "Term", "is_closed": 0}, pluck="name", limit=1)[0]
		return frappe.get_doc(
			{
				"doctype": "Inter Business Transfer", "posting_date": date, "from_business": AZARITA, "from_treasury": AZARITA_BOX,
				"to_business": HALLS, "to_treasury": HALLS_BOX, "amount": amount, "reason": "_Test", "period": term,
			}
		).insert().submit()

	def payout(self, amount, date):
		agreement = make_agreement("Books")
		frappe.get_doc({"doctype": "Doctor Ledger Entry", "agreement": agreement, "entry_type": "Accrual", "amount": 1000, "entry_date": date}).insert().submit()
		frappe.get_doc(
			{"doctype": "Doctor Ledger Entry", "agreement": agreement, "entry_type": "Payout", "amount": amount, "entry_date": date, "treasury": AZARITA_BOX}
		).insert().submit()

	# 1. A correct close: the figures by kind.
	def test_the_day_by_kind_and_the_expected_closing(self):
		opening = balance_before(DAY1)
		move(1000, DAY1)
		move(-80, DAY1)
		self.transfer_out(150, DAY1)
		self.payout(200, DAY1)
		doc = close(0, DAY1)
		self.assertEqual(
			(doc.opening, doc.collections, doc.transfers_in, doc.expenses_and_payouts, doc.transfers_out, doc.other_out),
			(opening, 1000, 0, 200, 150, 80),
		)
		self.assertEqual((doc.money_in, doc.money_out), (1000, 430))
		self.assertEqual(doc.expected, flt(opening + 1000 - 430, 2))
		self.assertEqual(doc.book_balance, doc.expected)
		self.assertEqual(doc.difference, -doc.expected)

	# 2. Counted as expected: no discrepancy, nothing posted.
	def test_no_difference_opens_nothing_and_posts_nothing(self):
		move(500, DAY1)
		before = gl_rows()
		doc = close(0, DAY1)
		doc.counted = doc.expected
		doc.submit()
		self.assertEqual(doc.difference, 0)
		self.assertFalse(doc.cash_discrepancy)
		self.assertEqual(gl_rows(), before)
		self.assertEqual((doc.counted_by, bool(doc.closed_on)), ("Administrator", True))

	# 3. A shortage: a discrepancy to investigate, nobody charged, nothing posted.
	def test_a_shortage_opens_an_investigation_and_charges_nobody(self):
		before = gl_rows()
		doc = close(0, DAY1, user=SARA, shift="Evening", note="Counted twice")
		doc.counted = doc.expected - 75
		frappe.set_user(SARA)
		doc.submit()
		frappe.set_user("Administrator")
		self.assertEqual(doc.difference, -75)
		discrepancy = frappe.get_doc("Cash Discrepancy", doc.cash_discrepancy)
		self.assertEqual(
			(discrepancy.kind, discrepancy.amount, discrepancy.status, discrepancy.shift, discrepancy.business),
			("Shortage", 75, "Pending Investigation", "Evening", AZARITA),
		)
		# Sara closed it, so she is listed; nobody is found responsible and nothing is to be recovered.
		self.assertEqual([(r.user, r.responsible, flt(r.recovery_amount)) for r in discrepancy.employees], [(SARA, 0, 0)])
		self.assertFalse(discrepancy.payroll_status)
		self.assertEqual(gl_rows(), before)

	# 4. A surplus: kept for review, never revenue.
	def test_a_surplus_waits_for_review_and_is_not_revenue(self):
		before = gl_rows()
		doc = close(0, DAY1)
		doc.counted = doc.expected + 40
		doc.submit()
		discrepancy = frappe.get_doc("Cash Discrepancy", doc.cash_discrepancy)
		self.assertEqual((discrepancy.kind, discrepancy.amount, discrepancy.status), ("Surplus", 40, "Pending Review"))
		self.assertEqual(gl_rows(), before)

	# The next close starts from the cash counted, whatever the books said.
	def test_the_next_close_opens_with_the_cash_counted(self):
		first = close(0, DAY1)
		counted = first.expected - 30
		first.counted = counted
		first.save()
		first.submit()
		move(200, DAY2)
		second = close(0, DAY2)
		self.assertEqual((second.last_close, second.opening, second.collections), (first.name, counted, 200))
		self.assertEqual(second.expected, flt(counted + 200, 2))
		# The books still hold the 30: the close changed no ledger line.
		self.assertEqual(second.book_balance, flt(second.expected + 30, 2))

	def test_days_not_closed_are_in_the_next_close(self):
		first = close(0, DAY1)
		first.counted = first.expected
		first.submit()
		move(100, DAY2)
		move(50, DAY3)
		third = close(0, DAY3)
		self.assertEqual((third.collections, third.expected), (150, flt(first.counted + 150, 2)))

	# 9. Once a day per box, and in order.
	def test_once_a_day_per_box_and_in_order(self):
		close(0, DAY2)
		self.refused(frappe.ValidationError, "already closed", close, 0, DAY2)
		close(0, DAY1)
		close(0, DAY2, treasury=HALLS_BOX, business=HALLS)
		submitted = close(0, DAY3, treasury=HALLS_BOX, business=HALLS, submit=True)
		self.assertTrue(submitted.name)
		self.refused(frappe.ValidationError, "was already closed later", close, 0, DAY1, HALLS_BOX, HALLS)

	def test_a_wallet_is_not_a_cash_box(self):
		self.refused(frappe.ValidationError, "is not a cash box", close, 0, DAY1, INSTAPAY)

	def test_not_ahead_of_today_and_kept_once_submitted(self):
		self.refused(frappe.ValidationError, "after today", close, 0, add_days(today(), 1))
		doc = close(0, DAY1, submit=True)
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Treasury Close", doc.name)

	# 6. Branches kept apart.
	def test_sara_closes_her_own_box_only(self):
		close(0, DAY1, user=SARA)
		self.refused(frappe.ValidationError, "is not a treasury of", close, 0, DAY1, MAWASAH_BOX, AZARITA, SARA)
		self.refused(frappe.PermissionError, "", close, 0, DAY1, MAWASAH_BOX, MAWASAH, SARA)
		mawasah = close(0, DAY1, treasury=MAWASAH_BOX, business=MAWASAH, submit=True)
		self.assertFalse(frappe.has_permission("Treasury Close", "read", mawasah.name, user=SARA))

	# 10. Two closes of one box at once wait for each other: the box is locked before the check.
	def test_the_box_is_locked_before_the_day_is_checked(self):
		reads = []
		original = frappe.db.get_value

		def spy(doctype, name=None, *args, **kwargs):
			if doctype == "Account" and kwargs.get("for_update"):
				reads.append(name)
			return original(doctype, name, *args, **kwargs)

		with patch("imed_erp.imederp.doctype.treasury_close.treasury_close.frappe.db.get_value", side_effect=spy):
			close(0, DAY1)
		self.assertIn(AZARITA_BOX, reads)


class IntegrationTestReopening(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fund_cash_boxes()

	def setUp(self):
		frappe.db.savepoint("reopening")
		from imed_erp.imederp.doctype.weekly_cash_reconciliation.test_weekly_cash_reconciliation import any_week

		any_week()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="reopening")

	def refused(self, error, pattern, fn, *args, **kwargs):
		frappe.db.savepoint("refused")
		try:
			with self.assertRaisesRegex(error, pattern):
				fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")
			frappe.db.rollback(save_point="refused")

	def as_user(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	# 7. A branch manager can neither reopen nor cancel.
	def test_a_branch_manager_cannot_reopen(self):
		doc = close(0, DAY1, user=SARA, submit=True)
		self.refused(frappe.PermissionError, "", self.as_user, SARA, reopen, doc.name, "wrong count")
		self.refused(frappe.PermissionError, "", self.as_user, SARA, lambda: frappe.get_doc("Treasury Close", doc.name).cancel())

	# 8. With a reason, by the accountant or the owner; the original kept; what it changes marked.
	def test_reopening_needs_a_reason_and_keeps_the_original(self):
		first = close(0, DAY1, user=SARA)
		first.counted = first.expected - 20
		self.as_user(SARA, first.submit)
		later = close(0, DAY2, submit=True)
		from imed_erp.imederp.doctype.weekly_cash_reconciliation.test_weekly_cash_reconciliation import review_week

		week = review_week(DAY1, note="checked")
		self.refused(frappe.ValidationError, "needs a reason", self.as_user, ACCOUNTANT, reopen, first.name, "  <b></b> ")
		self.refused(frappe.ValidationError, "needs a reason", self.as_user, ACCOUNTANT, lambda: frappe.get_doc("Treasury Close", first.name).cancel())
		before = frappe.db.count("GL Entry")

		draft = self.as_user(ACCOUNTANT, reopen, first.name, "Found 20 in the drawer")
		original = frappe.get_doc("Treasury Close", first.name)
		self.assertEqual(
			(original.docstatus, original.reopen_reason, original.reopened_by, original.counted),
			(2, "Found 20 in the drawer", ACCOUNTANT, first.counted),
		)
		self.assertEqual(frappe.db.get_value("Cash Discrepancy", first.cash_discrepancy, "status"), "Withdrawn")
		self.assertTrue(frappe.db.get_value("Treasury Close", later.name, "needs_review"))
		self.assertIn(first.name, frappe.db.get_value("Treasury Close", later.name, "review_note"))
		self.assertTrue(frappe.db.get_value("Weekly Cash Reconciliation", week, "needs_review"))
		# No entry was posted or reversed.
		self.assertEqual(frappe.db.count("GL Entry"), before)

		# The correction: amended in place, counted right, no discrepancy.
		amended = frappe.get_doc("Treasury Close", draft)
		self.assertEqual((amended.amended_from, amended.docstatus), (first.name, 0))
		amended.counted = amended.expected
		self.as_user(ACCOUNTANT, amended.submit)
		self.assertFalse(amended.cash_discrepancy)

		# 16. The week, reviewed again, shows the corrected close only.
		from imed_erp.imederp.doctype.weekly_cash_reconciliation.weekly_cash_reconciliation import WeeklyCashReconciliation

		# Amended as the form amends it: the closes are read again, not copied.
		again = frappe.copy_doc(frappe.get_doc("Weekly Cash Reconciliation", week), ignore_no_copy=False)
		again.docstatus = 0
		self.as_user(ACCOUNTANT, frappe.get_doc("Weekly Cash Reconciliation", week).cancel)
		again.amended_from = week
		again.insert()
		closes = [row.treasury_close for row in again.items if row.treasury == AZARITA_BOX]
		self.assertIn(amended.name, closes)
		self.assertNotIn(first.name, closes)
		self.assertIsInstance(again, WeeklyCashReconciliation)

	def test_the_owner_reopens_too(self):
		doc = close(0, DAY1, submit=True)
		self.assertTrue(self.as_user(OWNER, reopen, doc.name, "Recount"))

	def test_not_reopened_once_its_shortage_was_settled_in_the_books(self):
		from imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy import post_adjustment, write_off

		doc = close(0, DAY1, submit=True)
		self.as_user(ACCOUNTANT, write_off, doc.cash_discrepancy, "Not found")
		self.as_user(ACCOUNTANT, post_adjustment, doc.cash_discrepancy)
		self.refused(frappe.ValidationError, "already adjusted", self.as_user, ACCOUNTANT, reopen, doc.name, "Recount")

	# 15. A day already closed: the branch manager cannot change it; the accountant's entry is marked.
	def test_an_entry_dated_into_a_closed_day(self):
		doc = close(0, DAY2, submit=True)
		entry = move(10, DAY1, submit=False)
		entry.flags.ignore_permissions = True
		self.refused(frappe.ValidationError, "is already closed for", self.as_user, SARA, entry.submit)
		# Today is not closed: fine for her.
		today_entry = move(10, today(), submit=False)
		today_entry.flags.ignore_permissions = True
		self.as_user(SARA, today_entry.submit)
		self.assertFalse(frappe.db.get_value("Treasury Close", doc.name, "needs_review"))
		# The accountant may; the close is marked, its figures kept as they were.
		entry.reload()
		self.as_user(ACCOUNTANT, entry.submit)
		self.assertTrue(frappe.db.get_value("Treasury Close", doc.name, "needs_review"))
		self.assertEqual(frappe.db.get_value("Treasury Close", doc.name, "expected"), doc.expected)
