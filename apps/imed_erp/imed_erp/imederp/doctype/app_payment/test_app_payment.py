# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# What students pay BA Plus (22 Oct 2026): cash into the collecting branch's own box, in its daily close; electronic
# into a bank account or wallet, with its reference, never into a cash box; held for the doctor, never revenue;
# never posted twice. Rolled back afterwards.
#
#   bench --site frontend run-tests --doctype "App Payment"

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp.doctype.app_course.test_app_course import make_course
from imed_erp.imederp.doctype.app_payment.app_payment import cancel_payment, import_payment
from imed_erp.imederp.doctype.book_edition.test_book_edition import make_doctor

IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Academic Period", "App Course", "App Subscription", "App Payment", "Cost Center", "Customer", "Doctor Agreement", "Account",
	"Journal Entry", "Treasury Close",
]

APP = "تطبيق BA Plus - MMG"
AZARITA = "مكتبة الأزاريطة - MMG"
MAWASAH = "مكتبة المواساة - MMG"
AZARITA_BOX = "خزينة مكتبة الأزاريطة - MMG"
MAWASAH_BOX = "خزينة مكتبة المواساة - MMG"
APP_BANK = "خزينة تطبيق BA Plus - MMG"
INSTAPAY = "محفظة InstaPay - MMG"
HELD = "مقبوضات الطلبة لحساب الأطباء — التطبيق - MMG"
SARA, MENNA, ACCOUNTANT = "sara@imed.local", "menna@imed.local", "accountant@imed.local"


def subscription(student="_Test Paying Student"):
	doc = frappe.get_doc(
		{
			"doctype": "App Subscription",
			"student": make_doctor(student),
			"course": make_course("_Test Paid Course"),
			"subscription_date": "2026-09-15",
			"cost_center": APP,
		}
	).insert()
	doc.submit()
	return doc.name


def payment(sub, method="Cash", treasury=AZARITA_BOX, branch=AZARITA, amount=500, reference=None, submit=True, date=None):
	doc = frappe.get_doc(
		{
			"doctype": "App Payment",
			"subscription": sub,
			"posting_date": date or today(),
			"branch": branch,
			"payment_method": method,
			"treasury": treasury,
			"amount": amount,
			"reference_no": reference,
		}
	).insert()
	if submit:
		doc.submit()
	return doc


def lines(entry):
	return {
		r.account: flt(r.debit - r.credit, 2)
		for r in frappe.get_all("GL Entry", filters={"voucher_no": entry, "is_cancelled": 0}, fields=["account", "debit", "credit"])
	}


def as_user(user, fn, *args, **kwargs):
	frappe.set_user(user)
	try:
		return fn(*args, **kwargs)
	finally:
		frappe.set_user("Administrator")


