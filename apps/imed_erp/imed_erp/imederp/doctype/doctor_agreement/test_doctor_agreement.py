# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A doctor is a Customer in the doctor group (CRM-01); an agreement accepts only doctors. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Doctor Agreement"

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_doctor
from frappe.utils import flt, today

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import DOCTOR_GROUP


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
# Linked records already exist on the site or are made by the tests; without this list Frappe builds
# ERPNext's "_Test ..." records and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Customer", "Doctor Agreement"]



class IntegrationTestDoctorAgreement(IntegrationTestCase):
	def agreement(self, doctor, name="_Test Agreement"):
		return frappe.get_doc(
			{
				"doctype": "Doctor Agreement",
				"agreement_name": name,
				"doctor": doctor,
				"agreement_type": "Books",
				"share_type": "Fixed",
				"share_value": 80,
				"settlement_cycle": "Term",
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
