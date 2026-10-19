# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# App courses (APP-01, requirements v1.2): a course belongs to an app agreement and a term, the doctor comes
# from the agreement, and a course is not made twice in a term. Its platform fee (APP-03): the tier for its
# number of students, counted again with every subscription until the term is closed. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "App Course"

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement, make_doctor
from imed_erp.imederp.doctype.platform_fee_schedule.test_platform_fee_schedule import VALID_FROM, make_schedule

# Every doctype these tests link to is made here or already exists on the site. Without this Frappe builds
# ERPNext's "_Test ..." records for them and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Academic Period", "App Course", "App Subscription", "Cost Center", "Customer", "Doctor Agreement", "Platform Fee Schedule"
]

APP = "تطبيق BA Plus - MMG"


def make_term(name="_Test Course Term"):
	if frappe.db.exists("Academic Period", name):
		return name
	return (
		frappe.get_doc(
			# Starts when the tests' fee schedule does, so its fees are the owner's tiers whatever the site holds.
			{"doctype": "Academic Period", "period_name": name, "period_type": "Term", "start_date": VALID_FROM, "end_date": "2031-12-31"}
		)
		.insert()
		.name
	)


def make_course(course_name="_Test Course", agreement=None, period=None):
	# Shared by the tests that make subscriptions: the same course of the same agreement in the same term is
	# one course.
	agreement = agreement or make_agreement("App")
	period = period or make_term()
	name = frappe.db.get_value("App Course", {"course_name": course_name, "agreement": agreement, "period": period})
	if name:
		return name
	return (
		frappe.get_doc({"doctype": "App Course", "course_name": course_name, "agreement": agreement, "period": period})
		.insert()
		.name
	)


class IntegrationTestAppCourse(IntegrationTestCase):
	def test_doctor_comes_from_the_agreement(self):
		agreement = make_agreement("App")
		course = frappe.get_doc("App Course", make_course("_Test Anatomy", agreement))
		self.assertEqual(course.doctor, frappe.db.get_value("Doctor Agreement", agreement, "doctor"))
		self.assertEqual(course.status, "Active")

	def test_course_belongs_to_an_app_agreement(self):
		self.assertRaises(frappe.ValidationError, make_course, "_Test Books Course", make_agreement("Books"))

	def test_course_runs_in_a_term(self):
		term = make_term()
		round_ = frappe.get_doc(
			{
				"doctype": "Academic Period",
				"period_name": "_Test Course Round",
				"period_type": "Round",
				"parent_period": term,
				"start_date": VALID_FROM,
				"end_date": "2031-10-31",
			}
		).insert()
		self.assertRaises(frappe.ValidationError, make_course, "_Test Round Course", None, round_.name)

	def test_same_course_twice_in_a_term_is_refused(self):
		make_course("_Test Physiology")
		twin = frappe.get_doc(
			{"doctype": "App Course", "course_name": "_Test Physiology", "agreement": make_agreement("App"), "period": make_term()}
		)
		self.assertRaises(frappe.ValidationError, twin.insert)

	def test_same_course_in_another_term_is_allowed(self):
		make_course("_Test Pharmacology")
		other = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": "_Test Course Term 2", "period_type": "Term", "start_date": "2027-01-01", "end_date": "2027-04-15"}
		).insert()
		self.assertTrue(make_course("_Test Pharmacology", period=other.name))

	def test_agreement_and_term_stay_once_it_has_subscriptions(self):
		course = make_course("_Test Kept Course")
		subscribe(course, 1)
		doc = frappe.get_doc("App Course", course)
		doc.period = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": "_Test Course Term 3", "period_type": "Term", "start_date": "2032-01-01", "end_date": "2032-04-15"}
		).insert().name
		self.assertRaises(frappe.ValidationError, doc.save)


def subscribe(course, count):
	student = make_doctor("_Test Fee Student")
	subscriptions = []
	for _ in range(count):
		doc = frappe.get_doc(
			{"doctype": "App Subscription", "student": student, "course": course, "subscription_date": "2031-09-15", "cost_center": APP}
		).insert()
		doc.submit()
		subscriptions.append(doc)
	return subscriptions


COUNTED_PER = "imed_erp.imederp.doctype.app_course.app_course.TIER_COUNTED_PER"
COUNT_WITHDRAWN = "imed_erp.imederp.doctype.app_course.app_course.COUNT_WITHDRAWN"


