# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The accountant's weekly review (owner, 21 Oct 2026): every close of the week with its figures, the week's
# shortages and surpluses, what is still open, who was found responsible, the days not closed; once per week and
# business; the accountant's, not a branch manager's. Rolled back.
#
# Run:
#   bench --site frontend run-tests --doctype "Weekly Cash Reconciliation"

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from imed_erp.imederp.doctype.treasury_close.test_treasury_close import (
	ACCOUNTANT, AZARITA, AZARITA_BOX, HALLS, HALLS_BOX, SARA, close, move,
)
from imed_erp.imederp.testing import fund_cash_boxes

IGNORE_TEST_RECORD_DEPENDENCIES = ["Account", "Cost Center", "Journal Entry", "User", "Treasury Close", "Cash Discrepancy", "Weekly Cash Reconciliation"]

START = add_days(today(), -6)


def review_week(week_start, business=None, note=None, submit=True):
	doc = frappe.get_doc(
		{"doctype": "Weekly Cash Reconciliation", "week_start": week_start, "business": business, "review_note": note}
	).insert()
	if submit:
		doc.submit()
	return doc.name


def closed(day, off_by, treasury=AZARITA_BOX, business=AZARITA):
	doc = close(0, day, treasury, business)
	doc.counted = doc.expected + off_by
	doc.submit()
	return doc


class IntegrationTestWeeklyCashReconciliation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fund_cash_boxes()

	def setUp(self):
		frappe.db.savepoint("weekly")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="weekly")

	# 5. Several days and boxes in one week.
	def test_the_week_s_closes_and_totals(self):
		move(300, add_days(START, 1))
		first = closed(add_days(START, 1), -25)
		second = closed(add_days(START, 2), 0)
		third = closed(add_days(START, 3), 10)
		halls = closed(add_days(START, 2), -5, HALLS_BOX, HALLS)
		week = frappe.get_doc("Weekly Cash Reconciliation", review_week(START, submit=False))
		rows = {row.treasury_close: row for row in week.items}
		self.assertEqual(set(rows), {first.name, second.name, third.name, halls.name})
		self.assertEqual((rows[first.name].collections, rows[first.name].difference), (first.collections, -25))
		self.assertEqual(rows[second.name].opening, first.counted)
		self.assertEqual((week.total_shortage, week.total_surplus, week.unresolved), (30, 10, 3))
		self.assertEqual(rows[first.name].discrepancy_status, "Pending Investigation")
		# Azarita not closed on the first day; nor today, unless a close was made.
		self.assertIn(AZARITA_BOX, week.missing_days)

		# Open discrepancies need a note before the week is marked reviewed.
		self.assertRaisesRegex(frappe.ValidationError, "still open", week.submit)
		week.reload()
		week.review_note = "Azarita shortage under investigation"
		week.submit()
		self.assertEqual(week.reviewed_by, "Administrator")

		# One business only.
		azarita = frappe.get_doc("Weekly Cash Reconciliation", review_week(START, AZARITA, note="x", submit=False))
		self.assertEqual({row.business for row in azarita.items}, {AZARITA})

	def test_once_per_week_and_business(self):
		review_week(START, submit=False)
		self.assertRaisesRegex(frappe.ValidationError, "already reconciled", review_week, START, submit=False)
		review_week(START, AZARITA, submit=False)

	def test_an_empty_week(self):
		week = frappe.get_doc("Weekly Cash Reconciliation", review_week(add_days(START, -70), submit=False))
		self.assertEqual((len(week.items), week.total_shortage, week.unresolved), (0, 0, 0))

	# 6, 7. The accountant's only.
	def test_a_branch_manager_cannot_review(self):
		frappe.set_user(SARA)
		self.assertRaises(frappe.PermissionError, review_week, START, AZARITA, submit=False)
		frappe.set_user(ACCOUNTANT)
		review_week(START, AZARITA, note="ok")

	def test_a_draft_week_is_saved_after_one_of_its_closes_was_reopened(self):
		from imed_erp.imederp.doctype.treasury_close.treasury_close import reopen

		first = closed(add_days(START, 1), -10)
		week = frappe.get_doc("Weekly Cash Reconciliation", review_week(START, AZARITA, submit=False))
		frappe.set_user(ACCOUNTANT)
		draft = frappe.get_doc("Treasury Close", reopen(first.name, "Recount"))
		draft.counted = draft.expected
		draft.submit()
		frappe.set_user("Administrator")
		week.save()
		closes = [row.treasury_close for row in week.items]
		self.assertIn(draft.name, closes)
		self.assertNotIn(first.name, closes)
