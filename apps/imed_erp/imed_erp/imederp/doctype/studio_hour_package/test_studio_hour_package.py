# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Prepaid studio hours (22 Oct 2026): sessions draw their exact length, the hours left follow every change, never
# below zero; hours beyond the package are billed only on the accountant's or the owner's decision; the package's
# hours are billed once, by its own invoice. Rolled back afterwards.
#
#   bench --site frontend run-tests --doctype "Studio Hour Package"

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from imed_erp.imederp.doctype.studio_hour_package.studio_hour_package import cancel_package, make_invoice

IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Booking", "Booking Resource", "Booking Package", "Customer", "Cost Center", "Item", "Sales Invoice", "Studio Hour Package", "User",
]

STUDIO = "استوديو X - MMG"
HALLS = "قاعات Imed - MMG"
GILAN, NOUR, ACCOUNTANT = "gilan@imed.local", "nour@imed.local", "accountant@imed.local"
ITEM = "_TEST-SHP-STUDIO-HOUR"
DAY = add_days(today(), 5)


def as_user(user, fn, *args, **kwargs):
	frappe.set_user(user)
	try:
		return fn(*args, **kwargs)
	finally:
		frappe.set_user("Administrator")


class IntegrationTestStudioHourPackage(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc({"doctype": "Item", "item_code": ITEM, "item_name": ITEM, "item_group": "الخدمات", "stock_uom": "Nos", "is_stock_item": 0}).insert()
		frappe.get_doc({"doctype": "Item Price", "item_code": ITEM, "price_list": "Standard Selling", "price_list_rate": 400}).insert()
		cls.studio = frappe.get_doc(
			{"doctype": "Booking Resource", "resource_name": "_Test Recording Room", "resource_type": "Studio Service", "cost_center": STUDIO, "item": ITEM}
		).insert().name
		cls.hall = frappe.get_doc(
			{"doctype": "Booking Resource", "resource_name": "_Test Package Hall", "resource_type": "Hall", "cost_center": HALLS, "item": ITEM, "capacity": 20}
		).insert().name
		group = frappe.get_all("Customer Group", filters={"is_group": 0}, limit=1, pluck="name")[0]
		territory = frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0]
		cls.teacher, cls.other = (
			frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Individual", "customer_group": group, "territory": territory}).insert().name
			for name in ("_Test Recording Teacher", "_Test Other Teacher")
		)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("hour_package_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="hour_package_test")

	def package(self, hours=30, price=9000, customer=None, user=GILAN):
		def make():
			doc = frappe.get_doc(
				{"doctype": "Studio Hour Package", "customer": customer or self.teacher, "resource": self.studio, "purchase_date": today(), "hours_purchased": hours, "price": price}
			).insert()
			doc.submit()
			return doc

		return as_user(user, make)

	def session(self, package, start, end, date=DAY, user=GILAN, **values):
		return as_user(
			user,
			lambda: frappe.get_doc(
				{"doctype": "Booking", "resource": self.studio, "customer": self.teacher, "booking_date": date, "from_time": start, "to_time": end, "hour_package": package, **values}
			).insert(),
		)

	def left(self, package):
		return flt(frappe.db.get_value("Studio Hour Package", package, "hours_remaining"), 4)

	def test_sessions_draw_their_exact_hours(self):
		package = self.package().name
		self.session(package, "09:00", "11:00")
		self.session(package, "12:00", "15:00")
		third = self.session(package, "16:00", "17:30")
		self.assertEqual(self.left(package), 23.5)
		# Covered by the package: nothing more to pay for the session.
		self.assertEqual((third.package_hours, third.extra_hours, third.base_amount, third.total_amount), (1.5, 0, 0, 0))
		history = frappe.get_doc("Studio Hour Package", package).usage
		self.assertEqual([(r.hours, r.balance) for r in history], [(2, 28), (3, 25), (1.5, 23.5)])
		self.assertEqual({r.changed_by for r in history}, {GILAN})
		# Saved again, nothing more is drawn.
		as_user(GILAN, lambda: frappe.get_doc("Booking", third.name).save())
		self.assertEqual(self.left(package), 23.5)
		self.assertEqual(len(frappe.get_doc("Studio Hour Package", package).usage), 3)

	def test_sessions_over_days_and_weeks(self):
		package = self.package(hours=5).name
		self.session(package, "10:00", "12:00", date=DAY)
		self.session(package, "10:00", "12:00", date=add_days(DAY, 7))
		self.session(package, "10:00", "10:45", date=add_days(DAY, 14))
		self.assertEqual(self.left(package), 0.25)

	def test_rescheduled_and_cancelled_sessions_adjust_the_hours(self):
		package = self.package(hours=10).name
		booking = self.session(package, "10:00", "12:00")
		booking = frappe.get_doc("Booking", booking.name)
		booking.to_time = "13:30"
		as_user(GILAN, booking.save)
		self.assertEqual(self.left(package), 6.5)
		booking.reload()
		booking.booking_date, booking.from_time, booking.to_time = add_days(DAY, 1), "09:00", "10:00"
		as_user(GILAN, booking.save)
		self.assertEqual(self.left(package), 9)
		booking.reload()
		booking.status, booking.cancellation_reason = "Cancelled", "Teacher ill"
		as_user(GILAN, booking.save)
		self.assertEqual(self.left(package), 10)
		reasons = [r.reason for r in frappe.get_doc("Studio Hour Package", package).usage]
		self.assertIn("Teacher ill", reasons[-1])

	def test_never_more_than_what_is_left(self):
		package = self.package(hours=3).name
		self.session(package, "09:00", "11:00")
		self.assertRaisesRegex(frappe.ValidationError, "1.0 hours left|1 hours left", self.session, package, "12:00", "14:00")
		self.assertEqual(self.left(package), 1)
		# Only the accountant or the owner decides the hours beyond are billed.
		self.assertRaises(frappe.PermissionError, self.session, package, "12:00", "14:00", bill_extra_hours=1)
		extra = self.session(package, "12:00", "14:00", user=ACCOUNTANT, bill_extra_hours=1)
		self.assertEqual((extra.package_hours, extra.extra_hours, extra.extra_hours_approved_by), (1, 1, ACCOUNTANT))
		self.assertEqual((extra.rate, extra.base_amount), (400, 400))
		self.assertEqual((self.left(package), frappe.db.get_value("Studio Hour Package", package, "status")), (0, "Used Up"))
		# Made longer by the studio, the decision is taken again.
		extra = frappe.get_doc("Booking", extra.name)
		extra.to_time = "15:00"
		self.assertRaises(frappe.ValidationError, as_user, GILAN, extra.save)

	def test_the_package_is_billed_once_and_its_sessions_not_at_all(self):
		package = self.package(hours=4, price=1500).name
		invoice = as_user(GILAN, make_invoice, package)
		self.assertEqual(frappe.db.get_value("Sales Invoice", invoice, ["grand_total", "customer"]), (1500, self.teacher))
		self.assertRaises(frappe.ValidationError, as_user, GILAN, make_invoice, package)
		booking = self.session(package, "09:00", "11:00", date=add_days(today(), -1))
		booking = frappe.get_doc("Booking", booking.name)
		booking.status = "Completed"
		as_user(GILAN, booking.save)
		self.assertFalse(frappe.db.exists("Sales Invoice", {"custom_booking": booking.name, "docstatus": 1}))

	def test_the_right_package_for_the_right_session(self):
		theirs = self.package(customer=self.other).name
		self.assertRaisesRegex(frappe.ValidationError, "package for", self.session, theirs, "09:00", "10:00")
		draft = as_user(GILAN, lambda: frappe.get_doc(
			{"doctype": "Studio Hour Package", "customer": self.teacher, "resource": self.studio, "purchase_date": today(), "hours_purchased": 5, "price": 1}
		).insert())
		self.assertRaisesRegex(frappe.ValidationError, "not an active package", self.session, draft.name, "09:00", "10:00")
		# Prepaid hours are the studio's.
		self.assertRaises(
			frappe.ValidationError,
			lambda: frappe.get_doc({"doctype": "Studio Hour Package", "customer": self.teacher, "resource": self.hall, "purchase_date": today(), "hours_purchased": 5, "price": 1}).insert(),
		)

	def test_the_studio_s_own_business_only(self):
		self.assertRaises(frappe.PermissionError, self.package, user=NOUR)

	def test_cancelling_a_package_with_hours_held_is_refused(self):
		package = self.package(hours=6).name
		booking = self.session(package, "09:00", "10:00")
		self.assertRaises(frappe.PermissionError, as_user, GILAN, cancel_package, package, "wrong teacher")
		self.assertRaisesRegex(frappe.ValidationError, "held by bookings", as_user, ACCOUNTANT, cancel_package, package, "wrong teacher")
		booking = frappe.get_doc("Booking", booking.name)
		booking.status, booking.cancellation_reason = "Cancelled", "moved to another package"
		as_user(GILAN, booking.save)
		as_user(ACCOUNTANT, cancel_package, package, "wrong teacher")
		self.assertEqual(frappe.db.get_value("Studio Hour Package", package, ["status", "cancel_reason"]), ("Cancelled", "wrong teacher"))

	def test_overlapping_sessions_are_still_refused(self):
		package = self.package().name
		self.session(package, "09:00", "11:00")
		self.assertRaises(frappe.ValidationError, self.session, package, "10:00", "12:00")
		self.assertEqual(self.left(package), 28)

	def test_moved_to_another_package_gives_the_first_its_hours_back(self):
		first, second = self.package(hours=5).name, self.package(hours=5).name
		booking = self.session(first, "09:00", "11:00")
		booking = frappe.get_doc("Booking", booking.name)
		booking.hour_package = second
		as_user(GILAN, booking.save)
		self.assertEqual((self.left(first), self.left(second)), (5, 3))
