# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# App subscriptions (APP-04/05, requirements v1.2): no course money is recorded, and a subscription belongs
# to an app agreement. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "App Subscription"

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement, make_doctor

# Every doctype these tests link to is made here or already exists on the site. Without this Frappe builds
# ERPNext's "_Test ..." records for them and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Academic Period", "App Subscription", "Cost Center", "Customer", "Doctor Agreement"]

APP = "تطبيق BA Plus - MMG"


class IntegrationTestAppSubscription(IntegrationTestCase):
	def make_subscription(self, agreement):
		return frappe.get_doc(
			{
				"doctype": "App Subscription",
				"student": make_doctor("_Test Student"),
				"agreement": agreement,
				"course": "_Test Course",
				"subscription_date": "2026-10-07",
				"cost_center": APP,
			}
		).insert()

	def test_no_course_money_is_recorded(self):
		meta = frappe.get_meta("App Subscription")
		self.assertFalse(meta.has_field("total_paid"))
		self.assertFalse(meta.has_field("course_amount"))
		self.assertTrue(self.make_subscription(make_agreement("App")).name)

	def test_subscription_belongs_to_an_app_agreement(self):
		self.assertRaises(frappe.ValidationError, self.make_subscription, make_agreement("Books"))
