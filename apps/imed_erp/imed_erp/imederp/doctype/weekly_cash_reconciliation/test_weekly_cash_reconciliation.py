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
from frappe.utils import add_days, getdate, today

from imed_erp.imederp.doctype.treasury_close.test_treasury_close import (
	ACCOUNTANT, AZARITA, AZARITA_BOX, HALLS, HALLS_BOX, SARA, close, move,
)
from imed_erp.imederp.testing import fund_cash_boxes

IGNORE_TEST_RECORD_DEPENDENCIES = ["Account", "Cost Center", "Journal Entry", "User", "Treasury Close", "Cash Discrepancy", "Weekly Cash Reconciliation", "Cash Handover"]

START = add_days(today(), -6)


def review_week(week_start, business=None, note=None, submit=True):
	doc = frappe.get_doc(
		{"doctype": "Weekly Cash Reconciliation", "week_start": week_start, "business": business, "review_note": note}
	).insert()
	if submit:
		doc.submit()
	return doc.name


def any_week():
	"""Weeks of any seven days, whatever the site's Cash Close Settings say (rolled back with the test)."""
	frappe.db.set_single_value("Cash Close Settings", {"week_starts_on": None, "week_ends_on": None})


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
		any_week()

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

	# 1. An open discrepancy is carried, not counted again: the next close starts from the cash counted, and a later
	# week lists it apart from its own totals until it is settled.
	def test_an_open_discrepancy_is_carried_not_counted_twice(self):
		early = add_days(START, -7)
		short = closed(early, -40)
		nxt = close(0, add_days(START, 1))
		self.assertEqual((nxt.opening, nxt.difference), (short.counted, -nxt.expected))
		nxt.counted = nxt.expected
		nxt.submit()
		self.assertFalse(nxt.cash_discrepancy)
		week = frappe.get_doc("Weekly Cash Reconciliation", review_week(START, AZARITA, submit=False))
		self.assertEqual((week.total_shortage, week.unresolved, week.earlier_open), (0, 0, 1))
		self.assertIn(short.cash_discrepancy, week.earlier_open_list)
		self.assertRaisesRegex(frappe.ValidationError, "still open", week.submit)
		# Settled: no longer carried.
		from imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy import write_off

		frappe.set_user(ACCOUNTANT)
		write_off(short.cash_discrepancy, "Not found")
		frappe.set_user("Administrator")
		week.reload()
		week.save()
		self.assertEqual(week.earlier_open, 0)

	# 5. The reporting week's first day, once confirmed.
	def test_the_week_starts_on_the_day_set(self):
		settings = frappe.get_single("Cash Close Settings")
		settings.week_starts_on = None
		settings.save()
		review_week(START, AZARITA, submit=False)
		saturday = next(add_days(today(), -i) for i in range(7, 14) if getdate(add_days(today(), -i)).weekday() == 5)
		settings.week_starts_on = "Saturday"
		settings.save()
		self.assertRaisesRegex(frappe.ValidationError, "starts on Saturday", review_week, add_days(saturday, 1), HALLS, submit=False)
		week = frappe.get_doc("Weekly Cash Reconciliation", review_week(saturday, HALLS, submit=False))
		self.assertEqual(getdate(week.week_end).strftime("%A"), "Friday")

	def test_saturday_to_thursday_with_friday_off(self):
		frappe.set_user("Administrator")
		settings = frappe.get_single("Cash Close Settings")
		settings.week_starts_on, settings.week_ends_on = "Saturday", "Thursday"
		settings.save()
		saturday = next(add_days(today(), -i) for i in range(7, 14) if getdate(add_days(today(), -i)).weekday() == 5)
		friday = add_days(saturday, 6)
		on_friday = closed(friday, 0)
		week = frappe.get_doc("Weekly Cash Reconciliation", review_week(saturday, AZARITA, submit=False))
		self.assertEqual(getdate(week.week_end).strftime("%A"), "Thursday")
		# A close made on the Friday is still in its week; a Friday without one is not missing.
		self.assertIn(on_friday.name, [row.treasury_close for row in week.items])
		halls = frappe.get_doc("Weekly Cash Reconciliation", review_week(saturday, HALLS, submit=False))
		self.assertNotIn(frappe.format_value(friday, {"fieldtype": "Date"}), halls.missing_days)
		self.assertIn(frappe.format_value(add_days(saturday, 5), {"fieldtype": "Date"}), halls.missing_days)
