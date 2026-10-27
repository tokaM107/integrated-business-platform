# IMED's own lecture halls (never XStudio's rooms): the hall booking workflow end to end, on test resources rolled
# back afterwards. The existing checks (overlap, statuses, pricing, permissions) are in test_booking.py and
# test_booking_pricing.py; this module covers what the halls added on 26 Oct 2026: the booking types, not-billable
# bookings, the deposit-free Confirmed status, capacity, bookings across midnight, the buffer, maintenance blocks,
# the doctor and course links, the financial-review flag, the dashboard figures and the separation from XStudio.
#
#   bench --site frontend run-tests --module imed_erp.imederp.test_hall_bookings
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, get_datetime, now_datetime, today

from imed_erp.imederp.doctype.booking import booking as booking_module
from imed_erp.imederp.doctype.booking.booking import get_events

HALLS = "قاعات Imed - MMG"
STUDIO = "استوديو X - MMG"
DAY = add_days(today(), 10)
PAST = add_days(today(), -2)
ITEM = "_TEST-HALL-BK-HOUR"
NOUR, GILAN, HR = "nour@imed.local", "gilan@imed.local", "hr@imed.local"


class IntegrationTestHallBookings(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc({"doctype": "Item", "item_code": ITEM, "item_name": ITEM, "item_group": "الخدمات", "stock_uom": "Nos", "is_stock_item": 0}).insert()
		if not frappe.db.exists("Item Price", {"item_code": ITEM, "price_list": "Standard Selling"}):
			frappe.get_doc({"doctype": "Item Price", "item_code": ITEM, "price_list": "Standard Selling", "price_list_rate": 300}).insert()
		cls.hall = cls.resource("_Test IMED Hall A", capacity=30, item=ITEM, location="Floor 2")
		cls.hall_b = cls.resource("_Test IMED Hall B", capacity=12, item=ITEM, buffer_minutes=15)
		cls.studio_room = frappe.get_doc({"doctype": "Booking Resource", "resource_name": "_Test Studio Room", "resource_type": "Studio Service", "cost_center": STUDIO, "item": ITEM}).insert().name
		group = frappe.get_all("Customer Group", filters={"is_group": 0, "name": ("!=", "طبيب")}, limit=1, pluck="name")[0]
		territory = frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0]
		cls.renter = frappe.get_doc({"doctype": "Customer", "customer_name": "_Test Hall Renter", "customer_type": "Individual", "customer_group": group, "territory": territory, "mobile_no": "01066667777"}).insert().name
		cls.doctor = frappe.get_doc({"doctype": "Customer", "customer_name": "_Test Hall Doctor", "customer_type": "Individual", "customer_group": "طبيب", "territory": territory, "mobile_no": "01066668888"}).insert().name
		cls.not_a_doctor = cls.renter

	@staticmethod
	def resource(name, **values):
		return frappe.get_doc({"doctype": "Booking Resource", "resource_name": name, "resource_type": "Hall", "cost_center": HALLS, **values}).insert().name

	def setUp(self):
		frappe.db.savepoint("hall_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="hall_test")

	def book(self, kind="Fixed-fee Rental", resource=None, start="10:00", end="12:00", date=DAY, user="Administrator", **values):
		frappe.set_user(user)
		try:
			doc = frappe.get_doc(
				{
					"doctype": "Booking",
					"resource": resource or self.hall,
					"customer": self.renter,
					"booking_date": date,
					"from_time": start,
					"to_time": end,
					"hall_booking_type": kind,
					"activity": "Pathology lecture",
					"responsible_name": "منة",
					"responsible_phone": "01112223333",
					**values,
				}
			)
			return doc.insert()
		finally:
			frappe.set_user("Administrator")

	def counts(self):
		return (frappe.db.count("Sales Invoice"), frappe.db.count("Payment Entry"), frappe.db.count("Journal Entry"), frappe.db.count("GL Entry"))

	# ---------- 1-2-3-4: a booking, the overlap, other halls, back to back ----------

	def test_a_hall_booking_is_made_with_its_type_model_and_cost_center(self):
		booking = self.book()
		self.assertEqual((booking.resource_type, booking.cost_center, booking.hall_booking_type, booking.rental_model, booking.status), ("Hall", HALLS, "Fixed-fee Rental", "Fixed Rent", "Tentative"))
		self.assertEqual((booking.hours, booking.total_amount, booking.capacity, booking.source), (2, 600, 30, "Manual"))
		self.assertEqual((str(booking.starts_at), str(booking.ends_at)), (f"{DAY} 10:00:00", f"{DAY} 12:00:00"))

	def test_the_same_hall_at_an_overlapping_time_is_refused_and_other_halls_are_free(self):
		self.book(start="10:00", end="12:00")
		self.assertRaisesRegex(frappe.ValidationError, "already booked", self.book, start="11:00", end="13:00")
		self.assertRaisesRegex(frappe.ValidationError, "already booked", self.book, kind="Internal Meeting", start="09:00", end="10:30", customer=None)
		self.book(resource=self.hall_b, start="10:00", end="12:00")  # another hall, same time
		self.book(start="12:00", end="14:00")  # back to back: free on a hall with no buffer

	def test_a_buffer_keeps_minutes_free_around_each_booking(self):
		self.book(resource=self.hall_b, start="10:00", end="12:00")
		self.assertRaisesRegex(frappe.ValidationError, "15 minutes", self.book, resource=self.hall_b, start="12:10", end="13:00")
		self.book(resource=self.hall_b, start="12:15", end="13:00")

	# ---------- 5-6: times, midnight ----------

	def test_wrong_and_zero_length_times_are_refused(self):
		self.assertRaisesRegex(frappe.ValidationError, "no length", self.book, start="10:00", end="10:00")
		self.assertRaises(frappe.MandatoryError, self.book, from_time=None)

	def test_a_booking_across_midnight_holds_both_days(self):
		late = self.book(start="22:00", end="01:00")
		self.assertEqual((late.ends_next_day, late.hours, str(late.ends_at)), (1, 3, f"{add_days(DAY, 1)} 01:00:00"))
		# The next day's early hour is taken; later that morning is free.
		self.assertRaisesRegex(frappe.ValidationError, "already booked", self.book, date=add_days(DAY, 1), start="00:30", end="02:00")
		self.book(date=add_days(DAY, 1), start="01:00", end="02:00")
		# The calendar shows it on both days.
		events = get_events(f"{add_days(DAY, 1)} 00:00:00", f"{add_days(DAY, 1)} 23:59:59", [["resource", "=", self.hall]])
		self.assertIn(late.name, [e.name for e in events])

	# ---------- 7: capacity ----------

	def test_capacity_is_enforced_when_attendees_are_known(self):
		self.assertRaisesRegex(frappe.ValidationError, "capacity", self.book, expected_attendees=31)
		booking = self.book(expected_attendees=30)
		booking.attendees = 31
		self.assertRaisesRegex(frappe.ValidationError, "capacity", booking.save)
		self.book(resource=self.hall_b, start="14:00", end="15:00")  # no attendees given: nothing to check

	# ---------- 8-9: a cancelled slot is free again; rescheduling ----------

	def test_a_cancelled_booking_frees_its_slot_and_a_reschedule_is_checked(self):
		first = self.book(start="10:00", end="12:00")
		second = self.book(start="14:00", end="16:00")
		first.status, first.cancellation_reason = "Cancelled", "المحاضر اعتذر"
		first.save()
		again = self.book(start="10:00", end="12:00")  # the slot is free again
		# Rescheduling the second one onto the re-taken slot is refused; onto a free one, allowed.
		second.reload()
		second.from_time, second.to_time = "11:00", "13:00"
		self.assertRaisesRegex(frappe.ValidationError, "already booked", second.save)
		second.reload()
		second.from_time, second.to_time = "16:00", "18:00"
		second.save()
		self.assertEqual(str(second.starts_at), f"{DAY} 16:00:00")
		self.assertTrue(again.name)

	# ---------- 10: two saves at once ----------

	def test_two_bookings_of_a_hall_at_the_same_moment_are_serialised(self):
		self.assertEqual(frappe.db.sql("select @@innodb_snapshot_isolation")[0][0], 1)
		before = frappe.db.get_value("Booking Resource", self.hall, "bookings_saved") or 0
		self.book()
		self.assertEqual(frappe.db.get_value("Booking Resource", self.hall, "bookings_saved"), before + 1)

	# ---------- 11-12: inactive halls, maintenance ----------

	def test_an_inactive_hall_takes_no_new_booking(self):
		closed = self.resource("_Test Closed Hall", capacity=10, item=ITEM, disabled=1)
		self.assertRaisesRegex(frappe.ValidationError, "disabled", self.book, resource=closed)

	def test_a_maintenance_block_holds_the_hall_without_a_customer_or_a_price(self):
		block = self.book(kind="Maintenance Block", customer=None, activity="", responsible_name="", responsible_phone="", start="08:00", end="18:00")
		self.assertEqual((block.rental_model, block.customer, block.activity, block.total_amount), ("Not Billable", None, "Maintenance", 0))
		self.assertRaisesRegex(frappe.ValidationError, "already booked", self.book, start="10:00", end="12:00")
		block.status, block.cancellation_reason = "Cancelled", "done early"
		block.save()
		self.book(start="10:00", end="12:00")

	# ---------- 13-16: doctors, courses, agreements, rentals without a lecturer ----------

	def test_a_booking_names_an_existing_doctor_never_another_record(self):
		booking = self.book(kind="External Lecturer", rental_model="Fixed Rent", doctor=self.doctor)
		self.assertEqual(booking.doctor, self.doctor)
		self.assertRaisesRegex(frappe.ValidationError, "not a doctor", self.book, kind="External Lecturer", rental_model="Fixed Rent", doctor=self.not_a_doctor)
		self.assertEqual(frappe.db.count("Customer", {"customer_name": "_Test Hall Doctor"}), 1)

	def test_a_booking_links_an_existing_course_and_takes_its_doctor(self):
		agreement = frappe.get_all("Doctor Agreement", filters={"agreement_type": "App", "docstatus": 1}, limit=1, pluck="name")
		course = frappe.get_all("App Course", limit=1, fields=["name", "doctor"])
		if not course:
			self.skipTest("no App Course on this site")
		booking = self.book(kind="Internal Course or Lecture", course=course[0].name, customer=None)
		self.assertEqual((booking.course, booking.doctor, booking.rental_model, booking.total_amount), (course[0].name, course[0].doctor, "Not Billable", 0))

	def test_a_revenue_share_with_no_agreed_share_is_flagged_not_guessed(self):
		booking = self.book(kind="Revenue Share", attendees=20, admission_price=50)
		self.assertEqual((booking.rental_model, booking.expected_revenue, flt(booking.lecturer_share_percent), booking.financial_review), ("Revenue Share", 1000, 0, 1))
		self.assertIn("no Doctor Agreement", booking.financial_note)
		self.assertEqual(frappe.db.count("Doctor Agreement", {"agreement_type": ("not in", ("Books", "App"))}), 0)
		# Agreeing the share on the booking clears the flag; the shares follow what is collected.
		booking.lecturer_share_percent, booking.collected_amount = 40, 800
		booking.save()
		self.assertEqual((booking.financial_review, booking.lecturer_share, booking.center_share), (0, 320, 480))

	def test_a_rental_needs_no_lecturer_and_an_external_lecturer_is_never_free(self):
		booking = self.book(kind="Fixed-fee Rental")
		self.assertEqual((booking.doctor, booking.lecturer, booking.total_amount), (None, None, 600))
		self.assertRaisesRegex(frappe.ValidationError, "choose one", self.book, kind="External Lecturer", start="14:00", end="15:00")
		self.assertRaisesRegex(frappe.ValidationError, "choose one", self.book, kind="External Lecturer", rental_model="Not Billable", start="14:00", end="15:00")

	# ---------- 17-21: money ----------

	def test_a_fixed_rent_is_the_hall_s_price_times_the_hours(self):
		booking = self.book(start="09:00", end="12:30")
		self.assertEqual((booking.rate, booking.base_amount, booking.total_amount, booking.paid_amount, booking.outstanding_amount), (300, 1050, 1050, 0, 1050))

	def test_no_accounting_entry_comes_from_booking_confirming_rescheduling_or_cancelling(self):
		before = self.counts()
		booking = self.book()
		booking.status = "Confirmed"
		booking.save()
		booking.from_time, booking.to_time = "13:00", "15:00"
		booking.save()
		booking.status, booking.cancellation_reason = "Cancelled", "x"
		booking.save()
		self.assertEqual(self.counts(), before)

	def test_a_not_billable_booking_is_completed_without_an_invoice_and_takes_no_payment(self):
		from imed_erp.imederp.booking_accounts import record_payment

		before = self.counts()
		meeting = self.book(kind="Internal Meeting", customer=None, date=PAST, start="09:00", end="10:00")
		self.assertRaisesRegex(frappe.ValidationError, "not billable", record_payment, meeting.name, 100)
		meeting.status = "Completed"
		meeting.save()
		self.assertEqual((meeting.sales_invoice, meeting.journal_entry, self.counts()), (None, None, before))

	def test_a_billed_hall_booking_needs_its_customer(self):
		self.assertRaises(frappe.MandatoryError, self.book, customer=None)
		self.assertRaises(frappe.ValidationError, self.book, kind="Internal Meeting", package="_Test Not A Package")

	# ---------- 22: the owner's figures ----------

	def test_the_owner_s_hall_figures_follow_the_statuses_and_leave_xstudio_out(self):
		from imed_erp.imederp import owner_yesterday

		frappe.set_user("owner@imed.local")
		try:
			before = owner_yesterday.halls()
		finally:
			frappe.set_user("Administrator")
		now = now_datetime()
		held = self.book(date=today(), start=f"{(now.hour - 1) % 24:02d}:00", end=f"{(now.hour + 1) % 24:02d}:00") if 1 <= now.hour <= 22 else self.book(date=today(), start="00:00", end="23:00")
		cancelled = self.book(date=today(), start="23:00", end="23:30")
		cancelled.status, cancelled.cancellation_reason = "Cancelled", "x"
		cancelled.save()
		self.book(date=add_days(today(), 3))
		self.book(resource=self.studio_room, date=today(), start="23:30", end="23:45", kind=None, activity=None, responsible_name=None, responsible_phone=None)
		frappe.set_user("owner@imed.local")
		try:
			after = owner_yesterday.halls()
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(after["today"]["held"] - before["today"]["held"], 1)
		self.assertEqual(after["today"]["cancelled"] - before["today"]["cancelled"], 1)
		self.assertEqual(after["upcoming"] - before["upcoming"], 1)
		self.assertEqual(after["occupied_now"] - before["occupied_now"], 1)
		self.assertGreaterEqual(after["active_halls"], 2)  # the two test halls are active; the count never depends on bookings
		self.assertTrue(held.name)

	# ---------- 23-26: cost center, permissions, audit, labels ----------

	def test_the_cost_center_is_the_halls_never_the_studio_s(self):
		self.assertEqual(self.book().cost_center, HALLS)
		self.assertEqual(frappe.db.get_value("Booking Resource", self.hall, "cost_center"), HALLS)
		studio = self.book(resource=self.studio_room, kind=None, activity=None, responsible_name=None, responsible_phone=None)
		self.assertEqual((studio.cost_center, studio.resource_type, studio.hall_booking_type), (STUDIO, "Studio Service", None))

	def test_who_may_book_confirm_and_cancel(self):
		# The halls' manager books her halls; the studio's manager may not; a user without the role may not even read.
		self.book(user=NOUR, start="08:00", end="09:00")
		self.assertRaises(frappe.PermissionError, self.book, user=GILAN, start="09:00", end="10:00")
		frappe.set_user(HR)
		try:
			self.assertFalse(frappe.has_permission("Booking", "write"))
			self.assertFalse(frappe.has_permission("Booking", "create"))
		finally:
			frappe.set_user("Administrator")
		booking = self.book(start="14:00", end="15:00")
		frappe.set_user(HR)
		try:
			doc = frappe.get_doc("Booking", booking.name)
			doc.status = "Confirmed"
			self.assertRaises(frappe.PermissionError, doc.save)
		finally:
			frappe.set_user("Administrator")

	def test_changes_are_tracked(self):
		"""Booking tracks changes (a Version per save, as on the live site); the test runner skips versions unless asked."""
		booking = self.book()
		booking.status = "Confirmed"
		booking.save(ignore_version=False)
		booking.from_time, booking.to_time = "15:00", "17:00"
		booking.save(ignore_version=False)
		versions = frappe.get_all("Version", filters={"ref_doctype": "Booking", "docname": booking.name}, pluck="data")
		changed = {change[0] for v in versions for change in frappe.parse_json(v).get("changed", [])}
		self.assertTrue({"status", "from_time", "to_time"} <= changed)

	def test_the_confirmed_status_needs_no_deposit_on_a_hall_and_is_refused_on_the_studio(self):
		booking = self.book()
		booking.status = "Confirmed"
		booking.save()
		self.assertEqual((booking.status, booking.paid_amount), ("Confirmed", 0))
		studio = self.book(resource=self.studio_room, kind=None, activity=None, responsible_name=None, responsible_phone=None, start="14:00", end="15:00")
		studio.status = "Confirmed"
		self.assertRaisesRegex(frappe.ValidationError, "deposit", studio.save)

	def test_arabic_labels_exist_for_the_new_statuses_and_types(self):
		for text in ("Confirmed", "Hall Booking Type", "Maintenance Block", "Not Billable", "IMED hall bookings"):
			self.assertNotEqual(frappe._(text, "ar"), text, text)

	# ---------- 27: XStudio untouched ----------

	def test_xstudio_s_rooms_and_bookings_are_untouched(self):
		xstudio = frappe.get_all("Booking", filters={"source_system": "xstudio"}, fields=["name", "modified", "resource_type"])
		self.book()
		self.assertTrue(all(row.resource_type == "Studio Service" for row in xstudio))
		after = {row.name: row.modified for row in frappe.get_all("Booking", filters={"source_system": "xstudio"}, fields=["name", "modified"])}
		self.assertEqual({row.name: row.modified for row in xstudio}, after)
		self.assertEqual(frappe.db.count("Booking Resource", {"resource_type": "Hall", "name": ("like", "X Studio%")}), 0)

	def test_the_hall_bookings_report_lists_the_type_the_doctor_and_the_hours(self):
		from imed_erp.imederp.report.hall_bookings.hall_bookings import execute

		booking = self.book(kind="External Lecturer", rental_model="Fixed Rent", doctor=self.doctor)
		_, rows = execute({"from_date": DAY, "to_date": DAY, "hall": self.hall})
		[row] = [r for r in rows if r["name"] == booking.name]
		self.assertEqual((row["doctor"], row["hours"], row["rent"]), (self.doctor, 2, 600))
		self.assertEqual(row["hall_booking_type"], frappe._("External Lecturer"))

	# ---------- 27 Oct 2026: finalisation (explicit posting, availability, the sidebar, the labels, the halls) ----------

	def test_a_completed_hall_booking_posts_nothing_until_asked_then_posts_once(self):
		"""The requirements never say that completing a hall booking makes its invoice: Completed posts nothing; the
		explicit action (Make Invoice) posts it, once."""
		from imed_erp.imederp.booking_accounts import make_booking_invoice

		before = self.counts()
		booking = self.book(date=PAST, start="09:00", end="11:00")
		booking.status = "Completed"
		booking.save()
		booking.reload()
		self.assertEqual((booking.status, booking.sales_invoice, self.counts()), ("Completed", None, before))
		result = make_booking_invoice(booking.name)
		self.assertTrue(result.sales_invoice)
		self.assertEqual(frappe.db.get_value("Sales Invoice", result.sales_invoice, ["grand_total", "docstatus"]), (600, 1))
		make_booking_invoice(booking.name)
		self.assertEqual(frappe.db.count("Sales Invoice", {"custom_booking": booking.name, "docstatus": 1}), 1)
		# The studio keeps the 20 Oct behaviour: its invoice is made on completion.
		studio = self.book(resource=self.studio_room, kind=None, activity=None, responsible_name=None, responsible_phone=None, date=PAST, start="12:00", end="13:00")
		studio.status = "Completed"
		studio.save()
		self.assertTrue(frappe.db.get_value("Booking", studio.name, "sales_invoice"))

	def test_the_form_is_told_whether_the_hall_is_free_with_the_owner_s_words(self):
		from imed_erp.imederp.doctype.booking.booking import check_availability

		booking = self.book(start="10:00", end="12:00")
		free = check_availability(self.hall, DAY, "12:00", "14:00")
		taken = check_availability(self.hall, DAY, "11:00", "13:00")
		self.assertEqual((free["free"], taken["free"], taken["booking"]), (1, 0, booking.name))
		self.assertTrue(taken["message"].startswith(frappe._("This hall is already booked at the time you chose. Try another time.")))
		self.assertEqual(frappe._("This hall is already booked at the time you chose. Try another time.", "ar"), "القاعة دي محجوزة بالفعل في الوقت اللي اخترته. جرّبي معاد تاني.")
		# The same booking, edited, is not its own clash; another hall is free; across midnight is understood.
		self.assertEqual(check_availability(self.hall, DAY, "10:00", "12:00", name=booking.name)["free"], 1)
		self.assertEqual(check_availability(self.hall_b, DAY, "10:00", "12:00")["free"], 1)
		self.assertEqual(check_availability(self.hall, DAY, "23:00", "01:00")["free"], 1)
		self.assertEqual(check_availability(self.hall, DAY, "10:00", "10:00")["free"], 0)
		# The save refuses the clash with the same first sentence.
		self.assertRaisesRegex(frappe.ValidationError, "already booked at the time", self.book, start="11:00", end="13:00")
		frappe.set_user(HR)
		try:
			self.assertRaises(frappe.PermissionError, check_availability, self.hall, DAY, "12:00", "14:00")
		finally:
			frappe.set_user("Administrator")

	def test_a_lecture_is_billed_to_its_doctor_unless_a_renter_is_named(self):
		lecture = self.book(kind="External Lecturer", rental_model="Fixed Rent", doctor=self.doctor, customer=None)
		self.assertEqual(lecture.customer, self.doctor)
		rented = self.book(kind="External Lecturer", rental_model="Fixed Rent", doctor=self.doctor, customer=self.renter, start="13:00", end="14:00")
		self.assertEqual(rented.customer, self.renter)
		block = self.book(kind="Maintenance Block", doctor=self.doctor, customer=None, start="15:00", end="16:00")
		self.assertEqual((block.customer, block.doctor), (None, None))

	def test_the_calendar_names_the_hall_the_purpose_and_the_doctor(self):
		self.book(kind="External Lecturer", rental_model="Fixed Rent", doctor=self.doctor, start="10:00", end="12:00")
		self.book(kind="Maintenance Block", customer=None, activity=None, start="13:00", end="14:00")
		events = [e for e in get_events(f"{DAY} 00:00:00", f"{add_days(DAY, 1)} 00:00:00", filters={"resource": self.hall}) if e.resource == self.hall]
		titles = [e.title for e in sorted(events, key=lambda e: e.start)]
		status = f" ({frappe._('Tentative')})"
		self.assertEqual(titles[0], f"{self.hall} · Pathology lecture · {self.doctor} · {frappe._('External Lecturer')}" + status)
		self.assertEqual(titles[1], f"{self.hall} · {frappe._('Maintenance')} · {frappe._('Maintenance Block')}" + status)
		self.assertEqual({e.hall_booking_type for e in events}, {"External Lecturer", "Maintenance Block"})

	def test_the_sidebar_is_grouped_by_workflow_with_no_dead_link_and_no_duplicate(self):
		"""The sidebar file (workspace_sidebar/imederp.json): the halls apart from the studio, every link to a page
		that exists, each page once per filter, Arabic for every label, and the same items on the site."""
		import json
		import os

		import imed_erp

		path = os.path.join(os.path.dirname(imed_erp.__file__), "workspace_sidebar", "imederp.json")
		items = json.load(open(path, encoding="utf-8"))["items"]
		sections = [i["label"] for i in items if i["type"] == "Section Break"]
		self.assertEqual(sections[:2], ["IMED Hall Bookings", "Photo Studio Bookings"])
		self.assertEqual(sections[-2:], ["Reports", "Settings"])
		labels = [i["label"] for i in items]
		self.assertEqual(len(labels), len(set(labels)), "duplicate labels")
		targets = []
		for item in items:
			if item["type"] != "Link":
				continue
			self.assertNotEqual(frappe._(item["label"], "ar"), item["label"], item["label"])
			if item["link_type"] == "URL":
				self.assertTrue(item["url"].startswith("/desk/booking/view/calendar/"), item["url"])
				targets.append(item["url"])
				continue
			exists = {"DocType": lambda n: frappe.db.exists("DocType", n), "Report": lambda n: frappe.db.exists("Report", {"name": n, "disabled": 0}), "Workspace": lambda n: frappe.db.exists("Workspace", n)}
			self.assertTrue(exists[item["link_type"]](item["link_to"]), f"{item['label']} -> {item['link_type']} {item['link_to']}")
			targets.append((item["link_type"], item["link_to"], item.get("filters")))
			if item.get("filters"):
				[[doctype, field, operator, value]] = json.loads(item["filters"])
				self.assertEqual(doctype, item["link_to"])
				self.assertTrue(frappe.get_meta(doctype).has_field(field), field)
		self.assertEqual(len(targets), len(set(targets)), "the same page twice with the same filter")
		halls = [i["label"] for i in items[items.index(next(i for i in items if i["label"] == "IMED Hall Bookings")) + 1 :]][:4]
		self.assertEqual(halls, ["Hall Calendar", "Hall Bookings List", "IMED Halls", "Hall Bookings Report"])
		# The site carries the same sidebar (bench migrate syncs the file).
		on_site = frappe.get_all("Workspace Sidebar Item", filters={"parent": "ImedERP"}, pluck="label", order_by="idx")
		self.assertEqual(on_site, labels)

	def test_the_arabic_labels_the_owner_asked_for(self):
		wanted = {
			"Hall Capacity": "عدد الأماكن",
			"Start Time": "من الساعة",
			"End Time": "لحد الساعة",
			"Booking Type": "نوع الحجز",
			"Expected Attendees": "العدد المتوقع",
			"Fixed Rent": "إيجار ثابت",
			"Revenue Share": "نسبة من الإيراد",
			"Not Billable": "بدون رسوم",
			"IMED Hall Bookings": "حجوزات قاعات IMED",
			"Photo Studio Bookings": "حجوزات استوديو التصوير",
		}
		for english, arabic in wanted.items():
			self.assertEqual(frappe._(english, "ar"), arabic, english)
		meta = frappe.get_meta("Booking")
		self.assertEqual((meta.get_label("from_time"), meta.get_label("to_time"), meta.get_label("hall_booking_type")), ("Start Time", "End Time", "Booking Type"))

	def test_the_requirements_halls_are_seeded_by_name_only_and_never_twice(self):
		from imed_erp.imederp import setup_halls

		self.assertEqual(setup_halls.HALL_NAMES, ["قاعة 1", "قاعة 3", "قاعة 4", "قاعة 5", "قاعة 6", "قاعة 7", "قاعة 8"])
		plan = setup_halls.plan()
		self.assertEqual([p["resource_name"] for p in plan], setup_halls.HALL_NAMES)
		for p in plan:
			# Nothing invented: no capacity, no equipment, no location, no price of its own; and without a capacity
			# (question 15) nothing is written.
			self.assertEqual((p["record"]["capacity"], p["record"]["equipment"], p["record"]["location"], p["record"]["cost_center"]), (0, None, None, HALLS))
			self.assertIn(p["action"], ("wait (capacity unknown)", "skip (exists)"))
		before = frappe.db.count("Booking Resource")
		self.assertEqual(setup_halls.run(), [])
		self.assertEqual(frappe.db.count("Booking Resource"), before)
		# With an answer (inside this test's savepoint, rolled back): that hall only, and never twice.
		if plan[0]["action"] == "wait (capacity unknown)":
			answered = {setup_halls.HALL_NAMES[0]: 40}
			self.assertEqual(setup_halls.run(capacities=answered, dry_run=True), [setup_halls.HALL_NAMES[0]])
			self.assertEqual(frappe.db.count("Booking Resource"), before)
			frappe.get_doc(setup_halls.plan(answered)[0]["record"]).insert()
			self.assertEqual(frappe.db.count("Booking Resource"), before + 1)
			again = setup_halls.plan(answered)
			self.assertEqual((again[0]["action"], again[1]["action"]), ("skip (exists)", "wait (capacity unknown)"))
			self.assertEqual(setup_halls.run(capacities=answered, dry_run=True), [])
