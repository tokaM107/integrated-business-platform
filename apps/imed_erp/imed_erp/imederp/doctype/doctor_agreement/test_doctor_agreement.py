# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A doctor is a Customer in the doctor group (CRM-01); an agreement accepts only doctors. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Doctor Agreement"

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from frappe.utils import flt, today

from imed_erp.imederp.doctype.book_edition.test_book_edition import PAPER_COST, make_doctor
from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import DOCTOR_GROUP


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
# Linked records already exist on the site or are made by the tests; without this list Frappe builds
# ERPNext's "_Test ..." records and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Book Edition", "Cost Center", "Customer", "Doctor Agreement"]



class IntegrationTestDoctorAgreement(IntegrationTestCase):
	def agreement(self, doctor, name="_Test Agreement"):
		return frappe.get_doc(
			{
				"doctype": "Doctor Agreement",
				"agreement_name": name,
				"doctor": doctor,
				"agreement_type": "Books",
				"settlement_cycle": "Term",
				"terms": [{"amount_per_copy": 80}],
			}
		)

	def test_the_doctor_group_exists(self):
		# Made by setup/setup_core.py.
		self.assertTrue(frappe.db.exists("Customer Group", DOCTOR_GROUP))

	def test_an_agreement_is_made_with_a_doctor(self):
		self.agreement(make_doctor()).insert()

	def test_a_customer_who_is_not_a_doctor_is_refused(self):
		student = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test Not A Doctor",
				"customer_group": frappe.get_all(
					"Customer Group", filters={"is_group": 0, "name": ["!=", DOCTOR_GROUP]}, limit=1, pluck="name"
				)[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0],
			}
		).insert()
		self.assertRaisesRegex(frappe.ValidationError, "is not a doctor", self.agreement(student.name, "_Test Refused").insert)

	def entry(self, agreement, entry_type, amount):
		entry = frappe.get_doc(
			{"doctype": "Doctor Ledger Entry", "agreement": agreement, "entry_date": today(), "entry_type": entry_type, "amount": amount}
		).insert()
		entry.submit()
		return entry

	def test_a_new_agreement_starts_today_and_is_active(self):
		agreement = self.agreement(make_doctor(), "_Test Defaults").insert()
		self.assertEqual((str(agreement.start_date), agreement.status, flt(agreement.balance)), (today(), "Active", 0))

	def test_the_balance_comes_from_the_doctors_ledger(self):
		# 800 owed for copies sold, 300 paid, 50 charged for a cancellation, -20 adjusted: 430 left.
		agreement = self.agreement(make_doctor(), "_Test Balance").insert()
		self.entry(agreement.name, "Accrual", 800)
		payment = self.entry(agreement.name, "Payment", 300)
		self.entry(agreement.name, "Cancellation Charge", 50)
		self.entry(agreement.name, "Adjustment", -20)
		self.assertEqual(frappe.db.get_value("Doctor Agreement", agreement.name, "balance"), 430)

		# A cancelled entry no longer counts.
		payment.cancel()
		self.assertEqual(frappe.db.get_value("Doctor Agreement", agreement.name, "balance"), 730)

	def test_the_balance_is_not_typed(self):
		agreement = self.agreement(make_doctor(), "_Test Typed Balance")
		agreement.balance = 999
		agreement.insert()
		self.assertTrue(frappe.get_meta("Doctor Agreement").get_field("balance").read_only)

	def test_a_suspended_agreement_takes_no_new_edition_or_subscription(self):
		from imed_erp.imederp.doctype.book_edition.test_book_edition import LIBRARY

		books = self.agreement(make_doctor(), "_Test Suspended Books").insert()
		books.submit()
		# Suspended after it was submitted, without an amendment.
		books.status = "Suspended"
		books.save()
		edition = frappe.get_doc(
			{"doctype": "Book Edition", "edition_name": "_Test Suspended Edition", "agreement": books.name, "cost_center": LIBRARY, "pages": 10}
		)
		self.assertRaisesRegex(frappe.ValidationError, "suspended", edition.insert)

		app = self.agreement(make_doctor(), "_Test Suspended App")
		app.agreement_type = "App"
		app.status = "Suspended"
		app.insert()
		subscription = frappe.get_doc(
			{
				"doctype": "App Subscription",
				"student": make_doctor("_Test Suspended Student"),
				"agreement": app.name,
				"cost_center": frappe.get_all("Cost Center", filters={"is_group": 0}, pluck="name", limit=1)[0],
				"subscription_date": today(),
				"platform_fee": 50,
			}
		)
		self.assertRaisesRegex(frappe.ValidationError, "suspended", subscription.insert)

		# Its account can still be settled.
		self.entry(books.name, "Accrual", 100)
		self.entry(books.name, "Payment", 100)

	def books(self, name, terms, start_date="2026-01-01"):
		agreement = self.agreement(make_doctor(), name)
		agreement.start_date = start_date
		agreement.terms = []
		for valid_from, amount in terms:
			agreement.append("terms", {"valid_from": valid_from, "amount_per_copy": amount})
		return agreement

	def edition(self, agreement, edition_date, name):
		from imed_erp.imederp.doctype.book_edition.test_book_edition import LIBRARY

		return frappe.get_doc(
			{
				"doctype": "Book Edition",
				"edition_name": name,
				"agreement": agreement,
				"edition_date": edition_date,
				"cost_center": LIBRARY,
				"pages": 10,
			}
		).insert()

	def test_a_books_agreement_needs_an_amount_per_copy(self):
		agreement = self.books("_Test No Terms", [])
		self.assertRaisesRegex(frappe.ValidationError, "amount per copy", agreement.insert)

		# A term without a date starts with the agreement.
		agreement = self.books("_Test Undated Term", [(None, 80)], start_date="2026-09-01")
		agreement.insert()
		self.assertEqual(str(agreement.terms[0].valid_from), "2026-09-01")

		duplicate = self.books("_Test Same Date", [("2026-09-01", 80), ("2026-09-01", 90)])
		self.assertRaisesRegex(frappe.ValidationError, "same date", duplicate.insert)

	def test_an_app_agreement_has_no_terms(self):
		app = self.agreement(make_doctor(), "_Test App Terms")
		app.agreement_type = "App"
		app.insert()
		self.assertEqual(app.terms, [])

	def test_an_edition_takes_the_amount_in_force_on_its_date(self):
		# 80 a copy from January, 100 from November: an October edition is 80, a November one 100, and one
		# before January has no amount.
		agreement = self.books("_Test Two Terms", [("2026-11-01", 100), ("2026-01-01", 80)]).insert()
		self.assertEqual([(str(t.valid_from), t.amount_per_copy) for t in agreement.terms], [("2026-01-01", 80), ("2026-11-01", 100)])
		self.assertEqual(self.edition(agreement.name, "2026-10-15", "_Test October Edition").doctor_share, 80)
		self.assertEqual(self.edition(agreement.name, "2026-11-05", "_Test November Edition").doctor_share, 100)
		self.assertRaisesRegex(
			frappe.ValidationError, "no amount per copy", self.edition, agreement.name, "2025-12-31", "_Test Early Edition"
		)

	@patch(PAPER_COST, return_value=0.30)
	def test_a_new_amount_from_a_new_date_leaves_earlier_editions_alone(self, _):
		# The definition of done of card A6: 80 a copy, then 100 from a new date; the edition priced at 80
		# keeps 80.
		agreement = self.books("_Test New Amount", [("2026-01-01", 80)]).insert()
		agreement.submit()
		old = self.edition(agreement.name, "2026-10-01", "_Test Old Edition")
		old.submit()

		agreement = frappe.get_doc("Doctor Agreement", agreement.name)
		agreement.append("terms", {"valid_from": "2026-11-01", "amount_per_copy": 100})
		agreement.save()

		old = frappe.get_doc("Book Edition", old.name)
		old.save()
		self.assertEqual(old.doctor_share, 80)
		self.assertEqual(self.edition(agreement.name, "2026-11-02", "_Test New Edition").doctor_share, 100)

	def test_a_term_already_given_is_not_changed(self):
		agreement = self.books("_Test Locked Term", [("2026-01-01", 80)]).insert()
		agreement.submit()
		# Changing its amount is refused by Frappe (the row's fields are fixed once submitted); removing it, by
		# the agreement.
		agreement = frappe.get_doc("Doctor Agreement", agreement.name)
		agreement.terms[0].amount_per_copy = 70
		self.assertRaises(frappe.ValidationError, agreement.save)
		agreement = frappe.get_doc("Doctor Agreement", agreement.name)
		agreement.append("terms", {"valid_from": "2026-11-01", "amount_per_copy": 100})
		agreement.terms = agreement.terms[1:]
		self.assertRaisesRegex(frappe.ValidationError, "already in force", agreement.save)

	def test_the_balance_direction_comes_from_the_type(self):
		books = self.agreement(make_doctor(), "_Test Direction Books")
		books.balance_direction = "Owed by Doctor"  # typed by mistake: the type decides
		books.insert()
		self.assertEqual(books.balance_direction, "Owed to Doctor")

		app = self.agreement(make_doctor(), "_Test Direction App")
		app.agreement_type = "App"
		app.insert()
		self.assertEqual(app.balance_direction, "Owed by Doctor")

	def test_one_doctor_two_agreements_two_balances(self):
		# The definition of done of card A6: one doctor with a books agreement at 80 a copy, owed to him, and an
		# app agreement, owed by him. Each keeps its own balance: nothing is offset between them.
		doctor = make_doctor("_Test Doctor Two Agreements")
		books = self.agreement(doctor, "_Test Two Books").insert()
		app = self.agreement(doctor, "_Test Two App")
		app.agreement_type = "App"
		app.insert()

		self.entry(books.name, "Accrual", 800)  # 10 copies sold at 80
		self.entry(app.name, "Accrual", 200)  # platform fees

		self.assertEqual(books.terms[0].amount_per_copy, 80)
		self.assertEqual(
			frappe.db.get_value("Doctor Agreement", books.name, ["balance_direction", "balance"]), ("Owed to Doctor", 800)
		)
		self.assertEqual(
			frappe.db.get_value("Doctor Agreement", app.name, ["balance_direction", "balance"]), ("Owed by Doctor", 200)
		)
