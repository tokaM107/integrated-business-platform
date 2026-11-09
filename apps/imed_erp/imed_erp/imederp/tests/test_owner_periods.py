# Copyright (c) 2026, toka mohamed and contributors
# See license.txt

# The Owner Dashboard by period (imederp/owner_periods.py; owner, 5 Nov 2026): today, the week from Saturday, the
# month from the 1st; each business on its card.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_owner_periods

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp import owner_periods


class IntegrationTestOwnerPeriods(IntegrationTestCase):
	def test_today_then_the_week_from_saturday_then_the_month(self):
		data = owner_periods.periods("2026-11-05")  # a Thursday
		self.assertEqual([p["key"] for p in data["periods"]], ["today", "week", "month"])
		spans = {p["key"]: (str(p["from"]), str(p["to"])) for p in data["periods"]}
		self.assertEqual(spans, {"today": ("2026-11-05", "2026-11-05"), "week": ("2026-10-31", "2026-11-05"), "month": ("2026-11-01", "2026-11-05")})
		# A Saturday is the first day of its own week.
		week = owner_periods.periods("2026-11-07")["periods"][1]
		self.assertEqual(str(week["from"]), "2026-11-07")
		for p in data["periods"]:
			self.assertEqual([b["key"] for b in p["businesses"]], ["studio", "halls", "libraries", "app"])

	def test_a_hall_booking_is_counted_in_its_day_week_and_month(self):
		from imed_erp.imederp.tests.test_sparkle_sync import FakeSparkle, IntegrationTestSparkleSync

		case = IntegrationTestSparkleSync("test_a_hall_not_mapped_is_noted_and_skipped")
		case.setUp()
		try:
			today = frappe.utils.today()
			before = {p["key"]: p["businesses"][1]["activity"]["bookings"] for p in owner_periods.periods(today)["periods"]}
			case.x = FakeSparkle()
			case.x.booking(day=today, start="20:00", end="22:00", status="confirmed", total=700)
			case.sync()
			after = {p["key"]: p["businesses"][1]["activity"] for p in owner_periods.periods(today)["periods"]}
			for key in ("today", "week", "month"):
				self.assertEqual(after[key]["bookings"], before[key] + 1, key)
			self.assertGreaterEqual(after["today"]["value"], 700)
		finally:
			case.tearDown()

	def test_only_the_owner_sees_them(self):
		frappe.set_user("nour@imed.local")
		try:
			self.assertRaises(frappe.PermissionError, owner_periods.get_periods)
		finally:
			frappe.set_user("Administrator")

	def test_the_supplies_show_what_is_left_its_arrow_and_how_long_it_lasts(self):
		"""Paper in boxes; a library's finished box lowers it and counts as the week's use."""
		from imed_erp.imederp.tests.test_library_desk import ACCOUNT, IntegrationTestLibraryDesk
		from imed_erp.imederp import library_desk as desk

		case = IntegrationTestLibraryDesk("test_paper_is_counted_and_taken_off_in_boxes")
		case.setUp()
		try:
			before = next(s for s in owner_periods.stock() if s["item_code"] == "A4-PAPER")
			frappe.set_user(ACCOUNT)
			desk.count({"A4-PAPER": flt_box(before) + 3})
			desk.used_up("A4-PAPER", 1)
			frappe.set_user("Administrator")
			after = next(s for s in owner_periods.stock() if s["item_code"] == "A4-PAPER")
			self.assertEqual(after["unit"], "كرتونة")
			self.assertAlmostEqual(after["qty"], flt_box(before) + 2, places=1)
			self.assertGreaterEqual(after["used_week"], before["used_week"] + 1)
			self.assertIsNotNone(after["days_left"])
			self.assertTrue(any(s["store"] for s in after["stores"]))
		finally:
			case.tearDown()

	def test_the_cash_boxes_are_listed_largest_first(self):
		rows = owner_periods.boxes()
		self.assertEqual([r["balance"] for r in rows], sorted((r["balance"] for r in rows), reverse=True))
		self.assertTrue(all(" - " not in r["name"] for r in rows))


def flt_box(row):
	return round(row["qty"], 2)


class IntegrationTestOwnerPeriodShapes(IntegrationTestCase):
	def test_the_week_is_drawn_day_by_day_and_the_month_against_last_month(self):
		data = owner_periods.periods("2026-11-09")  # a Monday
		week, month = data["periods"][1], data["periods"][2]
		self.assertEqual([str(d) for d in week["days"]["dates"]][0], "2026-11-07")
		self.assertEqual(len(week["days"]["dates"]), 7)
		for key in ("studio", "halls", "libraries", "app"):
			self.assertEqual(len(week["days"][key]), 7)
		# The same stretch of last month: the 1st to the 9th of October.
		self.assertEqual((str(month["previous_from"]), str(month["previous_to"])), ("2026-10-01", "2026-10-09"))
		for b in month["businesses"]:
			self.assertIn("main", b)
			self.assertIn("previous", b)
		# The 31st against a shorter month: its last day.
		march = owner_periods.periods("2027-03-31")["periods"][2]
		self.assertEqual(str(march["previous_to"]), "2027-02-28")

	def test_tomorrows_bookings_list_the_halls_and_the_studio_apart(self):
		from imed_erp.imederp.tests.test_sparkle_sync import FakeSparkle, IntegrationTestSparkleSync

		case = IntegrationTestSparkleSync("test_a_hall_not_mapped_is_noted_and_skipped")
		case.setUp()
		try:
			tomorrow = frappe.utils.add_days(frappe.utils.today(), 1)
			case.x = FakeSparkle()
			case.x.booking(day=tomorrow, start="09:00", end="11:00", status="confirmed", full_name="_Test Tomorrow Renter")
			case.sync()
			listed = owner_periods.periods()["tomorrow"]
			self.assertEqual(str(listed["date"]), tomorrow)
			mine = [r for r in listed["halls"] if r.from_time == "09:00" and r.resource.startswith("_Test Sparkle Hall")]
			self.assertEqual(len(mine), 1)
			self.assertTrue(all(r.resource_type == "Studio Service" for r in listed["studio"]))
		finally:
			case.tearDown()
