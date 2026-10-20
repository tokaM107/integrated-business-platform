# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# App subscriptions (APP-04/05, requirements v1.2): no course money is recorded, and a subscription belongs
# to a course of an app agreement, which gives its agreement and term. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "App Subscription"

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.app_course.test_app_course import make_course
from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement, make_doctor

# Every doctype these tests link to is made here or already exists on the site. Without this Frappe builds
# ERPNext's "_Test ..." records for them and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Academic Period", "App Course", "App Subscription", "Cost Center", "Customer", "Doctor Agreement"]

APP = "تطبيق BA Plus - MMG"


class IntegrationTestAppSubscription(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("app_subscription_test")

	def tearDown(self):
		# The tests share one agreement and course; a suspended or closed one must not reach the next test.
		frappe.db.rollback(save_point="app_subscription_test")

	def make_subscription(self, course):
		return frappe.get_doc(
			{
				"doctype": "App Subscription",
				"student": make_doctor("_Test Student"),
				"course": course,
				"subscription_date": "2031-09-15",
				"cost_center": APP,
			}
		).insert()

	def test_no_course_money_is_recorded(self):
		meta = frappe.get_meta("App Subscription")
		self.assertFalse(meta.has_field("total_paid"))
		self.assertFalse(meta.has_field("course_amount"))
		self.assertTrue(self.make_subscription(make_course()).name)

	def test_agreement_doctor_and_term_come_from_the_course(self):
		course = frappe.get_doc("App Course", make_course())
		subscription = self.make_subscription(course.name)
		self.assertEqual(subscription.agreement, course.agreement)
		self.assertEqual(subscription.period, course.period)
		# APP-04: the student, the course, the doctor, the date and the term.
		self.assertEqual(subscription.doctor, course.doctor)

	def test_a_student_is_subscribed_once_to_a_course(self):
		course = make_course("_Test Twice Course")
		first = self.make_subscription(course)
		first.submit()
		self.assertRaises(frappe.ValidationError, self.make_subscription, course)
		# Cancelled, he can be subscribed again; another course is another subscription.
		first.cancel()
		self.make_subscription(course).submit()
		self.make_subscription(make_course("_Test Other Course")).submit()

	def test_closed_course_takes_no_new_subscriptions(self):
		course = frappe.get_doc("App Course", make_course("_Test Closed Course"))
		course.db_set("status", "Closed")
		self.assertRaises(frappe.ValidationError, self.make_subscription, course.name)

	def test_subscription_belongs_to_an_app_agreement(self):
		# A course of a books agreement is refused (test_app_course.py); an old course whose agreement is not
		# an app one any more is refused here too.
		course = make_course("_Test Moved Course")
		frappe.db.set_value("App Course", course, "agreement", make_agreement("Books"))
		self.assertRaises(frappe.ValidationError, self.make_subscription, course)

	def test_qa07_a_draft_is_not_submitted_once_its_course_is_closed(self):
		course = frappe.get_doc("App Course", make_course("_Test Closed Later Course"))
		draft = self.make_subscription(course.name)
		course.db_set("status", "Closed")
		self.assertRaisesRegex(frappe.ValidationError, "is closed", draft.submit)
		self.assertEqual(frappe.db.get_value("App Subscription", draft.name, "docstatus"), 0)

	def test_qa07_a_draft_is_not_submitted_once_its_agreement_is_suspended(self):
		course = make_course("_Test Suspended Later Course")
		draft = self.make_subscription(course)
		agreement = frappe.db.get_value("App Course", course, "agreement")
		frappe.db.set_value("Doctor Agreement", agreement, "status", "Suspended")
		self.assertRaisesRegex(frappe.ValidationError, "suspended", draft.submit)

	def test_qa17_the_date_is_in_the_course_s_term(self):
		course = make_course()
		for date in ("2026-10-07", "2032-01-01"):
			with self.subTest(date):
				doc = frappe.get_doc(
					{"doctype": "App Subscription", "student": make_doctor("_Test Student"), "course": course,
						"subscription_date": date, "cost_center": APP}
				)
				self.assertRaisesRegex(frappe.ValidationError, "in the course's term", doc.insert)
