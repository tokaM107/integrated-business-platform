# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A booking's price and money (HAL-03, HAL-08, HAL-11, HAL-12, STU-03, STU-04, STU-05, STU-14, ACC-04): prices from
# the price lists, packages and extras, the halls' two rental models, deposits into the business's own cash box, the
# invoice made once when the booking is completed, and the one overlap check for manual and imported bookings.
# Real company, accounts and cost centers; test items, prices and parties; rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_booking_pricing

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from imed_erp.imederp.booking_accounts import make_booking_invoice, record_payment
from imed_erp.imederp.booking_import import import_bookings
from imed_erp.imederp.booking_pricing import revenue_share

# A test module outside a doctype folder builds no "_Test ..." records; keep it here, not under a doctype.
HALLS, STUDIO, MAIN = "قاعات Imed - MMG", "استوديو X - MMG", "الإدارة الرئيسية - MMG"
HALL_BOX, STUDIO_BOX, INSTAPAY = "خزينة سنتر Imed - MMG", "خزينة X Studio - MMG", "محفظة InstaPay - MMG"
HALL_INCOME, STUDIO_INCOME, LECTURERS = (
	"إيراد القاعات - MMG",
	"إيراد X Studio - MMG",
	"مستحقات للمحاضرين - MMG",
)
HALL_CASH, STUDIO_CASH = "نقدي — قاعات Imed", "نقدي — استوديو X"
NOUR, GILAN = "nour@imed.local", "gilan@imed.local"
DAY = add_days(today(), 7)
PAST = add_days(today(), -2)
STANDARD = "Standard Selling"
PHONE = "01055556666"
STUDENTS = "_Test Booking Students"


