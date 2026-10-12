# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A doctor is a Customer in the doctor group (CRM-01); an agreement accepts only doctors. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Doctor Agreement"

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_doctor
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