class IntegrationTestPlatformFee(IntegrationTestCase):
	# APP-03: students -> tier -> fee per student x students, per course.
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_schedule()

	def fee(self, course):
		return frappe.db.get_value("App Course", course, ["subscriptions", "fee_per_student", "platform_fee_total"])

	def test_300_students_are_charged_60000(self):
		course = make_course("_Test 300 Course")
		subscribe(course, 300)
		self.assertEqual(self.fee(course), (300, 200, 60000))

	def test_100_students_are_charged_25000(self):
		# The top of the first tier.
		course = make_course("_Test 100 Course")
		subscribe(course, 100)
		self.assertEqual(self.fee(course), (100, 250, 25000))

	def test_501_students_are_charged_85170(self):
		# The first student over 500 moves the course to the third tier: 501 x 170.
		course = make_course("_Test 501 Course")
		subscribe(course, 501)
		self.assertEqual(self.fee(course), (501, 170, 85170))

	def test_new_tiers_from_a_later_date_leave_an_earlier_term_alone(self):
		# Prices from 1 Oct 2031 are for the terms that start from then; the term from 1 Sep 2031 keeps the
		# owner's tiers, and a term from 1 Oct takes the new ones.
		old = make_course("_Test Earlier Term Course")
		subscribe(old, 300)
		make_schedule("2031-10-01", [(1, None, 400)])
		self.assertEqual(self.fee(old), (300, 200, 60000))

		term = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": "_Test Later Term", "period_type": "Term", "start_date": "2031-10-01", "end_date": "2031-12-31"}
		).insert()
		new = make_course("_Test Later Term Course", period=term.name)
		subscribe(new, 300)
		self.assertEqual(self.fee(new), (300, 400, 120000))
		# A new subscription on the earlier term still counts by its own tiers.
		subscribe(old, 1)
		self.assertEqual(self.fee(old), (301, 200, 60200))

	def test_the_101st_student_moves_every_subscription_to_the_next_tier(self):
		course = make_course("_Test 101 Course")
		subscribe(course, 100)
		self.assertEqual(self.fee(course), (100, 250, 25000))
		last = subscribe(course, 1)[0]
		self.assertEqual(self.fee(course), (101, 200, 20200))
		fees = frappe.get_all("App Subscription", filters={"course": course, "docstatus": 1}, pluck="platform_fee")
		self.assertEqual(set(fees), {200})

		# A cancelled subscription is counted out again.
		last.cancel()
		self.assertEqual(self.fee(course), (100, 250, 25000))

	def test_each_course_is_counted_on_its_own(self):
		# Two courses of the same doctor, 80 students each: each in the first tier, not 160 in the second.
		agreement = make_agreement("App", 85)
		first, second = make_course("_Test First", agreement), make_course("_Test Second", agreement)
		subscribe(first, 80)
		subscribe(second, 80)
		self.assertEqual(self.fee(first), (80, 250, 20000))
		self.assertEqual(self.fee(second), (80, 250, 20000))

	@patch(COUNTED_PER, "doctor")
	def test_counted_on_all_the_doctors_courses_if_the_owner_says_so(self):
		# The same two courses counted together: 160 students, the second tier for both.
		agreement = make_agreement("App", 86)
		first, second = make_course("_Test First", agreement), make_course("_Test Second", agreement)
		subscribe(first, 80)
		subscribe(second, 80)
		self.assertEqual(self.fee(first), (80, 200, 16000))
		self.assertEqual(self.fee(second), (80, 200, 16000))

	def test_a_student_who_withdraws_is_still_counted(self):
		course = make_course("_Test Withdrawn Counted")
		withdrawn = subscribe(course, 101)[0]
		withdrawn.withdrawn = 1
		withdrawn.save()
		self.assertEqual(self.fee(course), (101, 200, 20200))
		self.assertEqual(frappe.db.get_value("App Subscription", withdrawn.name, "platform_fee"), 200)

	@patch(COUNT_WITHDRAWN, False)
	def test_a_student_who_withdraws_is_left_out_if_the_owner_says_so(self):
		course = make_course("_Test Withdrawn Left Out")
		withdrawn = subscribe(course, 101)[0]
		self.assertEqual(self.fee(course), (101, 200, 20200))
		withdrawn.withdrawn = 1
		withdrawn.save()
		# 100 left: back to the first tier, and nothing charged for him.
		self.assertEqual(self.fee(course), (100, 250, 25000))
		self.assertEqual(frappe.db.get_value("App Subscription", withdrawn.name, "platform_fee"), 0)

	def test_a_draft_is_not_counted(self):
		course = make_course("_Test Draft Course")
		subscribe(course, 2)
		frappe.get_doc(
			{"doctype": "App Subscription", "student": make_doctor("_Test Fee Student"), "course": course, "subscription_date": "2031-09-15", "cost_center": APP}
		).insert()
		self.assertEqual(self.fee(course), (2, 250, 500))

	def test_nothing_changes_once_the_term_is_closed(self):
		term = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": "_Test Closed Fee Term", "period_type": "Term", "start_date": VALID_FROM, "end_date": "2031-12-31"}
		).insert()
		course = make_course("_Test Closed Term Course", period=term.name)
		subscription = subscribe(course, 3)[0]
		frappe.db.set_value("Academic Period", term.name, "is_closed", 1)
		self.assertRaises(frappe.ValidationError, subscription.cancel)
		self.assertEqual(self.fee(course), (3, 250, 750))

	def test_new_tiers_charge_the_open_courses_again(self):
		# Its own term and tiers: 100 a student from 15 Dec 2035, for a term from 1 Jan 2036.
		make_schedule("2035-12-15", [(1, None, 100)])
		term = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": "_Test Repriced Term", "period_type": "Term", "start_date": "2036-01-01", "end_date": "2036-04-15"}
		).insert()
		course = make_course("_Test Repriced Course", period=term.name)
		subscribe(course, 10)
		self.assertEqual(self.fee(course), (10, 100, 1000))
		# New prices from before the term starts charge it again; withdrawn, the old ones are back.
		newer = make_schedule("2035-12-20", [(1, None, 120)])
		self.assertEqual(self.fee(course), (10, 120, 1200))
		frappe.get_doc("Platform Fee Schedule", newer).cancel()
		self.assertEqual(self.fee(course), (10, 100, 1000))
		# Prices from after the term starts do not touch it.
		make_schedule("2036-02-01", [(1, None, 500)])
		self.assertEqual(self.fee(course), (10, 100, 1000))