class IntegrationTestBookingPricing(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		if not frappe.db.exists("Price List", STUDENTS):
			frappe.get_doc(
				{"doctype": "Price List", "price_list_name": STUDENTS, "selling": 1, "currency": "EGP"}
			).insert()
		if not frappe.db.exists("Customer Group", STUDENTS):
			frappe.get_doc(
				{
					"doctype": "Customer Group",
					"customer_group_name": STUDENTS,
					"parent_customer_group": "All Customer Groups",
					"default_price_list": STUDENTS,
				}
			).insert()
		prices = {
			"_TEST-HALL-HOUR": [(STANDARD, 300), (STUDENTS, 200)],
			"_TEST-SB86-5H": [(STANDARD, 1150)],
			"_TEST-SB75-HOUR": [(STANDARD, 200)],
			"_TEST-PODCAST-2CAM": [(STANDARD, 1750)],
			"_TEST-MIC": [(STANDARD, 50)],
			"_TEST-LIGHT": [(STANDARD, 50)],
			"_TEST-FLAT": [(STANDARD, 120)],
			"_TEST-NO-PRICE": [],
		}
		# Counted in whole units (Nos), the harder case: a part of an hour still bills the booking's amount
		# (test_part_of_an_hour_is_invoiced_whatever_the_items_unit; a booking of 40 minutes is 0.67 of an hour).
		for item, rates in prices.items():
			if not frappe.db.exists("Item", item):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": item,
						"item_name": item,
						"item_group": "الخدمات",
						"stock_uom": "Nos",
						"is_stock_item": 0,
					}
				).insert()
			for price_list, rate in rates:
				frappe.get_doc(
					{
						"doctype": "Item Price",
						"item_code": item,
						"price_list": price_list,
						"price_list_rate": rate,
					}
				).insert()

		cls.hall = cls.make(
			"Booking Resource",
			resource_name="_Test Priced Hall",
			resource_type="Hall",
			cost_center=HALLS,
			capacity=40,
			item="_TEST-HALL-HOUR",
		)
		cls.sb86 = cls.make(
			"Booking Resource",
			resource_name="_Test Smart Board 86",
			resource_type="Studio Service",
			cost_center=STUDIO,
		)
		cls.sb75 = cls.make(
			"Booking Resource",
			resource_name="_Test Smart Board 75",
			resource_type="Studio Service",
			cost_center=STUDIO,
			item="_TEST-SB75-HOUR",
		)
		cls.podcast = cls.make(
			"Booking Resource",
			resource_name="_Test Priced Podcast",
			resource_type="Studio Service",
			cost_center=STUDIO,
		)
		cls.unpriced = cls.make(
			"Booking Resource",
			resource_name="_Test Unpriced Room",
			resource_type="Studio Service",
			cost_center=STUDIO,
			item="_TEST-NO-PRICE",
		)
		cls.no_box = cls.make(
			"Booking Resource",
			resource_name="_Test Room Without Cash Box",
			resource_type="Studio Service",
			cost_center=MAIN,
			item="_TEST-SB75-HOUR",
		)
		cls.five_hours = cls.make(
			"Booking Package",
			package_name="_Test Smart Board 86 — 5 Hours",
			resource=cls.sb86,
			item="_TEST-SB86-5H",
			charged="Once",
			hours=5,
		)
		cls.two_cameras = cls.make(
			"Booking Package",
			package_name="_Test Podcast — 2 Cameras",
			resource=cls.podcast,
			item="_TEST-PODCAST-2CAM",
			charged="Per Hour",
		)
		cls.mic = cls.make(
			"Booking Extra",
			extra_name="_Test Microphone",
			item="_TEST-MIC",
			charged="Per Piece per Hour",
			applies_to="Hall and Studio",
		)
		cls.light = cls.make(
			"Booking Extra",
			extra_name="_Test Lighting",
			item="_TEST-LIGHT",
			charged="Per Piece per Hour",
			applies_to="Studio Service",
		)
		cls.flat = cls.make(
			"Booking Extra",
			extra_name="_Test Flat Extra",
			item="_TEST-FLAT",
			charged="Per Piece",
			applies_to="Hall and Studio",
		)
		cls.unpriced_extra = cls.make(
			"Booking Extra",
			extra_name="_Test Unpriced Extra",
			item="_TEST-NO-PRICE",
			charged="Per Piece",
			applies_to="Hall and Studio",
		)
		group = frappe.get_all(
			"Customer Group",
			filters={"is_group": 0, "name": ["not in", [STUDENTS, "طبيب"]]},
			limit=1,
			pluck="name",
		)[0]
		territory = frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0]
		cls.customer = cls.make(
			"Customer",
			customer_name="_Test Pricing Customer",
			customer_type="Individual",
			customer_group=group,
			territory=territory,
		)
		cls.student = cls.make(
			"Customer",
			customer_name="_Test Pricing Student",
			customer_type="Individual",
			customer_group=STUDENTS,
			territory=territory,
		)
		cls.lecturer = cls.make("Supplier", supplier_name="_Test Lecturer", supplier_group="Services")
		# The import finds its customer by phone (CRM-04).
		cls.phoned = cls.make(
			"Customer",
			customer_name="_Test Pricing Phoned",
			customer_type="Individual",
			customer_group=group,
			territory=territory,
			mobile_no=PHONE,
		)

	@staticmethod
	def make(doctype, **values):
		return frappe.get_doc({"doctype": doctype, **values}).insert().name

	def setUp(self):
		frappe.db.savepoint("booking_pricing_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="booking_pricing_test")

	def book(
		self, resource=None, start="10:00", end="12:00", date=DAY, extras=(), user="Administrator", **values
	):
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
					"extras": [{"extra": extra, "quantity": qty} for extra, qty in extras],
					**(
						{
							"activity": "Anatomy lecture",
							"responsible_name": "د. أحمد",
							"responsible_phone": "01112223333",
							"rental_model": "Fixed Rent",
						}
						if hall
						else {}
					),
					**values,
				}
			).insert()
		finally:
			frappe.set_user("Administrator")

	def complete(self, booking, **values):
		"""Completed, then posted: the studio posts on completion; a hall posts only when asked (27 Oct 2026), so the
		explicit action follows, as the button on the form does."""
		booking.reload()
		booking.update({"status": "Completed", **values})
		booking.save()
		if booking.resource_type == "Hall":
			make_booking_invoice(booking.name)
		booking.reload()
		return booking

	def invoices(self, booking):
		return frappe.get_all(
			"Sales Invoice", filters={"custom_booking": booking, "docstatus": 1}, pluck="name"
		)

	# ---------- HAL-03: by resource, hours and customer category ----------

	def test_a_hall_is_priced_by_its_hours_and_the_customer_category(self):
		booking = self.book(start="10:00", end="12:00")
		self.assertEqual(
			(booking.rate, booking.base_amount, booking.total_amount, booking.price_list),
			(300, 600, 600, STANDARD),
		)
		self.assertIn("300", booking.pricing_note)
		student = self.book(start="13:00", end="14:30", customer=self.student)
		self.assertEqual(
			(student.rate, student.hours, student.total_amount, student.price_list), (200, 1.5, 300, STUDENTS)
		)
		# The category's list has no price for the extra: the default list's is used, and said.
		with_extra = self.book(start="15:00", end="16:00", customer=self.student, extras=[(self.mic, 1)])
		self.assertEqual(with_extra.extras_amount, 50)

	def test_a_price_is_kept_and_found_again_only_when_the_booking_changes(self):
		booking = self.book(start="10:00", end="12:00")
		frappe.db.set_value(
			"Item Price", {"item_code": "_TEST-HALL-HOUR", "price_list": STANDARD}, "price_list_rate", 350
		)
		booking.notes = "ok"
		booking.save()
		self.assertEqual(booking.total_amount, 600)  # priced already: the new price list does not change it
		booking.to_time = "13:00"
		booking.save()
		self.assertEqual((booking.rate, booking.total_amount), (350, 1050))

	def test_no_price_is_refused_not_zero(self):
		self.assertRaisesRegex(frappe.ValidationError, "has no price", self.book, self.unpriced)
		self.assertRaisesRegex(frappe.ValidationError, "no price by the hour", self.book, self.sb86)
		self.assertRaisesRegex(
			frappe.ValidationError, "has no price", self.book, self.sb75, extras=[(self.unpriced_extra, 1)]
		)

	def test_typed_amounts_are_not_taken(self):
		"""Through the API: the total and the amount paid of a manual booking are worked out, never sent."""
		booking = self.book(start="10:00", end="12:00", total_amount=1, paid_amount=600, outstanding_amount=0)
		self.assertEqual(
			(booking.total_amount, booking.paid_amount, booking.outstanding_amount), (600, 0, 600)
		)

	# ---------- STU-05: packages ----------

	def test_a_package_is_its_price_for_up_to_its_hours(self):
		booking = self.book(self.sb86, start="10:00", end="15:00", package=self.five_hours)
		self.assertEqual((booking.rate, booking.base_amount, booking.total_amount), (1150, 1150, 1150))
		shorter = self.book(self.sb86, start="16:00", end="20:00", package=self.five_hours)
		self.assertEqual(shorter.total_amount, 1150)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"covers up to 5",
			self.book,
			self.sb86,
			start="08:00",
			end="14:00",
			date=add_days(DAY, 1),
			package=self.five_hours,
		)
		# Extras come on top, once; the package is not counted again.
		with_extras = self.book(
			self.sb86,
			start="10:00",
			end="15:00",
			date=add_days(DAY, 2),
			package=self.five_hours,
			extras=[(self.mic, 1)],
		)
		self.assertEqual(
			(with_extras.base_amount, with_extras.extras_amount, with_extras.total_amount), (1150, 250, 1400)
		)

	def test_a_package_per_hour_and_wrong_packages(self):
		booking = self.book(self.podcast, start="10:00", end="12:00", package=self.two_cameras)
		self.assertEqual((booking.rate, booking.total_amount), (1750, 3500))
		self.assertRaisesRegex(
			frappe.ValidationError, "is for", self.book, self.sb75, package=self.five_hours
		)
		frappe.db.set_value("Booking Package", self.five_hours, "disabled", 1)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"disabled",
			self.book,
			self.sb86,
			start="10:00",
			end="15:00",
			package=self.five_hours,
		)

	# ---------- STU-04, HAL-11: extras ----------

	def test_extras(self):
		one = self.book(self.sb75, start="10:00", end="11:00", extras=[(self.mic, 1)])
		self.assertEqual((one.base_amount, one.extras_amount, one.total_amount), (200, 50, 250))
		two = self.book(self.sb75, start="11:00", end="12:00", extras=[(self.mic, 2)])
		self.assertEqual(two.extras_amount, 100)
		# 50 a piece an hour: two lights for two hours.
		lights = self.book(self.sb75, start="12:00", end="14:00", extras=[(self.light, 2), (self.flat, 1)])
		self.assertEqual(lights.extras_amount, 50 * 2 * 2 + 120)
		row = lights.extras[0]
		self.assertEqual(
			(row.rate, row.hours, row.amount, row.charged, row.item),
			(50, 2, 200, "Per Piece per Hour", "_TEST-LIGHT"),
		)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"listed twice",
			self.book,
			self.sb75,
			start="15:00",
			end="16:00",
			extras=[(self.mic, 1), (self.mic, 1)],
		)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"more than zero",
			self.book,
			self.sb75,
			start="15:00",
			end="16:00",
			extras=[(self.mic, 0)],
		)
		# Lighting is the studio's: not on a hall booking.
		self.assertRaisesRegex(frappe.ValidationError, "not offered", self.book, extras=[(self.light, 1)])

	# ---------- STU-03, ACC-04: the deposit (the requirements' example) ----------

	def test_the_smart_board_example(self):
		"""Smart board 86", 5 hours, 1,150; a deposit of 500 leaves 650."""
		booking = self.book(self.sb86, start="10:00", end="15:00", package=self.five_hours)
		payment = record_payment(booking.name, 500, request_id="test-deposit-1")
		booking.reload()
		self.assertEqual(
			(booking.total_amount, booking.paid_amount, booking.outstanding_amount), (1150, 500, 650)
		)
		self.assertEqual(booking.status, "Confirmed with Deposit")
		entry = frappe.get_doc("Payment Entry", payment)
		self.assertEqual(
			(
				entry.docstatus,
				entry.payment_type,
				entry.party_type,
				entry.party,
				entry.paid_to,
				entry.custom_booking,
				entry.unallocated_amount,
				entry.cost_center,
			),
			(1, "Receive", "Customer", self.customer, STUDIO_BOX, booking.name, 500, STUDIO),
		)
		self.assertNotEqual(entry.paid_to, HALL_BOX)
		# The same request again (a double click, a retry): no second deposit.
		self.assertEqual(record_payment(booking.name, 500, request_id="test-deposit-1"), payment)
		self.assertEqual(
			frappe.db.count("Payment Entry", {"custom_booking": booking.name, "docstatus": 1}), 1
		)
		self.assertRaisesRegex(
			frappe.ValidationError, "more than what is left", record_payment, booking.name, 700
		)
		self.assertRaisesRegex(frappe.ValidationError, "more than zero", record_payment, booking.name, 0)
		# Its total cannot drop below what was paid.
		booking.reload()
		booking.package, booking.from_time, booking.to_time = None, "10:00", "11:00"
		booking.resource = self.sb75
		self.assertRaisesRegex(frappe.ValidationError, "more than its new total", booking.save)

	def test_a_cancelled_deposit_is_taken_off(self):
		booking = self.book(self.sb86, start="10:00", end="15:00", package=self.five_hours)
		payment = frappe.get_doc("Payment Entry", record_payment(booking.name, 500))
		payment.cancel()
		booking.reload()
		self.assertEqual(
			(booking.paid_amount, booking.outstanding_amount, booking.status), (0, 1150, "Tentative")
		)

	# ---------- ACC-04: each business's cash box ----------

	def test_each_business_its_cash_box(self):
		studio = self.book(self.sb75, start="10:00", end="12:00")
		self.assertEqual(studio.treasury, STUDIO_BOX)
		self.assertRaisesRegex(
			frappe.ValidationError, "not .*cash box", record_payment, studio.name, 100, HALL_CASH
		)
		# The group's wallets take any business's money (CORE-03).
		self.assertRaisesRegex(
			frappe.ValidationError, "transaction number", record_payment, studio.name, 100, "InstaPay"
		)
		wallet = record_payment(studio.name, 100, "InstaPay", reference_no="IP-123")
		self.assertEqual(frappe.db.get_value("Payment Entry", wallet, "paid_to"), INSTAPAY)
		self.assertEqual(self.book(start="10:00", end="12:00").treasury, HALL_BOX)
		# A business without its cash box set: told when the booking is saved.
		self.assertRaisesRegex(frappe.ValidationError, "has no cash box", self.book, self.no_box)

	def test_a_branch_manager_records_only_her_business_payments(self):
		studio = self.book(self.sb75, start="10:00", end="12:00")
		frappe.set_user(GILAN)
		payment = record_payment(studio.name, 100)
		frappe.set_user(NOUR)
		self.assertRaises(frappe.PermissionError, record_payment, studio.name, 100)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Payment Entry", payment, "paid_to"), STUDIO_BOX)

	# ---------- The invoice when completed ----------

	def test_completed_makes_the_invoice_once_with_the_deposit(self):
		booking = self.book(
			self.sb86, start="10:00", end="15:00", date=PAST, package=self.five_hours, extras=[(self.mic, 1)]
		)
		record_payment(booking.name, 500)
		booking = self.complete(booking)
		[name] = self.invoices(booking.name)
		invoice = frappe.get_doc("Sales Invoice", name)
		self.assertEqual(booking.sales_invoice, name)
		self.assertEqual(
			(invoice.customer, invoice.grand_total, invoice.total_advance, invoice.outstanding_amount),
			(self.customer, 1400, 500, 900),
		)
		self.assertEqual(
			{
				(row.item_code, row.qty, row.rate, row.income_account, row.cost_center)
				for row in invoice.items
			},
			{("_TEST-SB86-5H", 1, 1150, STUDIO_INCOME, STUDIO), ("_TEST-MIC", 5, 50, STUDIO_INCOME, STUDIO)},
		)
		self.assertEqual((booking.paid_amount, booking.outstanding_amount), (500, 900))
		# Saved again, or asked again: no second invoice.
		booking.notes = "again"
		booking.save()
		make_booking_invoice(booking.name)
		self.assertEqual(len(self.invoices(booking.name)), 1)
		# The rest paid against the invoice, into the studio's cash box.
		payment = frappe.get_doc("Payment Entry", record_payment(booking.name, 900))
		self.assertEqual((payment.references[0].reference_name, payment.paid_to), (name, STUDIO_BOX))
		booking.reload()
		self.assertEqual((booking.paid_amount, booking.outstanding_amount), (1400, 0))
		self.assertEqual(frappe.db.get_value("Sales Invoice", name, "outstanding_amount"), 0)
		# What the invoice was made from does not change while it stands.
		booking.to_time = "14:00"
		self.assertRaisesRegex(frappe.ValidationError, "Cancel it first", booking.save)

	def test_a_cancelled_invoice_is_made_again(self):
		booking = self.book(self.sb75, start="10:00", end="12:00", date=PAST)
		booking = self.complete(booking)
		invoice = frappe.get_doc("Sales Invoice", booking.sales_invoice)
		invoice.cancel_reason = "Wrong hours"
		invoice.cancel()
		booking.reload()
		self.assertFalse(booking.sales_invoice)
		booking.to_time = "11:00"
		booking.save()
		result = make_booking_invoice(booking.name)
		self.assertEqual(frappe.db.get_value("Sales Invoice", result.sales_invoice, "grand_total"), 200)

	def test_an_invoice_with_a_deposit_is_cancelled_and_made_again(self):
		"""Correcting a completed booking that had a deposit: cancelling its invoice gives the deposit back to the
		booking, and the new invoice takes it off again."""
		booking = self.book(self.sb75, start="10:00", end="12:00", date=PAST)
		record_payment(booking.name, 150)
		booking = self.complete(booking)
		invoice = frappe.get_doc("Sales Invoice", booking.sales_invoice)
		invoice.cancel_reason = "Wrong hours"
		invoice.cancel()
		booking.reload()
		self.assertEqual(
			(booking.sales_invoice, booking.paid_amount, booking.outstanding_amount), (None, 150, 250)
		)
		booking.to_time = "11:00"
		booking.save()
		result = make_booking_invoice(booking.name)
		again = frappe.get_doc("Sales Invoice", result.sales_invoice)
		self.assertEqual((again.grand_total, again.total_advance, again.outstanding_amount), (200, 150, 50))

	def test_part_of_an_hour_is_invoiced_whatever_the_items_unit(self):
		"""90 minutes, priced by an item counted in whole units (Nos): the invoice still carries the booking's amount."""
		booking = self.book(self.sb75, start="10:00", end="11:30", date=PAST, extras=[(self.mic, 1)])
		self.assertEqual(
			(booking.hours, booking.base_amount, booking.extras_amount, booking.total_amount),
			(1.5, 300, 75, 375),
		)
		booking = self.complete(booking)
		invoice = frappe.get_doc("Sales Invoice", booking.sales_invoice)
		self.assertEqual(invoice.grand_total, 375)
		self.assertEqual(sorted(flt(row.amount) for row in invoice.items), [75, 300])

	def test_a_branch_manager_completes_her_business_booking(self):
		"""Gilan marks the studio's booking completed: its invoice is made (in the system's name), and her deposit is
		taken off it."""
		booking = self.book(self.sb75, start="10:00", end="12:00", date=PAST, user=GILAN)
		frappe.set_user(GILAN)
		record_payment(booking.name, 100)
		booking = frappe.get_doc("Booking", booking.name)
		booking.status = "Completed"
		booking.save()
		frappe.set_user("Administrator")
		booking.reload()
		invoice = frappe.get_doc("Sales Invoice", booking.sales_invoice)
		self.assertEqual(
			(invoice.docstatus, invoice.grand_total, invoice.total_advance, invoice.outstanding_amount),
			(1, 400, 100, 300),
		)
		self.assertEqual(booking.outstanding_amount, 300)

	# ---------- HAL-12: fixed rent ----------

	def test_fixed_rent(self):
		booking = self.book(
			start="10:00",
			end="12:00",
			date=PAST,
			attendees=30,
			collected_amount=999,
			lecturer_share_percent=40,
		)
		self.assertEqual(
			(booking.total_amount, booking.lecturer_share, booking.center_share, booking.collected_amount),
			(600, 0, 0, 0),
		)
		# A hall takes no deposit (requirements 4.9, question 2).
		self.assertRaisesRegex(frappe.ValidationError, "no deposit", record_payment, booking.name, 100)
		booking = self.complete(booking)
		invoice = frappe.get_doc("Sales Invoice", booking.sales_invoice)
		self.assertEqual(
			(invoice.grand_total, invoice.items[0].income_account, invoice.items[0].cost_center),
			(600, HALL_INCOME, HALLS),
		)
		self.assertFalse(booking.journal_entry)
		# The studio's cash box never takes a hall's money.
		self.assertRaisesRegex(
			frappe.ValidationError, "not .*cash box", record_payment, booking.name, 100, STUDIO_CASH
		)
		payment = record_payment(booking.name, 600)
		self.assertEqual(frappe.db.get_value("Payment Entry", payment, "paid_to"), HALL_BOX)
		booking.reload()
		self.assertEqual(booking.outstanding_amount, 0)
		self.assertRaisesRegex(
			frappe.ValidationError, "rental model", self.book, start="13:00", end="14:00", rental_model=""
		)

	# ---------- HAL-08, HAL-12: revenue share ----------

	def test_revenue_share(self):
		share = dict(rental_model="Revenue Share", attendees=30, admission_price=100, collected_amount=2500)
		booking = self.book(start="10:00", end="12:00", date=PAST, extras=[(self.mic, 1)], **share)
		self.assertEqual(
			(booking.expected_revenue, booking.base_amount, booking.extras_amount, booking.total_amount),
			(3000, 0, 100, 100),
		)
		# The lecturer's share is agreed per booking, never assumed: no completing without it, nor without the lecturer.
		self.assertRaisesRegex(frappe.ValidationError, "Share %", self.complete, booking)
		self.assertRaisesRegex(
			frappe.ValidationError, "Lecturer", self.complete, booking, lecturer_share_percent=40
		)
		booking = self.complete(booking, lecturer_share_percent=40, lecturer=self.lecturer)
		self.assertEqual((booking.lecturer_share, booking.center_share), (1000, 1500))
		entry = frappe.get_doc("Journal Entry", booking.journal_entry)
		rows = {
			(r.account, r.debit, r.credit, r.party_type or None, r.party or None, r.cost_center)
			for r in entry.accounts
		}
		self.assertEqual(
			rows,
			{
				(HALL_BOX, 2500, 0, None, None, HALLS),
				(HALL_INCOME, 0, 1500, None, None, HALLS),
				(LECTURERS, 0, 1000, "Supplier", self.lecturer, HALLS),
			},
		)
		# The extras are the customer's to pay, on an invoice of their own.
		self.assertEqual(frappe.db.get_value("Sales Invoice", booking.sales_invoice, "grand_total"), 100)
		self.assertEqual(entry.custom_booking, booking.name)
		# Saved again: no second entry.
		booking.notes = "again"
		booking.save()
		self.assertEqual(
			frappe.db.count("Journal Entry", {"custom_booking": booking.name, "docstatus": 1}), 1
		)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"no rent",
			self.book,
			start="13:00",
			end="14:00",
			package=self.five_hours,
			**share,
		)

	def test_the_shares_always_add_up(self):
		self.assertEqual(revenue_share(2500, 40), (1000, 1500))
		self.assertEqual(revenue_share(100.01, 33.33), (33.33, 66.68))
		self.assertEqual(revenue_share(999, 0), (0, 999))
		self.assertEqual(revenue_share(0, 50), (0, 0))
		self.assertEqual(sum(revenue_share(1234.57, 37.5)), 1234.57)

	# ---------- STU-14: one overlap check for manual and imported bookings ----------

	def test_manual_and_imported_bookings_are_checked_alike(self):
		imported = import_bookings(
			"studio_booking",
			[
				{
					"external_id": "P1",
					"resource": self.sb75,
					"customer_phone": PHONE,
					"booking_date": DAY,
					"from_time": "10:00",
					"to_time": "12:00",
					"total_amount": 400,
				}
			],
		)
		self.assertEqual(imported["failed"], [])
		self.assertRaisesRegex(
			frappe.ValidationError, "already booked", self.book, self.sb75, start="11:00", end="13:00"
		)
		self.book(self.sb75, start="12:00", end="13:00")  # back to back with the imported one
		failed = import_bookings(
			"studio_booking",
			[
				{
					"external_id": "P2",
					"resource": self.sb75,
					"customer_phone": PHONE,
					"booking_date": DAY,
					"from_time": "12:30",
					"to_time": "13:30",
					"total_amount": 200,
				}
			],
		)["failed"]
		self.assertIn("already booked", dict(failed)["P2"])
		# An imported booking keeps the booking system's amounts and posts nothing.
		booking = frappe.get_doc("Booking", imported["inserted"][0])
		self.assertEqual((booking.total_amount, booking.price_list, booking.treasury), (400, None, None))
		self.assertRaisesRegex(frappe.ValidationError, "imported", record_payment, booking.name, 100)

	# ---------- Audit 20 Oct 2026 ----------

	def test_qa13_a_part_hour_is_priced_from_its_minutes(self):
		# 40 minutes of the podcast with two cameras at 1,750 an hour: 1,166.67, not 0.67 x 1,750 = 1,172.50.
		booking = self.book(self.podcast, start="10:00", end="10:40", date=PAST, package=self.two_cameras, extras=[(self.mic, 3)])
		self.assertEqual(booking.hours, 0.67)
		self.assertEqual((booking.base_amount, booking.extras_amount), (1166.67, 100))
		# The invoice bills the same.
		booking = self.complete(booking)
		self.assertEqual(frappe.db.get_value("Sales Invoice", booking.sales_invoice, "grand_total"), 1266.67)

	def test_qa14_a_free_lecture_with_no_share_is_completed(self):
		share = dict(rental_model="Revenue Share", attendees=0, admission_price=0, collected_amount=0)
		booking = self.book(start="10:00", end="12:00", date=PAST, **share)
		# Without a lecturer, a 0% share is not an answer yet.
		self.assertRaisesRegex(frappe.ValidationError, "Lecturer", self.complete, booking)
		booking = self.complete(booking, lecturer_share_percent=0, lecturer=self.lecturer)
		self.assertEqual((booking.status, booking.lecturer_share, booking.center_share), ("Completed", 0, 0))

	def test_qa15_an_invoiced_booking_is_not_moved(self):
		booking = self.complete(self.book(self.sb75, start="10:00", end="11:00", date=PAST))
		self.assertTrue(booking.sales_invoice)
		for change in ({"booking_date": add_days(PAST, -1)}, {"from_time": "09:00:00"}, {"to_time": "10:30:00"}):
			with self.subTest(change):
				moved = frappe.get_doc("Booking", booking.name)
				moved.update(change)
				self.assertRaisesRegex(frappe.ValidationError, "Cancel it first", moved.save)

	def test_sec12_a_booking_with_money_or_imported_is_not_deleted(self):
		paid = self.book(self.sb75, start="10:00", end="11:00")
		record_payment(paid.name, 50, mode_of_payment=STUDIO_CASH)
		# Frappe's own link check already keeps one with a payment; the app's guard says why.
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Booking", paid.name)
		imported = import_bookings(
			"studio_booking",
			[{"external_id": "D1", "resource": self.sb75, "customer_phone": PHONE, "booking_date": DAY, "from_time": "14:00", "to_time": "15:00", "total_amount": 200}],
		)["inserted"][0]
		self.assertRaisesRegex(frappe.ValidationError, "imported", frappe.delete_doc, "Booking", imported)
		# A booking with nothing on it is still deleted as a mistake.
		frappe.delete_doc("Booking", self.book(self.sb75, start="16:00", end="17:00").name)

	def test_sec13_a_payment_names_a_booking_only_through_record_payment(self):
		booking = self.book(self.sb75, start="10:00", end="11:00", status="Cancelled", cancellation_reason="_Test cancelled")
		from erpnext.accounts.party import get_party_account

		company = frappe.db.get_value("Cost Center", STUDIO, "company")
		payment = frappe.get_doc(
			{
				"doctype": "Payment Entry", "payment_type": "Receive", "company": company,
				"party_type": "Customer", "party": self.customer,
				"paid_from": get_party_account("Customer", self.customer, company),
				"paid_to": STUDIO_BOX, "paid_amount": 999, "received_amount": 999, "cost_center": STUDIO,
				"custom_booking": booking.name,
			}
		)
		payment.setup_party_account_field()
		payment.set_missing_values()
		self.assertRaisesRegex(frappe.ValidationError, "Record Payment", payment.insert)

	# ---------- HAL-06: the halls' report ----------

	def test_hal06_the_halls_report(self):
		from imed_erp.imederp.report.hall_bookings.hall_bookings import execute as halls

		fixed = self.complete(self.book(start="10:00", end="12:00", date=PAST))  # 2 h at 300: rent 600, not paid yet
		share = self.book(
			start="13:00", end="15:00", date=PAST,
			rental_model="Revenue Share", attendees=30, admission_price=100, collected_amount=2500,
		)
		share = self.complete(share, lecturer_share_percent=40, lecturer=self.lecturer)
		gone = self.book(start="16:00", end="17:00", date=PAST)
		gone.reload()
		gone.update({"status": "Cancelled", "cancellation_reason": "_Test cancelled"})
		gone.save()

		rows = {r["name"]: r for r in halls({"from_date": PAST, "to_date": PAST, "hall": self.hall})[1]}
		self.assertEqual(
			(rows[fixed.name]["rent"], rows[fixed.name]["collected"], rows[fixed.name]["unpaid"], rows[fixed.name]["cancelled"]),
			(600, 0, 600, 0),
		)
		self.assertEqual(
			(rows[share.name]["attendees"], rows[share.name]["admission_price"], rows[share.name]["collected"], rows[share.name]["rent"]),
			(30, 100, 2500, 0),
		)
		self.assertEqual((rows[gone.name]["cancelled"], rows[gone.name]["unpaid"], rows[gone.name]["rent"]), (1, 0, 0))
		# Nour runs the halls; Gilan (the studio) sees none of them.
		frappe.set_user(GILAN)
		try:
			self.assertEqual(halls({"from_date": PAST, "to_date": PAST})[1], [])
		finally:
			frappe.set_user("Administrator")
