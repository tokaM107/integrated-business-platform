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
			before = paper_in(owner_periods.stock())
			frappe.set_user(ACCOUNT)
			desk.count({"A4-PAPER": flt_box(before) + 3})
			desk.used_up("A4-PAPER", 1)
			frappe.set_user("Administrator")
			after = paper_in(owner_periods.stock())
			self.assertEqual(after["unit"], "كرتونة")
			self.assertAlmostEqual(after["qty"], flt_box(before) + 2, places=1)
			self.assertGreaterEqual(after["used_week"], before["used_week"] + 1)
			self.assertIsNotNone(after["days_left"])
		finally:
			case.tearDown()

	def test_the_cash_boxes_are_listed_largest_first(self):
		rows = owner_periods.boxes()
		self.assertEqual([r["balance"] for r in rows], sorted((r["balance"] for r in rows), reverse=True))
		self.assertTrue(all(" - " not in r["name"] for r in rows))


def paper_in(stores):
	"""The paper of the test library's store (Mawasah's)."""
	from imed_erp.imederp.tests.test_library_desk import STORE

	return next(r for st in stores if st["store"] == STORE for r in st["items"] if r["item_code"] == "A4-PAPER")


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


class IntegrationTestOwnerStockByStore(IntegrationTestCase):
	def test_each_library_store_apart_the_epson_colours_and_the_requests(self):
		from imed_erp.imederp import library_desk as desk
		from imed_erp.imederp.tests.test_library_desk import ACCOUNT, INK, LIBRARY, STORE, IntegrationTestLibraryDesk

		case = IntegrationTestLibraryDesk("test_paper_is_counted_and_taken_off_in_boxes")
		case.setUp()
		try:
			# An Epson colour of the test: two counted, one finished this month.
			colour = "INK-EPSON-BK"
			# The library's Epson inks need its Epson machine.
			if not frappe.db.exists("Printing Machine", {"cost_center": LIBRARY, "machine_type": "Epson", "disabled": 0}):
				frappe.get_doc({"doctype": "Printing Machine", "machine_name": "_Test Epson", "machine_type": "Epson", "cost_center": LIBRARY, "warehouse": STORE}).insert()
			if not frappe.db.exists("Item", colour):
				frappe.get_doc({"doctype": "Item", "item_code": colour, "item_name": "حبر إبسون أسود", "item_group": "أحبار", "stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": 375}).insert()
			frappe.set_user(ACCOUNT)
			desk.count({colour: 2, INK: 3})
			desk.used_up(colour, 1)
			asked = desk.ask_for(INK, 2)["request"]
			frappe.set_user("Administrator")
			stores = {s["store"]: s for s in owner_periods.stock()}
			self.assertIn(STORE, stores)
			mine = stores[STORE]
			black = next(c for c in mine["epson"] if c["item_code"] == colour)
			self.assertEqual((black["qty"], black["finished_month"]), (1, 1))
			self.assertNotIn(colour, [r["item_code"] for r in mine["items"]])
			ink = next(r for r in mine["items"] if r["item_code"] == INK)
			self.assertEqual((ink["qty"], ink["counted"]), (3, 1))
			self.assertIn(asked, [r.name for r in owner_periods.requests()])
		finally:
			case.tearDown()

	def test_a_library_without_an_epson_machine_has_no_epson_inks(self):
		"""The owner, 9 Nov 2026: Azarita has no Epson inks, both libraries have Riso. An ink is a library's only
		when it has a machine of that kind in service."""
		from imed_erp.imederp import library_desk as desk
		from imed_erp.imederp.tests.test_library_desk import LIBRARY, STORE

		for code, name in (("INK-EPSON-BK", "حبر إبسون أسود"), ("INK-RISO", "حبر ريزو (إزازة)")):
			if not frappe.db.exists("Item", code):
				frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": "أحبار", "stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": 100}).insert()
		for kind in ("Epson", "Riso"):
			if not frappe.db.exists("Printing Machine", {"cost_center": LIBRARY, "machine_type": kind, "disabled": 0}):
				frappe.get_doc({"doctype": "Printing Machine", "machine_name": f"_Test {kind}", "machine_type": kind, "cost_center": LIBRARY, "warehouse": STORE}).insert()
		codes = lambda: {i.name for i in desk.supply_items(LIBRARY)}
		shown = lambda: {r["item_code"] for st in owner_periods.stock() if st["store"] == STORE for r in st["items"] + st["epson"]}
		self.assertIn("INK-EPSON-BK", codes())
		self.assertIn("INK-EPSON-BK", shown())
		# No Epson in service: the Epson inks go, the Riso stays.
		for name in frappe.get_all("Printing Machine", filters={"cost_center": LIBRARY, "machine_type": "Epson"}, pluck="name"):
			frappe.db.set_value("Printing Machine", name, "disabled", 1)
		self.assertNotIn("INK-EPSON-BK", codes())
		self.assertNotIn("INK-EPSON-BK", shown())
		self.assertIn("INK-RISO", codes())
		self.assertIn("INK-RISO", shown())
