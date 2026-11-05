# Copyright (c) 2026, toka mohamed and contributors
# See license.txt

# The halls' bookings and payments read from Sparkle (imederp/sparkle/sync.py; owner, 5 Nov 2026), against a
# stand-in for Sparkle's database: bookings here per hall held, the renter by phone, each payment once as a Journal
# Entry into its box (the owner's custody before November), the halls booked on Sparkle only while the sync is on.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_sparkle_sync

import random
import uuid

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from imed_erp.imederp.sparkle import sync

COST_CENTER = "قاعات Imed - MMG"
CASH, CUSTODY, INSTAPAY, WALLET = "خزينة سنتر Imed - MMG", "عهدة المالك النقدية - MMG", "محفظة InstaPay - MMG", "محفظة Vodafone Cash - MMG"
HALLS = {"hall-4": "_Test Sparkle Hall 4", "hall-5": "_Test Sparkle Hall 5", "hall-6": "_Test Sparkle Hall 6"}
OCTOBER = "2026-10-20"


def uid():
	return str(uuid.uuid4())


def phone():
	return "010" + "".join(random.choice("0123456789") for _ in range(8))


class FakeSparkle:
	"""Sparkle's tables as the client reads them."""

	def __init__(self):
		self.bookings_, self.resources_, self.customers_, self.payments_ = [], [], [], []

	def booking(self, hall="hall-4", day=OCTOBER, start="10:00", end="12:00", status="completed", total=1000, halls=None, **values):
		row = {
			"id": uid(), "hall_slug": hall, "booking_date": day, "start_time": f"{start}:00", "end_time": f"{end}:00", "status": status,
			"type": "lecture", "customer_id": None, "full_name": "_Test Sparkle Renter", "whatsapp": phone(), "notes": None,
			"settlement_note": None, "created_at": f"{day}T08:00:00", "final_total": total, "calculated_total": total,
			"override_total": None, "extras_total": 0,
		}
		row.update(values)
		self.bookings_.append(row)
		for slug in halls or [hall]:
			self.resources_.append({"booking_id": row["id"], "physical_slug": slug, "booking_date": day, "start_time": row["start_time"], "end_time": row["end_time"]})
		return row

	def payment(self, booking, amount, paid_on=OCTOBER, method="cash", kind="payment", reverses=None):
		row = {"id": uid(), "booking_id": booking["id"], "kind": kind, "amount": amount, "paid_on": paid_on, "method": method,
			"reference": None, "note": None, "reverses_id": reverses and reverses["id"], "created_at": f"{paid_on}T09:{len(self.payments_):02d}:00"}
		self.payments_.append(row)
		return row

	# the client's interface
	def bookings(self, since):
		return [b for b in self.bookings_ if b["booking_date"] >= since]

	def resources(self, ids):
		return [r for r in self.resources_ if r["booking_id"] in ids]

	def customers(self, ids):
		return [c for c in self.customers_ if c["id"] in ids]

	def payments(self, ids):
		return [p for p in self.payments_ if p["booking_id"] in ids]

	def close(self):
		pass


