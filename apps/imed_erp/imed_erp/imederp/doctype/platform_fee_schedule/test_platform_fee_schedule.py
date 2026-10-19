# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Platform fee tiers (APP-02, requirements v1.2): every count of students falls in exactly one tier, and the
# tiers in force on a date are the latest schedule from on or before it. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Platform Fee Schedule"

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.platform_fee_schedule.platform_fee_schedule import get_fee_per_student

IGNORE_TEST_RECORD_DEPENDENCIES = ["Platform Fee Schedule"]

# The owner's tiers. Tests use dates far ahead, so the site's own schedules are never the latest.
TIERS = [(1, 100, 250), (101, 500, 200), (501, None, 170)]
VALID_FROM = "2031-09-01"


def make_schedule(valid_from=VALID_FROM, tiers=TIERS, submit=True):
	if name := frappe.db.exists("Platform Fee Schedule", {"valid_from": valid_from, "docstatus": 1}):
		return name
	schedule = frappe.get_doc(
		{
			"doctype": "Platform Fee Schedule",
			"valid_from": valid_from,
			"tiers": [{"from_students": low, "to_students": high, "fee_per_student": fee} for low, high, fee in tiers],
		}
	)
	schedule.insert()
	if submit:
		schedule.submit()
	return schedule.name


class IntegrationTestPlatformFeeSchedule(IntegrationTestCase):
	def test_fee_by_number_of_students(self):
		make_schedule()
		for students, fee in ((1, 250), (100, 250), (101, 200), (300, 200), (500, 200), (501, 170), (2000, 170)):
			with self.subTest(students=students):
				self.assertEqual(get_fee_per_student(students, VALID_FROM), fee)
		# The definition of done: 300 students -> second tier -> 60,000.
		self.assertEqual(300 * get_fee_per_student(300, VALID_FROM), 60000)

	def test_tiers_in_force_on_a_date(self):
		make_schedule()
		make_schedule("2032-09-01", [(1, 100, 300), (101, None, 220)])
		self.assertEqual(get_fee_per_student(300, "2032-08-31"), 200)
		self.assertEqual(get_fee_per_student(300, "2032-09-01"), 220)
		self.assertIsNone(get_fee_per_student(300, "1990-01-01"))

	def test_a_draft_is_not_in_force(self):
		make_schedule("2033-09-01", [(1, None, 999)], submit=False)
		self.assertNotEqual(get_fee_per_student(10, "2033-09-01"), 999)

	def test_tiers_must_cover_every_count_once(self):
		for label, tiers in (
			("not from 1", [(2, 100, 250), (101, None, 200)]),
			("a gap", [(1, 100, 250), (102, None, 200)]),
			("an overlap", [(1, 100, 250), (100, None, 200)]),
			("open in the middle", [(1, None, 250), (101, None, 200)]),
			("closed at the end", [(1, 100, 250), (101, 500, 200)]),
			("to before from", [(1, 0, 250), (1, None, 200)]),
			("no fee", [(1, None, 0)]),
		):
			with self.subTest(label):
				self.assertRaises(frappe.ValidationError, make_schedule, "2034-01-01", tiers, False)

	def test_rows_are_put_in_order(self):
		name = make_schedule("2035-01-01", [(501, None, 170), (1, 100, 250), (101, 500, 200)])
		rows = frappe.get_doc("Platform Fee Schedule", name).tiers
		self.assertEqual([row.from_students for row in rows], [1, 101, 501])

	def test_one_schedule_per_date(self):
		make_schedule()
		twin = frappe.get_doc(
			{"doctype": "Platform Fee Schedule", "valid_from": VALID_FROM, "tiers": [{"from_students": 1, "fee_per_student": 99}]}
		)
		self.assertRaises(frappe.ValidationError, twin.insert)