class IntegrationTestAppPayment(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("app_payment_test")
		self.sub = subscription()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="app_payment_test")

	def test_cash_goes_into_the_branch_box_held_for_the_doctor(self):
		doc = as_user(SARA, payment, self.sub)
		self.assertEqual((doc.student, doc.doctor), (frappe.db.get_value("App Subscription", self.sub, "student"), frappe.db.get_value("App Subscription", self.sub, "doctor")))
		# Held for the doctor: no income account is touched.
		self.assertEqual(lines(doc.journal_entry), {AZARITA_BOX: 500, HELD: -500})
		income = frappe.get_all("GL Entry", filters={"voucher_no": doc.journal_entry, "account": ("like", "%إيراد%")})
		self.assertFalse(income)

	def test_a_cash_payment_is_in_the_day_s_close(self):
		from imed_erp.imederp.doctype.treasury_close.treasury_close import movements

		before = movements(AZARITA_BOX, today(), today()).collections
		as_user(SARA, payment, self.sub, amount=300)
		self.assertEqual(flt(movements(AZARITA_BOX, today(), today()).collections - before, 2), 300)

	def test_cash_only_into_the_collecting_branch_s_own_box(self):
		self.assertRaises(frappe.ValidationError, payment, self.sub, treasury=MAWASAH_BOX)
		# The app has no cash box: cash is paid at a branch.
		self.assertRaises(frappe.ValidationError, payment, self.sub, treasury=APP_BANK, branch=APP)
		# Cash is never put into a bank account.
		self.assertRaises(frappe.ValidationError, payment, self.sub, treasury=APP_BANK)

	def test_electronic_reaches_a_bank_or_wallet_with_its_reference(self):
		self.assertRaises(frappe.ValidationError, payment, self.sub, "InstaPay", INSTAPAY, APP)
		self.assertRaises(frappe.ValidationError, payment, self.sub, "Bank Transfer", AZARITA_BOX, AZARITA, reference="TX-1")
		doc = payment(self.sub, "Bank Transfer", APP_BANK, APP, reference=" tx-1001 ")
		self.assertEqual(doc.reference_no, "TX-1001")
		self.assertEqual(lines(doc.journal_entry), {APP_BANK: 500, HELD: -500})
		entry = frappe.get_doc("Journal Entry", doc.journal_entry)
		# Matched with the statement on its reference (ERPNext's Bank Clearance).
		self.assertEqual((entry.voucher_type, entry.cheque_no), ("Bank Entry", "TX-1001"))
		cash_lines = [a for a in lines(doc.journal_entry) if frappe.db.get_value("Account", a, "account_type") == "Cash"]
		self.assertFalse(cash_lines)

	def test_a_reference_is_recorded_once_per_account(self):
		payment(self.sub, "InstaPay", INSTAPAY, APP, reference="IP-77")
		other = subscription("_Test Second Student")
		self.assertRaises(frappe.ValidationError, payment, other, "InstaPay", INSTAPAY, APP, reference="ip-77")
		# The same number at another bank is another transaction.
		self.assertTrue(payment(other, "Bank Transfer", APP_BANK, APP, reference="IP-77").journal_entry)

	def test_branch_managers_record_only_at_their_branch(self):
		self.assertRaises(frappe.PermissionError, as_user, SARA, payment, self.sub, treasury=MAWASAH_BOX, branch=MAWASAH)
		# The app's bank account is the app's; the group's wallets are anybody's.
		self.assertRaises(frappe.ValidationError, as_user, SARA, payment, self.sub, "Bank Transfer", APP_BANK, AZARITA, reference="S-1")
		self.assertTrue(as_user(SARA, payment, self.sub, "InstaPay", INSTAPAY, AZARITA, reference="S-2").journal_entry)
		self.assertTrue(as_user(MENNA, payment, self.sub, "Bank Transfer", APP_BANK, APP, reference="M-1").journal_entry)

	def test_import_is_idempotent(self):
		data = {
			"external_id": "bap-555", "subscription": self.sub, "posting_date": today(), "branch": APP,
			"payment_method": "Vodafone Cash", "treasury": "محفظة Vodafone Cash - MMG", "amount": 250, "reference_no": "VC-9",
		}
		first, created = import_payment(data)
		again, created_again = import_payment(data)
		self.assertEqual((first, created, again, created_again), (first, True, first, False))
		self.assertEqual(frappe.db.count("App Payment", {"import_key": "BA Plus:bap-555"}), 1)
		# Cancelled, it is still not imported again.
		cancel_payment(first, "wrong course")
		self.assertEqual(tuple(import_payment(data)), (first, False))
		# Only the import makes or changes an imported payment.
		self.assertRaises(frappe.PermissionError, as_user, SARA, import_payment, data)

	def test_cancelling_is_the_accountant_s_with_a_reason(self):
		doc = as_user(SARA, payment, self.sub, "InstaPay", INSTAPAY, AZARITA, reference="C-1")
		self.assertRaises(frappe.PermissionError, as_user, SARA, cancel_payment, doc.name, "mistake")
		self.assertRaises(frappe.ValidationError, as_user, ACCOUNTANT, cancel_payment, doc.name, "  ")
		# Its entry is reversed only through the payment.
		entry = frappe.get_doc("Journal Entry", doc.journal_entry)
		self.assertRaises(frappe.ValidationError, entry.cancel)
		as_user(ACCOUNTANT, cancel_payment, doc.name, "paid twice by mistake")
		doc.reload()
		self.assertEqual((doc.docstatus, doc.cancel_reason), (2, "paid twice by mistake"))
		self.assertEqual(frappe.db.get_value("Journal Entry", doc.journal_entry, "docstatus"), 2)
		# The reference may be recorded again, correctly.
		self.assertTrue(payment(self.sub, "InstaPay", INSTAPAY, AZARITA, reference="C-1").journal_entry)

	def test_submitting_twice_posts_once(self):
		doc = payment(self.sub)
		doc.on_submit()
		self.assertEqual(frappe.db.count("Journal Entry", {"user_remark": ("like", f"{doc.name}:%"), "docstatus": 1}), 1)

	def test_the_platform_fee_is_unchanged(self):
		course = frappe.db.get_value("App Subscription", self.sub, "course")
		fee = frappe.db.get_value("App Course", course, "platform_fee_total")
		payment(self.sub, amount=900)
		self.assertEqual(frappe.db.get_value("App Course", course, "platform_fee_total"), fee)

	def test_a_draft_subscription_takes_no_payment(self):
		draft = frappe.get_doc(
			{"doctype": "App Subscription", "student": make_doctor("_Test Draft Student"), "course": make_course("_Test Paid Course"), "subscription_date": "2026-09-15", "cost_center": APP}
		).insert()
		self.assertRaises(frappe.ValidationError, payment, draft.name)

	def test_the_report_matches_electronic_payments_and_keeps_branches_apart(self):
		from imed_erp.imederp.report.app_payments.app_payments import data

		cash = as_user(SARA, payment, self.sub, amount=120)
		wire = payment(self.sub, "Bank Transfer", APP_BANK, APP, reference="R-1", amount=80)
		filters = frappe._dict(from_date=today(), to_date=today(), doctor=cash.doctor)
		names = [r.name for r in data(filters)]
		self.assertIn(cash.name, names)
		self.assertIn(wire.name, names)
		# Waiting to be matched with the statement: the electronic one only, until Bank Clearance dates it.
		pending = [r.name for r in data(frappe._dict(filters, not_cleared=1))]
		self.assertEqual((wire.name in pending, cash.name in pending), (True, False))
		frappe.db.set_value("Journal Entry", wire.journal_entry, "clearance_date", today())
		self.assertNotIn(wire.name, [r.name for r in data(frappe._dict(filters, not_cleared=1))])
		# Sara sees her branch's payments, not the app's.
		hers = [r.name for r in as_user(SARA, data, filters)]
		self.assertEqual((cash.name in hers, wire.name in hers), (True, False))