class IntegrationTestSparkleSync(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("sparkle_test")
		for slug, name in HALLS.items():
			if not frappe.db.exists("Booking Resource", name):
				frappe.get_doc({"doctype": "Booking Resource", "resource_name": name, "resource_type": "Hall", "cost_center": COST_CENTER, "capacity": 40}).insert()
		income = frappe.db.get_value("Account", {"account_name": "إيراد القاعات", "is_group": 0}) or frappe.db.get_value(
			"Account", {"root_type": "Income", "is_group": 0, "company": frappe.db.get_value("Cost Center", COST_CENTER, "company")}
		)
		settings = frappe.get_single("Sparkle Settings")
		settings.update({
			"enabled": 1, "start_date": "2026-09-01", "customer_group": "Individual", "income_account": income, "cost_center": COST_CENTER,
			"custody_account": CUSTODY, "custody_until": "2026-10-31", "cash_account": CASH, "instapay_account": INSTAPAY, "wallet_account": WALLET,
			"db_host": "fake", "db_user": "fake",
		})
		settings.set("hall_map", [{"sparkle_hall": slug, "resource": name} for slug, name in HALLS.items()])
		settings.save()
		self.income = income
		self.x = FakeSparkle()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="sparkle_test")

	def sync(self):
		return sync.run(trigger="test", client=self.x)

	def booking(self, row, slug=None):
		external = f"{row['id']}:{slug}" if slug else row["id"]
		name = frappe.db.get_value("Booking", {"import_key": f"sparkle:{external}"})
		return frappe.get_doc("Booking", name) if name else None

	def entry(self, payment):
		name = frappe.db.get_value("Journal Entry", {"sparkle_payment_id": payment["id"], "docstatus": 1})
		return frappe.get_doc("Journal Entry", name) if name else None

	def moved(self, entry, account):
		"""What the entry brought into `account` (negative: took out)."""
		return sum(flt(a.debit_in_account_currency) - flt(a.credit_in_account_currency) for a in entry.accounts if a.account == account)

	def test_a_booking_comes_in_as_a_hall_booking_with_its_price_and_renter(self):
		row = self.x.booking(total=1500, type="course")
		self.x.payment(row, 1000)
		log = self.sync()
		self.assertEqual((log.status, log.failed), ("Completed", 0), log.as_dict().get("errors"))
		b = self.booking(row)
		self.assertEqual((b.resource, b.status, b.total_amount, b.paid_amount, b.outstanding_amount), (HALLS["hall-4"], "Completed", 1500, 1000, 500))
		self.assertEqual((b.source, b.activity, b.rental_model, b.cost_center), ("Imported", "كورس", "Fixed Rent", COST_CENTER))
		self.assertEqual(frappe.db.get_value("Customer", b.customer, "customer_name"), "_Test Sparkle Renter")
		# The same renter booking again (same phone) is the same customer.
		again = self.x.booking(day="2026-10-21", whatsapp=row["whatsapp"], full_name="_Test Other Spelling")
		self.sync()
		self.assertEqual(self.booking(again).customer, b.customer)

	def test_a_combined_hall_holds_both_halls_and_its_money_sits_on_the_first(self):
		row = self.x.booking(hall="hall-5-6", halls=["hall-5", "hall-6"], total=2400)
		self.x.payment(row, 2400)
		self.sync()
		five, six = self.booking(row, "hall-5"), self.booking(row, "hall-6")
		self.assertEqual((five.resource, five.total_amount, five.paid_amount), (HALLS["hall-5"], 2400, 2400))
		self.assertEqual((six.resource, six.total_amount, six.paid_amount), (HALLS["hall-6"], 0, 0))
		self.assertIn("hall-5-6", six.notes)
		# Neither hall can be taken at that time any more (here, through the import).
		clash = self.x.booking(hall="hall-6", total=500)
		log = self.sync()
		self.assertIsNone(self.booking(clash))
		self.assertEqual(log.failed, 1)

	def test_a_hall_not_mapped_is_noted_and_skipped(self):
		self.x.booking(hall="call-center")
		log = self.sync()
		self.assertEqual((log.status, log.failed), ("Completed", 0))
		self.assertIn("call-center", " ".join(r.reason for r in log.errors))

	def test_each_payment_is_posted_once_into_its_box(self):
		october = self.x.booking(total=3000)
		november = self.x.booking(day=add_days(today(), 1), status="confirmed", total=3000)
		before_november = self.x.payment(october, 1000)  # paid in October: handed to the owner already
		cash = self.x.payment(november, 700, paid_on=today())
		transfer = self.x.payment(november, 300, paid_on=today(), method="bank_transfer")
		wallet = self.x.payment(november, 200, paid_on=today(), method="wallet")
		log = self.sync()
		self.assertEqual(log.failed, 0, [r.reason for r in log.errors])
		self.assertEqual(self.moved(self.entry(before_november), CUSTODY), 1000)
		self.assertEqual(self.moved(self.entry(cash), CASH), 700)
		self.assertEqual(self.moved(self.entry(transfer), INSTAPAY), 300)  # a bank transfer counts as InstaPay
		self.assertEqual(self.moved(self.entry(wallet), WALLET), 200)
		self.assertEqual(self.moved(self.entry(cash), self.income), -700)  # revenue credited
		e = self.entry(cash)
		self.assertEqual((str(e.posting_date), e.accounts[0].cost_center), (today(), COST_CENTER))
		# A second run posts nothing again.
		entries = frappe.db.count("Journal Entry", {"sparkle_payment_id": ["is", "set"]})
		self.sync()
		self.assertEqual(frappe.db.count("Journal Entry", {"sparkle_payment_id": ["is", "set"]}), entries)
		self.assertEqual(self.booking(november).paid_amount, 1200)

	def test_a_reversal_takes_the_money_back_and_its_undoing_brings_it_in(self):
		row = self.x.booking(day=add_days(today(), 2), status="confirmed", total=1000)
		paid = self.x.payment(row, 800, paid_on=today())
		reversal = self.x.payment(row, 800, paid_on=today(), kind="reversal", reverses=paid)
		self.sync()
		self.assertEqual(self.moved(self.entry(reversal), CASH), -800)
		self.assertEqual(self.booking(row).paid_amount, 0)
		undo = self.x.payment(row, 800, paid_on=today(), kind="reversal_undo", reverses=reversal)
		self.sync()
		self.assertEqual(self.moved(self.entry(undo), CASH), 800)
		self.assertEqual(self.booking(row).paid_amount, 800)

	def test_a_change_in_sparkle_follows_and_a_cancelled_one_frees_the_hall(self):
		row = self.x.booking(day=add_days(today(), 3), status="pending", total=900)
		self.sync()
		self.assertEqual(self.booking(row).status, "Tentative")
		row.update(status="cancelled", settlement_note="العميل اعتذر")
		log = self.sync()
		self.assertEqual(log.updated, 1)
		b = self.booking(row)
		self.assertEqual((b.status, b.cancellation_reason), ("Cancelled", "العميل اعتذر"))
		# Moved to another hall: the hall it left is freed.
		moved = self.x.booking(day=add_days(today(), 4), status="confirmed")
		self.sync()
		first = self.booking(moved).name
		self.x.resources_ = [r for r in self.x.resources_ if r["booking_id"] != moved["id"]]
		moved["hall_slug"] = "hall-5-6"
		for slug in ("hall-5", "hall-6"):
			self.x.resources_.append({"booking_id": moved["id"], "physical_slug": slug, "booking_date": moved["booking_date"], "start_time": moved["start_time"], "end_time": moved["end_time"]})
		self.sync()
		self.assertEqual(frappe.db.get_value("Booking", first, "status"), "Cancelled")
		self.assertEqual(self.booking(moved, "hall-5").status, "Confirmed")

	def test_while_on_a_hall_is_booked_on_sparkle_only(self):
		values = {
			"doctype": "Booking", "resource": HALLS["hall-4"], "booking_date": add_days(today(), 10), "from_time": "10:00:00", "to_time": "11:00:00",
			"status": "Tentative", "hall_booking_type": "Internal Meeting", "activity": "اجتماع", "responsible_name": "س", "responsible_phone": phone(),
		}
		self.assertRaisesRegex(frappe.ValidationError, "Sparkle", frappe.get_doc(dict(values)).insert)
		frappe.db.set_single_value("Sparkle Settings", "enabled", 0)
		frappe.get_doc(dict(values)).insert()  # with the sync off, as before
