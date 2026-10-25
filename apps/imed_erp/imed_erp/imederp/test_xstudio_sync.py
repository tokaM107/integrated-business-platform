# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The XStudio sync (imederp/xstudio/) against a faithful stand-in for XStudio's API: the same endpoints, answers,
# 500-row cap and permissions as xstudio-platform/backend/src/routes.js, served from memory. Nothing here reaches a
# real XStudio; the live API is exercised by hand (docs/XSTUDIO_SYNC.md). Everything is rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_xstudio_sync

import itertools
import uuid
from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from imed_erp.imederp.xstudio import client as client_module
from imed_erp.imederp.xstudio import mappers, sync
from imed_erp.imederp.xstudio.client import XStudioClient, XStudioError
from imed_erp.imederp.xstudio.mappers import CAIRO

# A test module outside a doctype folder builds no "_Test ..." records; keep it here, not under a doctype.
STUDIO = "استوديو X - MMG"
GROUP = "عملاء الاستوديو"
TOKEN = "test-token"
PASSWORD = "sync-password-1"
COUNTER = itertools.count(1)


def uid():
	return str(uuid.uuid4())


def cairo(day_offset, hour, minute=0):
	"""An instant in Cairo, `day_offset` days from today, as XStudio sends it (ISO, UTC)."""
	day = datetime.now(CAIRO).date() + timedelta(days=day_offset)
	local = datetime.combine(day, time(hour % 24, minute), tzinfo=CAIRO) + timedelta(days=hour // 24)
	return mappers.iso_utc(local)


class FakeXStudio:
	"""XStudio's data and API, in memory. Bookings are filtered and capped exactly as routes.js does."""

	def __init__(self):
		self.halls = [{"id": h, "name": f"Hall {h}", "price_per_hour": 300, "open_minute": 600, "close_minute": 1440, "is_active": True} for h in (1, 3, 4, 5, 6, 8)]
		self.customers = {}  # id -> {name, phone}
		self.bookings = {}  # id -> row
		self.packages = {}  # id -> row (with usage, payments)
		self.logins = 0
		self.fail_with = None  # an HTTP status to answer every call with
		self.down = False
		self.calls = []

	def customer(self, name, phone):
		cid = uid()
		self.customers[cid] = {"name": name, "phone": phone}
		return cid

	def booking(self, customer_id, hall=3, start=(1, 10), end=(1, 12), status="confirmed", **values):
		row = {
			"id": uid(),
			"hall_id": hall,
			"hall_name": f"Hall {hall}",
			"customer_id": customer_id,
			"customer_name": self.customers[customer_id]["name"] if customer_id else values.pop("customer_name", "Walk-in"),
			"customer_phone": self.customers[customer_id]["phone"] if customer_id else values.pop("customer_phone", ""),
			"starts_at": cairo(*start),
			"ends_at": cairo(*end),
			"hours": 2,
			"price_total": 600,
			"package_id": None,
			"package_name": None,
			"hours_deducted": 0,
			"amount_due": 600,
			"amount_paid": 0,
			"payment_status": "unpaid",
			"status": status,
			"session_type": "",
			"booking_type": "session",
			"screen_size": None,
			"cameras": None,
			"deposit_due": 0,
			"price_pending": False,
			"notes": "",
			"created_by": None,
			"created_at": cairo(-1, 9),
			"updated_at": cairo(-1, 9),
			"cancelled_by": None,
			"cancel_note": "",
			"photographer_id": None,
		}
		row.update(values)
		self.bookings[row["id"]] = row
		return row

	def package(self, customer_id, hours=10, remaining=None, price=1700, category="smart", **values):
		row = {
			"id": uid(),
			"customer_id": customer_id,
			"template_id": None,
			"name": "Smart 86 — 10 ساعات",
			"hours_total": hours,
			"hours_remaining": hours if remaining is None else remaining,
			"price": price,
			"payment_status": "unpaid",
			"purchased_at": cairo(-40, 12),
			"expires_at": cairo(300, 12),
			"category": category,
			"paid_total": 0,
			"payments": None,
			"usage": None,
		}
		row.update(values)
		self.packages[row["id"]] = row
		return row

	def use(self, package, booking, hours, reason="booking", when=None):
		row = {"id": uid(), "package_id": package["id"], "booking_id": booking["id"] if booking else None, "hours": hours, "reason": reason, "created_at": when or cairo(-1, 10)}
		package["usage"] = (package["usage"] or []) + [row]
		package["hours_remaining"] = flt(package["hours_remaining"] - hours, 2)
		booking["package_id"], booking["hours_deducted"] = package["id"], flt(booking["hours_deducted"] + hours, 2)
		return row

	def pay(self, package, amount, method="cash"):
		package["payments"] = (package["payments"] or []) + [{"amount": amount, "method": method, "created_at": cairo(-2, 12)}]
		package["paid_total"] = flt(package["paid_total"] + amount, 2)

	def touch(self, booking, **changes):
		booking.update(changes)
		booking["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

	# ---------- the API ----------

	def answer(self, method, path, params=None, body=None, auth=True):
		self.calls.append((method, path, params))
		if self.down:
			raise XStudioError("XStudio did not answer (/api): ConnectTimeout")
		if self.fail_with:
			raise XStudioError(f"XStudio answered {self.fail_with} on {path}: boom")
		if path == "/api/health":
			return {"ok": True}
		if path == "/api/halls":
			return self.halls
		if path == "/api/bookings":
			params = params or {}
			rows = [b for b in self.bookings.values()]
			if params.get("from"):
				rows = [b for b in rows if mappers.parse_instant(b["starts_at"]) >= mappers.parse_instant(params["from"])]
			if params.get("to"):
				rows = [b for b in rows if mappers.parse_instant(b["starts_at"]) < mappers.parse_instant(params["to"])]
			if params.get("customerId"):
				rows = [b for b in rows if b["customer_id"] == params["customerId"]]
			if params.get("status"):
				rows = [b for b in rows if b["status"] == params["status"]]
			rows.sort(key=lambda b: b["starts_at"])
			return [dict(b) for b in rows[: client_module.BOOKINGS_LIMIT]]
		if path.startswith("/api/customers/") and path.endswith("/packages"):
			cid = path.split("/")[3]
			return [dict(p) for p in self.packages.values() if p["customer_id"] == cid]
		if path == "/api/photographers":
			return []
		raise XStudioError(f"XStudio answered 404 on {path}: Not found")

	def login(self, client):
		self.logins += 1
		if self.down:
			raise XStudioError("XStudio did not answer the login: ConnectTimeout")
		if client.settings.get_password("password", raise_exception=False) != PASSWORD:
			raise client_module.XStudioAuthError("XStudio refused the login (401): Invalid credentials")
		client.token = TOKEN
		return TOKEN


class IntegrationTestXStudioSync(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Customer Group", GROUP):
			frappe.get_doc({"doctype": "Customer Group", "customer_group_name": GROUP, "parent_customer_group": "All Customer Groups"}).insert()
		# A booking entered here is priced: the test resources carry a priced item, so the clash test can make one.
		cls.item = "_TEST-XS-HOUR"
		if not frappe.db.exists("Item", cls.item):
			frappe.get_doc({"doctype": "Item", "item_code": cls.item, "item_name": cls.item, "item_group": "الخدمات", "stock_uom": "Nos", "is_stock_item": 0}).insert()
		if not frappe.db.exists("Item Price", {"item_code": cls.item, "price_list": "Standard Selling"}):
			frappe.get_doc({"doctype": "Item Price", "item_code": cls.item, "price_list": "Standard Selling", "price_list_rate": 100}).insert()
		cls.resources = {}
		for hall in (1, 3, 4, 5, 6, 8):
			cls.resources[hall] = cls.resource(f"_Test XStudio Hall {hall}")
		cls.packages_resource = cls.resource("_Test XStudio Packages")
		settings = frappe.get_single("XStudio Settings")
		settings.update(
			{
				"enabled": 1,
				"base_url": "https://xstudio.test",
				"login": "+201000000001",
				"password": PASSWORD,
				"lookback_days": 30,
				"lookahead_days": 60,
				"poll_minutes": 10,
				"customer_group": GROUP,
				"packages_resource": cls.packages_resource,
				"hall_map": [],
			}
		)
		for hall, resource in cls.resources.items():
			settings.append("hall_map", {"hall_id": hall, "hall_name": f"Hall {hall}", "resource": resource})
		settings.save()

	@staticmethod
	def resource(name):
		if frappe.db.exists("Booking Resource", name):
			return name
		return frappe.get_doc(
			{"doctype": "Booking Resource", "resource_name": name, "resource_type": "Studio Service", "cost_center": STUDIO, "item": "_TEST-XS-HOUR"}
		).insert().name

	def setUp(self):
		frappe.db.savepoint("xstudio_test")
		# Bookings a real XStudio put on this site are not the fake's: set aside until the rollback at the end.
		frappe.db.sql("update `tabBooking` set source_system = 'xstudio-set-aside' where source_system = 'xstudio'")
		# Nor is a token a real XStudio gave: the fake logs in itself.
		frappe.db.set_single_value("XStudio Settings", {"token": None, "token_obtained_at": None}, update_modified=False)
		frappe.clear_document_cache("XStudio Settings", "XStudio Settings")
		self.x = FakeXStudio()
		self.patches = [
			patch.object(XStudioClient, "request", lambda c, method, path, params=None, body=None, auth=True, _retry=True: self.fake_request(c, method, path, params, body, auth)),
			patch.object(XStudioClient, "login", lambda c: self.x.login(c)),
		]
		for p in self.patches:
			p.start()
		self.n = next(COUNTER)

	def tearDown(self):
		for p in self.patches:
			p.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="xstudio_test")

	def fake_request(self, client, method, path, params, body, auth):
		"""As the real client does: a call that needs the token logs in first when there is none."""
		if auth and not client.token:
			client.login()
		return self.x.answer(method, path, params, body, auth)

	def phone(self, i):
		return f"0109{self.n:03d}{i:04d}"

	def run_sync(self, **kwargs):
		return sync.run(trigger="test", **kwargs)

	def erp_booking(self, row):
		name = frappe.db.get_value("Booking", {"import_key": mappers.import_key(row["id"])}, "name")
		return frappe.get_doc("Booking", name) if name else None

	def erp_package(self, row):
		name = frappe.db.get_value("Studio Hour Package", {"import_key": mappers.import_key(row["id"])}, "name")
		return frappe.get_doc("Studio Hour Package", name) if name else None

	def counts(self, log):
		return (log.status, log.rows_read, log.inserted, log.updated, log.skipped, log.changed, log.failed)

	# ---------- the definition of done: one run brings bookings, customers and packages ----------

	def test_one_run_brings_the_bookings_their_customers_and_their_packages(self):
		teacher = self.x.customer("_Test Teacher One", self.phone(1))
		package = self.x.package(teacher, hours=10)
		self.x.pay(package, 1000, "instapay")
		session = self.x.booking(teacher, hall=6, start=(2, 14), end=(2, 16), booking_type="smartboard", screen_size=86, price_total=400, amount_due=400)
		self.x.use(package, session, 2)
		session["amount_due"] = 0
		other = self.x.customer("_Test Walk In", self.phone(2))
		walk_in = self.x.booking(other, hall=1, start=(-3, 18), end=(-3, 19), status="completed", amount_paid=300, amount_due=300, payment_status="paid")

		log = self.run_sync()
		self.assertEqual(self.counts(log), ("Completed", 6, 3, 0, 0, 0, 0))  # read: 2 customers, 1 package, 2 bookings, 1 ledger; inserted: 1 package + 2 bookings
		self.assertEqual((log.source_system, log.records_created), ("xstudio", 2 + 1))  # 2 customers made, 1 usage row

		customer = frappe.get_doc("Customer", {"xstudio_customer_id": teacher})
		self.assertEqual((customer.customer_name, customer.customer_group, customer.custom_phone_key, customer.xstudio_needs_review), ("_Test Teacher One", GROUP, "+20" + self.phone(1)[1:], 0))

		booking = self.erp_booking(session)
		self.assertEqual((booking.source, booking.source_system, booking.external_id, booking.import_key), ("Imported", "xstudio", session["id"], f"xstudio:{session['id']}"))
		self.assertEqual((booking.resource, booking.customer, booking.status, booking.xstudio_status), (self.resources[6], customer.name, "Tentative", "confirmed"))
		self.assertEqual((str(booking.from_time), str(booking.to_time), booking.hours, booking.xstudio_crosses_midnight), ("14:00:00", "16:00:00", 2.0, 0))
		self.assertEqual((booking.total_amount, booking.paid_amount, booking.xstudio_price_total, booking.xstudio_amount_due), (0, 0, 400, 0))
		self.assertEqual((booking.xstudio_booking_type, booking.xstudio_screen_size, booking.package_hours), ("smartboard:86", 86, 2))
		self.assertEqual(booking.booking_date, (datetime.now(CAIRO) + timedelta(days=2)).date())
		self.assertTrue(booking.source_payload and booking.source_payload_hash and booking.last_synced_at and booking.source_updated_at)

		erp_package = self.erp_package(package)
		self.assertEqual(booking.hour_package, erp_package.name)
		self.assertEqual((erp_package.docstatus, erp_package.status, erp_package.source, erp_package.unit), (1, "Active", "Imported", "Hour"))
		self.assertEqual((erp_package.hours_purchased, erp_package.hours_used, erp_package.hours_remaining, erp_package.xstudio_balance_matches), (10, 2, 8, 1))
		self.assertEqual((erp_package.xstudio_paid_total, erp_package.xstudio_payment_status), (1000, "unpaid"))
		self.assertIn("1000 (instapay", erp_package.xstudio_payments_summary)
		[usage] = erp_package.usage
		self.assertEqual((usage.booking, usage.hours, usage.balance, usage.external_id), (booking.name, 2, 8, package["usage"][0]["id"]))

		done = self.erp_booking(walk_in)
		self.assertEqual((done.status, done.total_amount, done.paid_amount, done.outstanding_amount, done.xstudio_payment_status), ("Completed", 300, 300, 0, "paid"))
		# Monitoring only: nothing was posted.
		for doctype in ("Payment Entry", "Sales Invoice", "Journal Entry"):
			self.assertFalse(frappe.db.exists(doctype, {"custom_booking": ("in", [booking.name, done.name])}))
		self.assertFalse(frappe.db.exists("Sales Invoice", {"customer": customer.name, "docstatus": 1}))

	def test_running_again_changes_nothing(self):
		teacher = self.x.customer("_Test Teacher Two", self.phone(1))
		self.x.booking(teacher)
		first = self.run_sync()
		before = frappe.db.count("Booking", {"source_system": "xstudio"}), frappe.db.count("Customer", {"xstudio_customer_id": teacher})
		second = self.run_sync()
		self.assertEqual(self.counts(first)[2], 1)
		self.assertEqual(self.counts(second), ("Completed", 2, 0, 0, 1, 0, 0))
		self.assertEqual((frappe.db.count("Booking", {"source_system": "xstudio"}), frappe.db.count("Customer", {"xstudio_customer_id": teacher})), before)
		self.assertEqual(frappe.db.count("Booking", {"import_key": mappers.import_key(list(self.x.bookings)[0])}), 1)

	def test_a_dry_run_says_what_it_would_add_and_keeps_nothing(self):
		teacher = self.x.customer("_Test Teacher Dry", self.phone(1))
		self.x.booking(teacher)
		logs = frappe.db.count("Integration Import Log", {"source_system": "xstudio"})
		attempt = frappe.db.get_single_value("XStudio Settings", "last_attempt_at")
		result = sync.run(trigger="dry run", dry_run=True)
		self.assertTrue(result["dry_run"])
		self.assertEqual(result["counts"]["inserted"], 1)
		self.assertEqual([c["customer_name"] for c in result["would_add"]["customers"]], ["_Test Teacher Dry"])
		self.assertEqual(len(result["would_add"]["bookings"]), 1)
		# Nothing stayed: no booking, no customer, no log, and the settings' last attempt is as it was.
		self.assertEqual(frappe.db.count("Booking", {"import_key": mappers.import_key(list(self.x.bookings)[0])}), 0)
		self.assertEqual(frappe.db.count("Customer", {"xstudio_customer_id": teacher}), 0)
		self.assertEqual(frappe.db.count("Integration Import Log", {"source_system": "xstudio"}), logs)
		self.assertEqual(frappe.db.get_single_value("XStudio Settings", "last_attempt_at"), attempt)
		# A real run after it adds exactly what the dry run said.
		self.assertEqual(self.counts(self.run_sync())[2], 1)

	# ---------- the 30-day window ----------

	def test_only_bookings_of_the_window_are_read(self):
		teacher = self.x.customer("_Test Teacher Window", self.phone(1))
		old = self.x.booking(teacher, start=(-31, 10), end=(-31, 11))
		edge = self.x.booking(teacher, start=(-30, 0), end=(-30, 1))
		soon = self.x.booking(teacher, start=(5, 10), end=(5, 11))
		far = self.x.booking(teacher, start=(61, 10), end=(61, 11))
		self.run_sync()
		self.assertIsNone(self.erp_booking(old))
		self.assertIsNotNone(self.erp_booking(edge))
		self.assertIsNotNone(self.erp_booking(soon))
		self.assertIsNone(self.erp_booking(far))

	def test_a_full_answer_splits_the_window_and_a_span_that_still_fills_is_listed_incomplete(self):
		teacher = self.x.customer("_Test Teacher Many", self.phone(1))
		with patch.object(client_module, "BOOKINGS_LIMIT", 4):
			# 6 bookings over 3 days: one window of 6 > 4 is halved until each answer is under the cap.
			for day in (1, 2, 3):
				self.x.booking(teacher, hall=1, start=(day, 10), end=(day, 11))
				self.x.booking(teacher, hall=3, start=(day, 10), end=(day, 11))
			log = self.run_sync()
			self.assertEqual(log.inserted, 6)
			self.assertEqual(log.failed, 0)
			windows = [c for c in self.x.calls if c[1] == "/api/bookings" and c[2] and c[2].get("from")]
			self.assertGreater(len(windows), 1)
			# 4 bookings in the same hour across halls: the hour cannot be split, so it is listed, not claimed.
			for hall in (4, 5, 6, 8):
				self.x.booking(teacher, hall=hall, start=(4, 10), end=(4, 11))
			log = self.run_sync()
			self.assertEqual(log.status, "Completed with Errors")
			[row] = [r for r in log.errors if "maximum" in r.reason]
			self.assertEqual(row.kind, "Failed")

	# ---------- customers ----------

	def test_a_customer_without_a_usable_phone_is_made_without_one_and_marked(self):
		placeholder = self.x.customer("_Test No Phone", "no-phone-ab12cd34")
		invalid = self.x.customer("_Test Bad Phone", "+200000000000")
		self.x.booking(placeholder, hall=1)
		self.x.booking(invalid, hall=3)
		log = self.run_sync()
		self.assertEqual(log.failed, 0)
		for xid in (placeholder, invalid):
			customer = frappe.get_doc("Customer", {"xstudio_customer_id": xid})
			self.assertEqual((customer.mobile_no or None, customer.custom_phone_key or None, customer.xstudio_needs_review, customer.customer_group), (None, None, 1, GROUP))

	def test_a_customer_already_here_with_the_phone_is_linked_not_duplicated(self):
		existing = frappe.get_doc(
			{"doctype": "Customer", "customer_name": "_Test Already Here", "customer_type": "Individual", "customer_group": GROUP, "mobile_no": self.phone(7)}
		).insert()
		teacher = self.x.customer("_Test Already Here (XStudio)", "+20" + self.phone(7)[1:])
		self.x.booking(teacher)
		self.run_sync()
		self.assertEqual(frappe.db.get_value("Customer", existing.name, "xstudio_customer_id"), teacher)
		self.assertEqual(frappe.db.count("Customer", {"custom_phone_key": "+20" + self.phone(7)[1:]}), 1)

	def test_the_same_phone_on_two_xstudio_customers_fails_the_second_alone(self):
		one = self.x.customer("_Test Phone Owner", self.phone(8))
		two = self.x.customer("_Test Phone Taker", self.phone(8))
		self.x.booking(one, hall=1)
		later = self.x.booking(two, hall=3)
		log = self.run_sync()
		self.assertEqual((log.inserted, log.failed), (1, 2))  # the customer and its booking
		reasons = " ".join(r.reason for r in log.errors)
		self.assertIn("another XStudio customer", reasons)
		self.assertIsNone(self.erp_booking(later))

	# ---------- statuses, money, times ----------

	def test_statuses_follow_xstudio_and_the_deposit(self):
		teacher = self.x.customer("_Test Statuses", self.phone(1))
		pending = self.x.booking(teacher, hall=1, status="pending")
		confirmed = self.x.booking(teacher, hall=3, status="confirmed")
		deposit = self.x.booking(teacher, hall=4, status="confirmed", amount_paid=200, payment_status="partial")
		done = self.x.booking(teacher, hall=5, start=(-1, 10), end=(-1, 12), status="completed", amount_paid=600, payment_status="paid")
		cancelled = self.x.booking(teacher, hall=6, status="cancelled", cancelled_by="customer", cancel_note="sick")
		self.run_sync()
		self.assertEqual(self.erp_booking(pending).status, "Tentative")
		self.assertEqual((self.erp_booking(confirmed).status, self.erp_booking(confirmed).xstudio_status), ("Tentative", "confirmed"))
		self.assertEqual((self.erp_booking(deposit).status, self.erp_booking(deposit).paid_amount), ("Confirmed with Deposit", 200))
		self.assertEqual(self.erp_booking(done).status, "Completed")
		booking = self.erp_booking(cancelled)
		self.assertEqual((booking.status, booking.cancellation_reason, booking.xstudio_cancelled_by), ("Cancelled", "Cancelled in XStudio by the customer: sick", "customer"))

	def test_money_is_read_as_it_is_and_never_posted(self):
		teacher = self.x.customer("_Test Money", self.phone(1))
		discounted = self.x.booking(teacher, hall=1, price_total=600, amount_due=500, amount_paid=500, payment_status="paid")
		pending_price = self.x.booking(teacher, hall=3, price_total=0, amount_due=0, amount_paid=100, price_pending=True, payment_status="paid")
		self.run_sync()
		a = self.erp_booking(discounted)
		self.assertEqual((a.total_amount, a.paid_amount, a.outstanding_amount, a.xstudio_price_total), (500, 500, 0, 600))
		b = self.erp_booking(pending_price)
		# Paid more than is due (the price is still to be agreed): the total is raised to what was paid, and the
		# source figures stay visible.
		self.assertEqual((b.total_amount, b.paid_amount, b.xstudio_amount_due, b.xstudio_price_pending), (100, 100, 0, 1))
		self.assertEqual(frappe.db.count("Payment Entry", {"custom_booking": ("in", [a.name, b.name])}), 0)
		self.assertEqual(frappe.db.count("GL Entry", {"against_voucher": ("in", [a.name, b.name])}), 0)

	def test_a_booking_to_midnight_keeps_its_day_its_exact_end_and_is_marked(self):
		teacher = self.x.customer("_Test Midnight", self.phone(1))
		late = self.x.booking(teacher, hall=1, start=(1, 22), end=(2, 0), hours=2)
		self.run_sync()
		booking = self.erp_booking(late)
		self.assertEqual((str(booking.from_time), str(booking.to_time), booking.xstudio_crosses_midnight, booking.xstudio_hours), ("22:00:00", "23:59:59", 1, 2))
		self.assertEqual(booking.booking_date, (datetime.now(CAIRO) + timedelta(days=1)).date())
		self.assertEqual(booking.xstudio_ends_at, datetime.combine((datetime.now(CAIRO) + timedelta(days=2)).date(), time(0, 0)))
		self.assertEqual(booking.xstudio_starts_at, datetime.combine((datetime.now(CAIRO) + timedelta(days=1)).date(), time(22, 0)))

	def test_times_are_cairo_whatever_the_site_zone(self):
		teacher = self.x.customer("_Test Zone", self.phone(1))
		row = self.x.booking(teacher, starts_at="2026-07-15T09:30:00.000Z", ends_at="2026-07-15T11:00:00.000Z")  # Cairo is UTC+3 in July
		date, start, end, crosses = mappers.booking_times(row)
		self.assertEqual((str(date), str(start), str(end), crosses), ("2026-07-15", "12:30:00", "14:00:00", False))
		row = self.x.booking(teacher, starts_at="2026-12-15T09:30:00.000Z", ends_at="2026-12-15T11:00:00.000Z")  # UTC+2 in December
		self.assertEqual(str(mappers.booking_times(row)[1]), "11:30:00")

	# ---------- changes in XStudio ----------

	def test_a_rescheduled_booking_moves_here_and_an_unchanged_one_is_skipped(self):
		teacher = self.x.customer("_Test Moves", self.phone(1))
		row = self.x.booking(teacher, hall=1, start=(3, 10), end=(3, 12))
		still = self.x.booking(teacher, hall=3)
		self.run_sync()
		self.x.touch(row, starts_at=cairo(4, 15), ends_at=cairo(4, 17))
		log = self.run_sync()
		self.assertEqual((log.updated, log.skipped, log.inserted), (1, 1, 0))
		booking = self.erp_booking(row)
		self.assertEqual((booking.booking_date, str(booking.from_time)), ((datetime.now(CAIRO) + timedelta(days=4)).date(), "15:00:00"))
		self.assertEqual(frappe.db.count("Booking", {"import_key": mappers.import_key(row["id"])}), 1)
		self.assertEqual(self.erp_booking(still).status, "Tentative")

	def test_a_cancellation_in_xstudio_cancels_here_and_gives_the_package_hours_back(self):
		teacher = self.x.customer("_Test Cancels", self.phone(1))
		package = self.x.package(teacher, hours=5)
		row = self.x.booking(teacher, hall=6, booking_type="smartboard", screen_size=86)
		self.x.use(package, row, 2)
		self.run_sync()
		self.assertEqual(self.erp_package(package).hours_remaining, 3)
		self.x.touch(row, status="cancelled", cancelled_by="staff", cancel_note="rain")
		self.x.use(package, row, -2, reason="cancel_refund", when=cairo(0, 9))
		log = self.run_sync()
		self.assertEqual(log.updated, 2)  # the booking and its package
		booking = self.erp_booking(row)
		self.assertEqual((booking.status, booking.cancellation_reason), ("Cancelled", "Cancelled in XStudio by the studio: rain"))
		erp_package = self.erp_package(package)
		self.assertEqual((erp_package.hours_used, erp_package.hours_remaining, len(erp_package.usage), erp_package.xstudio_balance_matches), (0, 5, 2, 1))
		# The freed time can be taken by another XStudio booking.
		again = self.x.booking(teacher, hall=6)
		self.assertEqual(self.run_sync().inserted, 1)
		self.assertIsNotNone(self.erp_booking(again))

	def test_a_completed_session_with_its_payment(self):
		teacher = self.x.customer("_Test Completes", self.phone(1))
		row = self.x.booking(teacher, start=(-1, 10), end=(-1, 12))
		self.run_sync()
		self.x.touch(row, status="completed", amount_paid=600, payment_status="paid")
		self.run_sync()
		booking = self.erp_booking(row)
		self.assertEqual((booking.status, booking.paid_amount, booking.outstanding_amount, booking.xstudio_payment_status), ("Completed", 600, 0, "paid"))
		self.assertIsNone(booking.sales_invoice)
		self.assertEqual(frappe.db.count("Payment Entry", {"custom_booking": booking.name}), 0)

	def test_a_booking_moved_out_of_the_window_is_found_through_its_customer(self):
		teacher = self.x.customer("_Test Far Move", self.phone(1))
		row = self.x.booking(teacher, start=(2, 10), end=(2, 12))
		self.run_sync()
		self.x.touch(row, starts_at=cairo(90, 10), ends_at=cairo(90, 12))
		log = self.run_sync()
		self.assertEqual((log.updated, log.changed), (1, 0))
		booking = self.erp_booking(row)
		self.assertEqual((booking.booking_date, booking.xstudio_not_in_last_fetch), ((datetime.now(CAIRO) + timedelta(days=90)).date(), 0))

	def test_a_booking_xstudio_no_longer_returns_is_kept_and_listed(self):
		teacher = self.x.customer("_Test Vanishes", self.phone(1))
		row = self.x.booking(teacher)
		self.run_sync()
		del self.x.bookings[row["id"]]  # XStudio never does this; a partial or wrong answer looks the same
		log = self.run_sync()
		booking = self.erp_booking(row)
		self.assertEqual((booking.status, booking.xstudio_not_in_last_fetch), ("Tentative", 1))
		self.assertEqual((log.changed, log.status), (1, "Completed with Errors"))
		self.assertEqual([r.kind for r in log.errors], ["Needs Review"])

	# ---------- packages ----------

	def test_a_package_bought_before_the_window_comes_with_its_whole_ledger(self):
		teacher = self.x.customer("_Test Old Package", self.phone(1))
		package = self.x.package(teacher, hours=30, purchased_at=cairo(-200, 12))
		old = self.x.booking(teacher, hall=1, start=(-100, 10), end=(-100, 13), status="completed")  # outside the window
		self.x.use(package, old, 3, when=cairo(-100, 9))
		recent = self.x.booking(teacher, hall=3, start=(-2, 10), end=(-2, 12), status="completed")
		self.x.use(package, recent, 2, when=cairo(-2, 9))
		self.run_sync()
		erp_package = self.erp_package(package)
		self.assertEqual((erp_package.hours_purchased, erp_package.hours_used, erp_package.hours_remaining, erp_package.xstudio_balance_matches), (30, 5, 25, 1))
		self.assertEqual(str(erp_package.purchase_date), str((datetime.now(CAIRO) - timedelta(days=200)).date()))
		[first, second] = erp_package.usage
		self.assertEqual((first.hours, first.booking, first.balance), (3, None, 27))  # its booking is outside the window: not here
		self.assertIn("not imported", first.reason)
		self.assertEqual((second.hours, second.booking, second.balance), (2, self.erp_booking(recent).name, 25))
		self.assertIsNone(self.erp_booking(old))
		# Read again: the ledger rows are not repeated.
		self.run_sync()
		self.assertEqual(len(self.erp_package(package).usage), 2)

	def test_a_balance_edited_by_hand_in_xstudio_is_kept_and_flagged(self):
		teacher = self.x.customer("_Test Hand Edit", self.phone(1))
		package = self.x.package(teacher, hours=10, remaining=7)  # 3 hours gone with no ledger row (PATCH /customer-packages/:id)
		self.x.booking(teacher)
		log = self.run_sync()
		erp_package = self.erp_package(package)
		self.assertEqual((erp_package.hours_remaining, erp_package.xstudio_hours_remaining, erp_package.hours_used, erp_package.xstudio_balance_matches), (7, 7, 0, 0))
		self.assertEqual([r.kind for r in log.errors], ["Needs Review"])
		self.assertIn("edited by hand", log.errors[0].reason)

	def test_a_reels_bundle_counts_reels(self):
		teacher = self.x.customer("_Test Reels", self.phone(1))
		package = self.x.package(teacher, hours=10, category="reels", name="باقة 10 ريلز")
		row = self.x.booking(teacher, booking_type="reels", price_total=500, amount_due=0)
		self.x.use(package, row, 1)
		self.run_sync()
		erp_package = self.erp_package(package)
		self.assertEqual((erp_package.unit, erp_package.hours_remaining), ("Reel", 9))

	def test_an_imported_package_is_not_drawn_on_by_a_booking_entered_here(self):
		teacher = self.x.customer("_Test Protected", self.phone(1))
		package = self.x.package(teacher)
		self.x.booking(teacher)
		self.run_sync()
		erp_package = self.erp_package(package)
		manual = frappe.get_doc(
			{
				"doctype": "Booking",
				"resource": self.packages_resource,
				"customer": erp_package.customer,
				"booking_date": (datetime.now(CAIRO) + timedelta(days=9)).date(),
				"from_time": "10:00",
				"to_time": "11:00",
				"hour_package": erp_package.name,
			}
		)
		self.assertRaisesRegex(frappe.ValidationError, "Book the session there", manual.insert)

	# ---------- XStudio is the owner ----------

	def test_an_imported_booking_is_not_changed_here(self):
		teacher = self.x.customer("_Test Owner", self.phone(1))
		row = self.x.booking(teacher)
		self.run_sync()
		booking = self.erp_booking(row)
		booking.status, booking.cancellation_reason = "Cancelled", "x"
		self.assertRaisesRegex(frappe.ValidationError, "Change it there", booking.save)
		self.assertEqual(frappe.db.get_value("Booking", booking.name, "status"), "Tentative")

	def test_an_imported_package_is_not_changed_here(self):
		teacher = self.x.customer("_Test Owner P", self.phone(1))
		package = self.x.package(teacher)
		self.x.booking(teacher)
		self.run_sync()
		erp_package = self.erp_package(package)
		erp_package.notes = "changed here"
		self.assertRaises(frappe.ValidationError, erp_package.save)  # submitted, and imported
		erp_package = self.erp_package(package)
		erp_package.cancel_reason = "cancelled here"
		self.assertRaisesRegex(frappe.ValidationError, "Change it there", erp_package.cancel)
		self.assertEqual(frappe.db.get_value("Studio Hour Package", erp_package.name, ["docstatus", "status"]), (1, "Active"))

	def test_a_manual_booking_in_the_way_fails_the_xstudio_row_alone(self):
		teacher = self.x.customer("_Test Clash", self.phone(1))
		frappe.get_doc(
			{
				"doctype": "Booking",
				"resource": self.resources[1],
				"customer": frappe.get_all("Customer", filters={"customer_group": GROUP}, limit=1, pluck="name")[0] if frappe.db.exists("Customer", {"customer_group": GROUP}) else self.manual_customer(),
				"booking_date": (datetime.now(CAIRO) + timedelta(days=1)).date(),
				"from_time": "10:00",
				"to_time": "11:00",
			}
		).insert()
		clash = self.x.booking(teacher, hall=1, start=(1, 10), end=(1, 12))
		free = self.x.booking(teacher, hall=3, start=(1, 10), end=(1, 12))
		log = self.run_sync()
		self.assertEqual((log.inserted, log.failed), (1, 1))
		self.assertIn("already booked", log.errors[0].reason)
		self.assertIsNone(self.erp_booking(clash))
		self.assertIsNotNone(self.erp_booking(free))

	def manual_customer(self):
		return frappe.get_doc({"doctype": "Customer", "customer_name": "_Test Manual Studio Customer", "customer_type": "Individual", "customer_group": GROUP}).insert().name

	def test_lecture_halls_are_untouched(self):
		before = frappe.db.count("Booking", {"resource_type": "Hall"})
		teacher = self.x.customer("_Test Separation", self.phone(1))
		self.x.booking(teacher)
		self.run_sync()
		self.assertEqual(frappe.db.count("Booking", {"resource_type": "Hall"}), before)
		self.assertEqual(frappe.db.count("Booking", {"source_system": "xstudio", "cost_center": ("!=", STUDIO)}), 0)

	def test_an_unmapped_hall_fails_its_booking_with_a_clear_reason(self):
		teacher = self.x.customer("_Test Unmapped", self.phone(1))
		self.x.booking(teacher, hall=9)
		log = self.run_sync()
		self.assertEqual(log.failed, 1)
		self.assertIn("hall 9 is not mapped", log.errors[0].reason)

	# ---------- when XStudio cannot be read ----------

	def test_xstudio_down_fails_the_run_and_keeps_what_was_imported(self):
		teacher = self.x.customer("_Test Down", self.phone(1))
		row = self.x.booking(teacher)
		self.run_sync()
		self.x.down = True
		log = self.run_sync()
		self.assertEqual((log.status, log.inserted), ("Failed", 0))
		self.assertIn("did not answer", log.message)
		self.assertIsNotNone(self.erp_booking(row))
		self.assertEqual(self.erp_booking(row).status, "Tentative")
		settings = frappe.get_single("XStudio Settings")
		self.assertEqual((settings.consecutive_failures, settings.health), (1, "Degraded"))
		self.x.down = False
		self.run_sync()
		self.assertEqual((frappe.get_single("XStudio Settings").consecutive_failures, frappe.get_single("XStudio Settings").health), (0, "Healthy"))

	def test_a_wrong_password_fails_the_run_with_the_reason(self):
		settings = frappe.get_single("XStudio Settings")
		settings.password = "wrong-password"
		settings.save()
		teacher = self.x.customer("_Test Auth", self.phone(1))
		self.x.booking(teacher)
		log = self.run_sync()
		self.assertEqual(log.status, "Failed")
		self.assertIn("refused the login", log.message)
		settings.password = PASSWORD
		settings.save()

	def test_an_http_error_on_a_customer_s_packages_fails_that_customer_only(self):
		teacher = self.x.customer("_Test Partial", self.phone(1))
		self.x.package(teacher)
		row = self.x.booking(teacher)
		original = self.x.answer

		def flaky(method, path, params=None, body=None, auth=True):
			if path.endswith("/packages"):
				raise XStudioError(f"XStudio answered 500 on {path}: Internal server error")
			return original(method, path, params, body, auth)

		with patch.object(self.x, "answer", flaky):
			log = self.run_sync()
		self.assertEqual((log.status, log.inserted, log.failed), ("Completed with Errors", 1, 1))
		self.assertIsNotNone(self.erp_booking(row))
		self.assertIn("500", log.errors[0].reason)

	def test_two_runs_at_once_the_second_is_refused(self):
		self.assertTrue(sync.acquire_lock())
		with patch.object(sync, "acquire_lock", return_value=False):
			self.assertRaisesRegex(frappe.ValidationError, "already running", self.run_sync)
		sync.release_lock()

	def test_the_sync_runs_only_when_enabled_and_when_it_is_time(self):
		frappe.db.set_single_value("XStudio Settings", "enabled", 0)
		self.assertRaisesRegex(frappe.ValidationError, "not enabled", self.run_sync)
		self.assertIsNone(sync.run_scheduled())
		frappe.db.set_single_value("XStudio Settings", "enabled", 1)
		frappe.db.set_single_value("XStudio Settings", "last_attempt_at", frappe.utils.now_datetime())
		self.assertIsNone(sync.run_scheduled())  # ran a moment ago
		frappe.db.set_single_value("XStudio Settings", "last_attempt_at", frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-11))
		self.assertIsNotNone(sync.run_scheduled())

	def test_the_log_and_the_status_screen_show_the_run(self):
		teacher = self.x.customer("_Test Shown", self.phone(1))
		self.x.booking(teacher)
		log = self.run_sync()
		self.assertEqual((log.source_system, log.run_by), ("xstudio", "Administrator"))
		self.assertIn("XStudio bookings starting", log.file_name)
		from imed_erp.imederp.report.integration_status.integration_status import get_data

		[row] = [r for r in get_data() if r["system"] == "xstudio"]
		self.assertEqual((row["log"], row["status"], row["inserted"]), (log.name, "Completed", 1))

	def test_who_may_sync_by_hand(self):
		frappe.set_user("gilan@imed.local")  # the studio's branch manager: not an owner nor the accountant
		self.assertRaises(frappe.PermissionError, sync.sync_now)
		frappe.set_user("Administrator")

	# ---------- the mappers on their own ----------

	def test_status_mapping(self):
		self.assertEqual(mappers.booking_status({"status": "pending", "amount_paid": 500}), "Tentative")
		self.assertEqual(mappers.booking_status({"status": "confirmed", "amount_paid": 0}), "Tentative")
		self.assertEqual(mappers.booking_status({"status": "confirmed", "amount_paid": 50}), "Confirmed with Deposit")
		self.assertEqual(mappers.booking_status({"status": "completed", "amount_paid": 0}), "Completed")
		self.assertEqual(mappers.booking_status({"status": "cancelled"}), "Cancelled")
		self.assertRaises(ValueError, mappers.booking_status, {"status": "no_show"})

	def test_payload_hash_ignores_join_fields_and_key_order(self):
		a = {"id": "1", "status": "confirmed", "hall_name": "Hall 3", "amount_paid": 0}
		b = {"amount_paid": 0, "hall_name": "Hall 3 (renamed)", "status": "confirmed", "id": "1"}
		self.assertEqual(mappers.booking_payload_hash(a), mappers.booking_payload_hash(b))
		self.assertNotEqual(mappers.booking_payload_hash(a), mappers.booking_payload_hash({**a, "amount_paid": 1}))

	def test_window_edges_are_cairo_midnights(self):
		start, end = mappers.window_edges(datetime(2026, 10, 24).date(), 30, 60)
		self.assertEqual((start.isoformat(), end.isoformat()), ("2026-09-24T00:00:00+03:00", "2026-12-24T00:00:00+02:00"))
