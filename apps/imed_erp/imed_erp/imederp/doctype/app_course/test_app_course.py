# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# App courses (APP-01, requirements v1.2): a course belongs to an app agreement and a term, the doctor comes
# from the agreement, and a course is not made twice in a term. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "App Course"

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement

# Every doctype these tests link to is made here or already exists on the site. Without this Frappe builds
# ERPNext's "_Test ..." records for them and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Academic Period", "App Course", "Customer", "Doctor Agreement"]


def make_term(name="_Test Course Term"):
	if frappe.db.exists("Academic Period", name):
		return name
	return (
		frappe.get_doc(
			{"doctype": "Academic Period", "period_name": name, "period_type": "Term", "start_date": "2026-09-01", "end_date": "2026-12-31"}
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
				"start_date": "2026-09-01",
				"end_date": "2026-10-31",
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
