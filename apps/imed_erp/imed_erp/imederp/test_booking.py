# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Bookable resources (HAL-01) and bookings (HAL-02, STU-01, STU-08, STU-14): checks, overlaps, statuses, source and
# import. Real cost centers and users; rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_booking

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from imed_erp.imederp.booking_import import import_bookings

# A test module outside a doctype folder builds no "_Test ..." records; keep it here, not under a doctype.
HALLS = "قاعات Imed - MMG"
STUDIO = "استوديو X - MMG"
NOUR, GILAN, HR = "nour@imed.local", "gilan@imed.local", "hr@imed.local"
DAY = add_days(today(), 7)
PAST = add_days(today(), -3)
PHONE = "01055554444"
HALL_ITEM, STUDIO_ITEM = "_TEST-BK-HALL-HOUR", "_TEST-BK-STUDIO-HOUR"


def patch_user_permissions(permissions):
	from unittest.mock import patch

	return patch("frappe.permissions.get_user_permissions", return_value=permissions)


class IntegrationTestBooking(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Bookings entered here are priced (booking_pricing.py): test service items with their prices.
		for item, price in ((HALL_ITEM, 250), (STUDIO_ITEM, 625)):
			if not frappe.db.exists("Item", item):
				frappe.get_doc({"doctype": "Item", "item_code": item, "item_name": item, "item_group": "الخدمات", "stock_uom": "Nos", "is_stock_item": 0}).insert()
			frappe.get_doc({"doctype": "Item Price", "item_code": item, "price_list": "Standard Selling", "price_list_rate": price}).insert()
		cls.hall = cls.resource("_Test Hall 1", "Hall", HALLS, capacity=40, item=HALL_ITEM)
		cls.hall2 = cls.resource("_Test Hall 2", "Hall", HALLS, capacity=20, item=HALL_ITEM)
		cls.podcast = cls.resource("_Test Podcast", "Studio Service", STUDIO, item=STUDIO_ITEM)
		cls.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test Booking Customer",
				"customer_type": "Individual",
				"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"mobile_no": PHONE,
			}
		).insert().name

	@staticmethod
	def resource(name, resource_type, cost_center, **values):
		return frappe.get_doc(
			{"doctype": "Booking Resource", "resource_name": name, "resource_type": resource_type, "cost_center": cost_center, **values}
		).insert().name

	def setUp(self):
		frappe.db.savepoint("booking_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="booking_test")

	def book(self, resource=None, start="10:00", end="12:00", date=DAY, user="Administrator", **values):
		resource = resource or self.hall
		hall = frappe.db.get_value("Booking Resource", resource, "resource_type") == "Hall"
		frappe.set_user(user)
		try:
			return frappe.get_doc(
				{
					"doctype": "Booking",
					"resource": resource,
					"customer": self.customer,
					"booking_date": date,
					"from_time": start,
					"to_time": end,
					**({"activity": "Anatomy lecture", "responsible_name": "د. أحمد", "responsible_phone": "01112223333", "rental_model": "Fixed Rent"} if hall else {}),
					**values,
				}
			).insert()
		finally:
			frappe.set_user("Administrator")

	# ---------- HAL-01: resources ----------

	def test_a_resource_is_made_and_edited(self):
		hall = frappe.get_doc("Booking Resource", self.hall)
		self.assertEqual((hall.resource_type, hall.capacity, hall.cost_center, hall.item), ("Hall", 40, HALLS, HALL_ITEM))
		hall.capacity = 45
		hall.equipment = "شاشة، صوت"
		hall.save()
		self.assertEqual(frappe.db.get_value("Booking Resource", self.hall, "capacity"), 45)

	def test_a_resource_is_checked(self):
		self.assertRaises(frappe.ValidationError, self.resource, "_Test No Capacity", "Hall", HALLS)
		self.assertRaises(frappe.ValidationError, self.resource, "_Test Group", "Studio Service", "سنتر Imed - MMG")
		self.assertRaises(frappe.ValidationError, self.resource, "_Test Stock", "Studio Service", STUDIO, item="A4-PAPER")
		self.assertTrue(self.resource("_Test Reels", "Studio Service", STUDIO))  # a service has no capacity

	# ---------- HAL-02: bookings ----------

	def test_a_booking_is_made_and_read_back(self):
		name = self.book().name
		booking = frappe.get_doc("Booking", name)
		self.assertEqual(
			(booking.hours, booking.total_amount, booking.outstanding_amount, booking.status, booking.source, booking.cost_center, booking.resource_type),
			(2, 500, 500, "Tentative", "Manual", HALLS, "Hall"),
		)
		self.assertEqual(booking.responsible_name, "د. أحمد")

	def test_required_values_and_times(self):
		self.assertRaises(frappe.MandatoryError, self.book, customer=None)
		self.assertRaisesRegex(frappe.ValidationError, "not after it starts", self.book, start="12:00", end="10:00")
		self.assertRaisesRegex(frappe.ValidationError, "not after it starts", self.book, start="10:00", end="10:00")
		for field in ("activity", "responsible_name", "responsible_phone"):
			self.assertRaises(frappe.ValidationError, self.book, **{field: ""})
		self.assertRaisesRegex(frappe.ValidationError, "not a valid phone", self.book, responsible_phone="123")
		# A studio service needs none of the hall's details.
		self.assertEqual(self.book(self.podcast).hours, 2)

	def test_amounts(self):
		"""A manual booking's amounts are worked out (test_booking_pricing.py); typed ones are not taken, and nothing
		is posted until a payment or the booking is completed."""
		booking = self.book(total_amount=100, paid_amount=150)
		self.assertEqual((booking.total_amount, booking.paid_amount, booking.outstanding_amount), (500, 0, 500))
		booking.paid_amount = 40
		booking.save()
		self.assertEqual((booking.paid_amount, booking.outstanding_amount), (0, 500))
		self.assertFalse(frappe.db.exists("GL Entry", {"against_voucher": booking.name}))

	# ---------- Overlaps ----------

	def test_overlapping_bookings_are_refused(self):
		first = self.book(start="10:00", end="12:00")
		self.assertRaisesRegex(frappe.ValidationError, "already booked", self.book, start="10:00", end="12:00")
		self.assertRaisesRegex(frappe.ValidationError, "already booked", self.book, start="11:00", end="13:00")
		self.assertRaisesRegex(frappe.ValidationError, "already booked", self.book, start="09:00", end="10:30")
		self.assertRaisesRegex(frappe.ValidationError, "already booked", self.book, start="10:30", end="11:30")
		# Ending when the next starts, another resource, another day: free.
		self.book(start="12:00", end="14:00")
		self.book(start="08:00", end="10:00")
		self.book(self.hall2, start="10:00", end="12:00")
		self.book(date=add_days(DAY, 1), start="10:00", end="12:00")
		# Saving a booking again does not clash with itself.
		first.reload()
		first.notes = "ok"
		first.save()

	def test_two_saves_at_the_same_moment_are_checked_one_after_the_other(self):
		"""What makes the overlap check hold for two people saving at once (booking.check_overlap): every booking that
		holds time writes its resource's row, and MariaDB refuses the second writer whose row changed meanwhile. That
		refusal needs innodb_snapshot_isolation, MariaDB 11.8's default; if it is ever turned off, this fails."""
		self.assertEqual(frappe.db.sql("select @@innodb_snapshot_isolation")[0][0], 1)
		before = frappe.db.get_value("Booking Resource", self.hall, "bookings_saved") or 0
		self.book(start="15:00", end="16:00")
		self.assertEqual(frappe.db.get_value("Booking Resource", self.hall, "bookings_saved"), before + 1)

	def test_a_booking_without_its_times_is_told_so(self):
		"""Sent through the API, without the screen's required fields: a clear message, not a failure reading them."""
		self.assertRaisesRegex(frappe.MandatoryError, "Enter the booking's", self.book, start=None)
		self.assertRaisesRegex(frappe.MandatoryError, "Enter the booking's", self.book, end="")

	def test_the_api_is_checked_like_the_screen(self):
		"""frappe.client.insert / save, what the REST API runs: the same overlap check, for a branch manager too."""
		from frappe.client import insert, save

		self.book(start="10:00", end="12:00")
		values = {
			"doctype": "Booking",
			"resource": self.hall,
			"customer": self.customer,
			"booking_date": DAY,
			"from_time": "11:00",
			"to_time": "13:00",
			"activity": "Anatomy lecture",
			"responsible_name": "د. أحمد",
			"responsible_phone": "01112223333",
			"rental_model": "Fixed Rent",
		}
		frappe.set_user(NOUR)
		self.assertRaisesRegex(frappe.ValidationError, "already booked", insert, values)
		later = insert({**values, "from_time": "12:00", "to_time": "13:00"})  # back to back
		self.assertRaisesRegex(frappe.ValidationError, "already booked", save, {**later, "from_time": "11:30"})

	def test_cancelled_and_no_show_bookings_free_their_time(self):
		cancelled = self.book(start="10:00", end="12:00")
		cancelled.status, cancelled.cancellation_reason = "Cancelled", "Lecture moved"
		cancelled.save()
		self.book(start="10:00", end="12:00")
		missed = self.book(date=PAST, start="10:00", end="12:00")
		missed.status = "No Show"
		missed.save()
		self.book(date=PAST, start="11:00", end="12:00")
		# Taking a cancelled booking back is checked like a new one.
		cancelled.reload()
		cancelled.status = "Tentative"
		self.assertRaisesRegex(frappe.ValidationError, "already booked", cancelled.save)

	def test_a_disabled_resource_takes_no_new_booking(self):
		booking = self.book()
		frappe.db.set_value("Booking Resource", self.hall, "disabled", 1)
		self.assertRaisesRegex(frappe.ValidationError, "disabled", self.book, start="14:00", end="15:00")
		# Its bookings can still be cancelled, or have their amounts changed.
		booking.reload()
		booking.total_amount = 300
		booking.save()
		booking.status, booking.cancellation_reason = "Cancelled", "Hall closed"
		booking.save()
		# ... but not take time on it again: taken back, or moved to another time.
		booking.status = "Tentative"
		self.assertRaisesRegex(frappe.ValidationError, "disabled", booking.save)
		frappe.db.set_value("Booking Resource", self.hall, "disabled", 0)
		moved = self.book(start="16:00", end="17:00")
		frappe.db.set_value("Booking Resource", self.hall, "disabled", 1)
		moved.reload()
		moved.from_time, moved.to_time = "18:00", "19:00"
		self.assertRaisesRegex(frappe.ValidationError, "disabled", moved.save)

	# ---------- STU-08: statuses ----------

	def test_statuses(self):
		from imed_erp.imederp.booking_accounts import record_payment

		booking = self.book(self.podcast)
		self.assertEqual(booking.total_amount, 1250)
		booking.status = "Confirmed with Deposit"
		self.assertRaisesRegex(frappe.ValidationError, "deposit", booking.save)
		# The deposit confirms it (STU-08).
		record_payment(booking.name, 300)
		booking.reload()
		self.assertEqual((booking.status, booking.paid_amount), ("Confirmed with Deposit", 300))
		booking.status = "Completed"
		self.assertRaisesRegex(frappe.ValidationError, "not started", booking.save)
		booking.reload()
		booking.status = "Cancelled"
		self.assertRaisesRegex(frappe.ValidationError, "reason", booking.save)
		booking.reload()
		booking.status, booking.cancellation_reason = "Cancelled", "  العميل اعتذر  "
		booking.save()
		self.assertEqual(booking.cancellation_reason, "العميل اعتذر")
		booking.status = "Tentative"
		booking.save()
		self.assertIsNone(booking.cancellation_reason)
		past = self.book(self.podcast, date=PAST)
		past.status = "Completed"
		past.save()
		self.assertEqual(frappe.db.get_value("Booking", past.name, "status"), "Completed")

	# ---------- STU-14: source ----------

	def test_a_booking_entered_here_is_manual(self):
		booking = self.book(source="Imported", source_system="x", external_id="1", import_key="x:1")
		self.assertEqual((booking.source, booking.source_system, booking.external_id, booking.import_key), ("Manual", None, None, None))
		booking.source, booking.import_key = "Imported", "x:1"
		booking.save()
		self.assertEqual(frappe.db.get_value("Booking", booking.name, ["source", "import_key"]), ("Manual", None))

	def import_rows(self, *rows):
		base = {"resource": self.podcast, "customer_phone": "+20 10 5555 4444", "booking_date": DAY, "total_amount": 1250, "paid_amount": 0}
		return import_bookings("studio_booking", [{**base, **row} for row in rows])

	def test_an_import_is_recorded_once_and_never_overwritten(self):
		first = self.import_rows({"external_id": "A1", "from_time": "10:00", "to_time": "11:00"})
		[name] = first["inserted"]
		booking = frappe.get_doc("Booking", name)
		self.assertEqual((booking.source, booking.source_system, booking.external_id), ("Imported", "studio_booking", "A1"))
		self.assertEqual(booking.customer, self.customer)  # found by phone, in another spelling
		# The same file again: nothing new.
		again = self.import_rows({"external_id": "A1", "from_time": "10:00", "to_time": "11:00"})
		self.assertEqual((again["inserted"], again["skipped"]), ([], ["A1"]))
		# Changed in the source: listed, not overwritten.
		changed = self.import_rows({"external_id": "A1", "from_time": "10:00", "to_time": "11:30"})
		self.assertEqual(changed["changed"], [("A1", name, ["to_time"])])
		self.assertEqual(str(frappe.db.get_value("Booking", name, "to_time")), "11:00:00")
		self.assertEqual(frappe.db.count("Booking", {"external_id": "A1"}), 1)

	def test_an_imported_booking_is_changed_only_in_its_source(self):
		[name] = self.import_rows({"external_id": "A2", "from_time": "10:00", "to_time": "11:00"})["inserted"]
		booking = frappe.get_doc("Booking", name)
		booking.status, booking.cancellation_reason = "Cancelled", "x"
		self.assertRaisesRegex(frappe.ValidationError, "Change it there", booking.save)

	def test_bad_import_rows_fail_alone(self):
		self.book(self.podcast, start="10:00", end="11:00")  # a WhatsApp booking entered here
		result = self.import_rows(
			{"external_id": "B1", "from_time": "10:30", "to_time": "11:30"},  # overlaps the manual one
			{"external_id": "B2", "from_time": "12:00", "to_time": "13:00", "customer_phone": "01099998888"},
			{"external_id": "", "from_time": "13:00", "to_time": "14:00"},
			{"external_id": "B3", "from_time": "14:00", "to_time": "13:00"},
			{"external_id": "B4", "from_time": "15:00", "to_time": "16:00"},
		)
		failed = dict(result["failed"])
		self.assertIn("already booked", failed["B1"])
		self.assertIn("No customer", failed["B2"])
		self.assertIn("no id", failed[""])
		self.assertIn("not after it starts", failed["B3"])
		self.assertEqual(len(result["inserted"]), 1)
		self.assertFalse(frappe.db.exists("Booking", {"external_id": ["in", ["B1", "B2", "B3"]]}))

	def test_an_import_rolled_back_by_the_database_says_so(self):
		"""After a deadlock the database has rolled the whole run back, savepoint and all: the import must not
		return a result listing bookings that are gone."""
		from unittest.mock import patch

		real_rollback = frappe.db.rollback

		def lost_savepoint(save_point=None, **kwargs):
			if save_point == "booking_import_row":
				raise Exception("SAVEPOINT booking_import_row does not exist")
			return real_rollback(save_point=save_point, **kwargs) if save_point else None

		with patch.object(frappe.db, "rollback", side_effect=lost_savepoint):
			with self.assertRaisesRegex(frappe.ValidationError, "nothing of this run was kept"):
				self.import_rows(
					{"external_id": "C1", "from_time": "10:00", "to_time": "11:00"},
					{"external_id": "C2", "from_time": "11:00", "to_time": "10:00"},  # fails
				)

	def test_restrictions_for_other_screens_do_not_apply(self):
		from imed_erp.imederp.doctype.booking.booking import check_own_business

		with patch_user_permissions({"Cost Center": [{"doc": HALLS, "applicable_for": "Expense"}]}):
			check_own_business(STUDIO)  # restricted on expenses only
		with patch_user_permissions({"Cost Center": [{"doc": HALLS, "applicable_for": None}]}):
			self.assertRaises(frappe.PermissionError, check_own_business, STUDIO)

	# ---------- Who ----------

	def test_each_business_books_only_its_own(self):
		own = self.book(user=NOUR)
		self.assertEqual(own.cost_center, HALLS)
		self.assertRaises(frappe.PermissionError, self.book, self.podcast, user=NOUR)
		# ... nor by moving her own booking to the studio's resource.
		frappe.set_user(NOUR)
		own.reload()
		own.resource = self.podcast
		self.assertRaises(frappe.PermissionError, own.save)
		frappe.set_user("Administrator")
		self.assertEqual(self.book(self.podcast, user=GILAN, start="14:00", end="15:00").cost_center, STUDIO)
		self.assertRaises(frappe.PermissionError, self.book, user=HR, start="16:00", end="17:00")
		hall_booking = self.book(start="18:00", end="19:00")
		frappe.set_user(GILAN)
		self.assertFalse(frappe.has_permission("Booking", "read", hall_booking.name))

	# ---------- The calendar: a day or a week of bookings ----------

	def events(self, start, days, user="Administrator", **filters):
		from imed_erp.imederp.doctype.booking.booking import get_events

		frappe.set_user(user)
		try:
			return get_events(f"{start} 00:00:00", f"{add_days(start, days)} 00:00:00", frappe.as_json(filters) if filters else None)
		finally:
			frappe.set_user("Administrator")

	def test_the_calendar_shows_a_day(self):
		booking = self.book(start="10:00", end="12:00", total_amount=500)
		self.book(self.podcast, start="10:00", end="11:00")  # same time, another resource
		self.book(date=add_days(DAY, 1), start="10:00", end="12:00")  # the next day
		events = {e.name: e for e in self.events(DAY, 1)}
		self.assertEqual(len(events), 2)
		event = events[booking.name]
		self.assertEqual(
			(event.resource, event.status, event.start, event.end, event.holding, event.conflict),
			(self.hall, "Tentative", f"{DAY} 10:00:00", f"{DAY} 12:00:00", 1, 0),
		)
		self.assertIn(self.hall, event.title)
		self.assertIn("Tentative", event.title)
		self.assertEqual(self.events(add_days(DAY, 30), 1), [])  # an empty day

	def test_the_calendar_shows_a_week(self):
		first = self.book(date=DAY, start="09:00", end="10:00")
		last = self.book(date=add_days(DAY, 6), start="09:00", end="10:00")
		self.book(date=add_days(DAY, 7), start="09:00", end="10:00")  # the next week (the range's end is not in it)
		self.book(date=add_days(DAY, -1), start="09:00", end="10:00")  # the week before
		cancelled = self.book(date=add_days(DAY, 2), start="09:00", end="10:00")
		cancelled.status, cancelled.cancellation_reason = "Cancelled", "Moved"
		cancelled.save()
		events = {e.name: e for e in self.events(DAY, 7)}
		self.assertEqual(set(events), {first.name, last.name, cancelled.name})
		# A cancelled booking is shown, as not holding its time.
		self.assertEqual((events[cancelled.name].status, events[cancelled.name].holding), ("Cancelled", 0))
		# The list's filters apply.
		self.assertEqual({e.name for e in self.events(DAY, 7, status="Cancelled")}, {cancelled.name})
		self.assertEqual(self.events(DAY, 7, resource=self.hall2), [])

	def test_the_calendar_marks_an_overlap_made_around_the_check(self):
		booking = self.book(start="10:00", end="12:00")
		# Written straight to the database, as nothing in the app can: the calendar still shows it, in red.
		clash = frappe.copy_doc(booking)
		clash.update({"from_time": "11:00:00", "to_time": "13:00:00"})
		clash.name = None
		clash.set_new_name()
		clash.db_insert()
		self.book(self.hall2, start="10:00", end="12:00")  # same time, another hall: no overlap
		events = {e.name: e for e in self.events(DAY, 1)}
		self.assertEqual({name for name, e in events.items() if e.conflict}, {booking.name, clash.name})

	def test_the_calendar_shows_only_what_the_user_may_read(self):
		hall_booking = self.book(start="10:00", end="12:00")
		studio_booking = self.book(self.podcast, start="10:00", end="12:00")
		self.assertEqual({e.name for e in self.events(DAY, 1, user=NOUR)}, {hall_booking.name})
		self.assertEqual({e.name for e in self.events(DAY, 1, user=GILAN)}, {studio_booking.name})
		self.assertEqual({e.name for e in self.events(DAY, 1)}, {hall_booking.name, studio_booking.name})
		# No access to bookings at all: refused, not an empty calendar.
		self.assertRaises(frappe.PermissionError, self.events, DAY, 1, user=HR)
