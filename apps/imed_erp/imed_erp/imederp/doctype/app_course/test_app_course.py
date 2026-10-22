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
from frappe.utils import today

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement, make_doctor
from imed_erp.imederp.doctype.platform_fee_schedule.test_platform_fee_schedule import VALID_FROM, make_schedule

# Every doctype these tests link to is made here or already exists on the site. Without this Frappe builds
# ERPNext's "_Test ..." records for them and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Academic Period",
	"App Course",
	"App Subscription",
	"Cost Center",
	"Customer",
	"Doctor Agreement",
	"Integration Import Log",
	"Platform Fee Schedule",
]

APP = "تطبيق BA Plus - MMG"


def make_term(name="_Test Course Term"):
	if frappe.db.exists("Academic Period", name):
		return name
	return (
		frappe.get_doc(
			# Starts when the tests' fee schedule does, so its fees are the owner's tiers whatever the site holds.
			{"doctype": "Academic Period", "period_name": name, "period_type": "Term", "start_date": VALID_FROM, "end_date": "2027-06-30"}
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
				"end_date": "2026-12-31",
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
	# Each subscription is another student: a student counts once in a course.
	start = frappe.db.count("App Subscription", {"course": course})
	# Dated in the course's term (QA-17): 15 Sep 2026 in the tests' term, else the first day of the course's own.
	term = frappe.db.get_value(
		"Academic Period", frappe.db.get_value("App Course", course, "period"), ["start_date", "end_date"], as_dict=True
	)
	date = "2026-09-15" if str(term.start_date) <= "2026-09-15" <= str(term.end_date) else term.start_date
	subscriptions = []
	for i in range(start, start + count):
		doc = frappe.get_doc(
			{"doctype": "App Subscription", "student": make_student(i), "course": course, "subscription_date": date, "cost_center": APP}
		).insert()
		doc.submit()
		subscriptions.append(doc)
	return subscriptions


COUNTED_PER = "imed_erp.imederp.doctype.app_course.app_course.TIER_COUNTED_PER"
COUNT_WITHDRAWN = "imed_erp.imederp.doctype.app_course.app_course.COUNT_WITHDRAWN"


def make_student(i):
	return make_doctor(f"_Test Fee Student {i}")


class IntegrationTestPlatformFee(IntegrationTestCase):
	# APP-03: students -> tier -> fee per student x students, per course. Counting only: posting each change to
	# the doctor's account (a journal entry a subscription) has its own tests below and would make these slow.
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_schedule()
		cls.no_posting = patch("imed_erp.imederp.platform_fee_posting.post_fee_change")
		cls.no_posting.start()

	@classmethod
	def tearDownClass(cls):
		cls.no_posting.stop()
		super().tearDownClass()

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
		# Prices from 1 Oct 2026 are for the terms that start from then; the term from 2 Sep 2026 keeps the
		# owner's tiers, and a term from 1 Oct takes the new ones.
		old = make_course("_Test Earlier Term Course")
		subscribe(old, 300)
		make_schedule("2026-10-01", [(1, None, 400)])
		self.assertEqual(self.fee(old), (300, 200, 60000))

		term = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": "_Test Later Term", "period_type": "Term", "start_date": "2026-10-01", "end_date": "2026-12-31"}
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
			{"doctype": "App Subscription", "student": make_student(999), "course": course, "subscription_date": "2026-09-15", "cost_center": APP}
		).insert()
		self.assertEqual(self.fee(course), (2, 250, 500))

	def test_nothing_changes_once_the_term_is_closed(self):
		term = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": "_Test Closed Fee Term", "period_type": "Term", "start_date": VALID_FROM, "end_date": "2027-06-30"}
		).insert()
		course = make_course("_Test Closed Term Course", period=term.name)
		subscription = subscribe(course, 3)[0]
		frappe.db.set_value("Academic Period", term.name, "is_closed", 1)
		self.assertRaises(frappe.ValidationError, subscription.cancel)
		self.assertEqual(self.fee(course), (3, 250, 750))

	def test_new_tiers_charge_the_open_courses_again(self):
		# Its own term and tiers: 100 a student from 3 Sep 2026, for a term from 5 Sep 2026.
		make_schedule("2026-09-03", [(1, None, 100)])
		term = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": "_Test Repriced Term", "period_type": "Term", "start_date": "2026-09-05", "end_date": "2026-12-31"}
		).insert()
		course = make_course("_Test Repriced Course", period=term.name)
		subscribe(course, 10)
		self.assertEqual(self.fee(course), (10, 100, 1000))
		# New prices from before the term starts charge it again; withdrawn, the old ones are back.
		newer = make_schedule("2026-09-04", [(1, None, 120)])
		self.assertEqual(self.fee(course), (10, 120, 1200))
		frappe.get_doc("Platform Fee Schedule", newer).cancel()
		self.assertEqual(self.fee(course), (10, 100, 1000))
		# Prices from after the term starts do not touch it.
		make_schedule("2026-09-06", [(1, None, 500)])
		self.assertEqual(self.fee(course), (10, 100, 1000))

	def test_the_platform_fees_report(self):
		# APP-07: students per course and per doctor, the tier applied and the fee due.
		from imed_erp.imederp.report.platform_fees import platform_fees

		agreement = make_agreement("App", 87)
		course = make_course("_Test Report Course", agreement)
		subscribe(course, 300)
		doctor = frappe.db.get_value("Doctor Agreement", agreement, "doctor")
		rows = platform_fees.execute({"agreement": agreement, "doctor": doctor})[1]
		self.assertEqual(
			[(r["course_name"], r["subscriptions"], r["tier"], r["fee_per_student"], r["platform_fee_total"]) for r in rows],
			[("_Test Report Course", 300, "101–500", 200, 60000)],
		)
		roles = {r.role for r in frappe.get_doc("Report", "Platform Fees").roles}
		self.assertEqual(roles, {"System Manager", "Accounts Manager"})


APP_TREASURY = "خزينة تطبيق BA Plus - MMG"


class IntegrationTestPlatformFeePosting(IntegrationTestCase):
	# APP-05: the doctor's account follows each course's fee, with every student; APP-06: collected into a treasury.
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_schedule()

	def ledger(self, course):
		return frappe.get_all(
			"Doctor Ledger Entry",
			filters={"app_course": course, "docstatus": 1},
			fields=["entry_type", "amount", "journal_entry"],
			order_by="creation",
		)

	def gl(self, journal_entry):
		return {
			(row.account.rsplit(" - ", 1)[0], row.party or ""): (row.debit, row.credit)
			for row in frappe.get_all(
				"GL Entry", filters={"voucher_no": journal_entry, "is_cancelled": 0}, fields=["account", "party", "debit", "credit"]
			)
		}

	def test_each_student_adds_his_fee_to_the_doctors_account(self):
		agreement = make_agreement("App", 88)
		doctor = frappe.db.get_value("Doctor Agreement", agreement, "doctor")
		course = make_course("_Test Posted Course", agreement)
		subscribe(course, 3)
		entries = self.ledger(course)
		self.assertEqual([(e.entry_type, e.amount) for e in entries], [("Accrual", 250)] * 3)
		self.assertEqual(frappe.db.get_value("Doctor Agreement", agreement, "balance"), 750)
		self.assertEqual(
			self.gl(entries[0].journal_entry),
			{("مستحقات على الأطباء — رسوم المنصة", doctor): (250, 0), ("إيراد رسوم المنصة", ""): (0, 250)},
		)

	def test_the_101st_student_lowers_the_account_to_the_new_tier(self):
		agreement = make_agreement("App", 89)
		course = make_course("_Test Posted 101", agreement)
		subscriptions = subscribe(course, 101)
		# 100 x 250 = 25,000, then 101 x 200 = 20,200: 4,800 less, in one adjustment.
		last = self.ledger(course)[-1]
		self.assertEqual((last.entry_type, last.amount), ("Adjustment", -4800))
		self.assertEqual(frappe.db.get_value("Doctor Agreement", agreement, "balance"), 20200)
		doctor = frappe.db.get_value("Doctor Agreement", agreement, "doctor")
		self.assertEqual(
			self.gl(last.journal_entry),
			{("مستحقات على الأطباء — رسوم المنصة", doctor): (0, 4800), ("إيراد رسوم المنصة", ""): (4800, 0)},
		)
		# Cancelled, the student goes and the course is back at 25,000.
		subscriptions[-1].cancel()
		self.assertEqual(frappe.db.get_value("Doctor Agreement", agreement, "balance"), 25000)

	def test_the_courses_entries_are_the_systems(self):
		agreement = make_agreement("App", 90)
		course = make_course("_Test Kept Entries", agreement)
		subscribe(course, 1)
		entry = frappe.get_doc("Doctor Ledger Entry", {"app_course": course, "docstatus": 1})
		# No approval, no statement email, and nobody cancels them by hand.
		self.assertFalse(entry.approval_status)
		self.assertRaisesRegex(frappe.ValidationError, "changes with the course", entry.cancel)

	def test_a_collection_goes_into_a_treasury(self):
		agreement = make_agreement("App", 91)
		doctor = frappe.db.get_value("Doctor Agreement", agreement, "doctor")
		course = make_course("_Test Collected Course", agreement)
		subscribe(course, 2)

		def collection(amount, **values):
			return frappe.get_doc(
				{"doctype": "Doctor Ledger Entry", "agreement": agreement, "entry_type": "Collection", "amount": amount, "entry_date": today(), **values}
			).insert()

		self.assertRaisesRegex(frappe.ValidationError, "goes into", collection, 300)
		self.assertRaisesRegex(frappe.ValidationError, "more than that", collection, 501, treasury=APP_TREASURY)
		paid = collection(300, treasury=APP_TREASURY)
		paid.submit()
		self.assertEqual(frappe.db.get_value("Doctor Agreement", agreement, "balance"), 200)
		self.assertEqual(
			self.gl(paid.journal_entry),
			{("خزينة تطبيق BA Plus", ""): (300, 0), ("مستحقات على الأطباء — رسوم المنصة", doctor): (0, 300)},
		)
		# Cancelled, the money goes back out of the treasury.
		paid.cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", paid.journal_entry, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Doctor Agreement", agreement, "balance"), 500)

	def test_card_definition_of_done_300_students_40000_collected_20000_carried(self):
		# 300 students -> 60,000 owed by the doctor (Dr receivable / Cr revenue); 40,000 collected into the app's
		# treasury; the 20,000 left is a debt (APP-08) and the next term's balance brought forward (APP-12), and the
		# app statement shows the course, its students, tier and fee (APP-11).
		from imed_erp.imederp.report.doctor_debts.doctor_debts import execute as debts
		from imed_erp.imederp.report.doctor_statement.doctor_statement import execute as statement

		agreement = make_agreement("App", 92)
		doctor = frappe.db.get_value("Doctor Agreement", agreement, "doctor")
		term = make_term()
		course = make_course("_Test Done Course", agreement, term)
		subscribe(course, 300)
		journal_entries = [e.journal_entry for e in self.ledger(course)]
		receivable = frappe.db.sql(
			"""select sum(debit - credit) from `tabGL Entry` where voucher_no in %s and is_cancelled = 0
			and party = %s""",
			(journal_entries, doctor),
		)[0][0]
		revenue = frappe.db.sql(
			"""select sum(credit - debit) from `tabGL Entry` where voucher_no in %s and is_cancelled = 0
			and account like 'إيراد رسوم المنصة%%'""",
			(journal_entries,),
		)[0][0]
		self.assertEqual((receivable, revenue), (60000, 60000))

		collected = frappe.get_doc(
			{
				"doctype": "Doctor Ledger Entry",
				"agreement": agreement,
				"period": term,
				"entry_type": "Collection",
				"amount": 40000,
				"entry_date": today(),
				"treasury": APP_TREASURY,
			}
		).insert()
		collected.submit()
		self.assertEqual(frappe.db.get_value("Doctor Agreement", agreement, "balance"), 20000)
		self.assertEqual({r["agreement"]: r["debt"] for r in debts({"as_of": today()})[1]}.get(agreement), 20000)

		columns, rows, _message, _chart, summary = statement({"agreement": agreement, "period": term})
		self.assertIn("course_name", [c["fieldname"] for c in columns])
		[fee] = [r for r in rows if r.get("course_name") == "_Test Done Course"]
		self.assertEqual(
			(fee["students"], fee["tier"], fee["fee_per_student"], fee["owed"]), (300, "101–500", 200, 60000)
		)
		self.assertEqual(rows[-1]["balance"], 20000)

		# The next term starts from the 20,000 still owed.
		later = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": "_Test Next Fee Term", "period_type": "Term", "start_date": "2032-01-01", "end_date": "2032-04-15"}
		).insert()
		rows = statement({"agreement": agreement, "period": later.name})[1]
		self.assertEqual((rows[0]["balance"], rows[-1]["balance"]), (20000, 20000))

	def test_qa34_the_tier_is_kept_as_counted(self):
		from imed_erp.imederp.report.platform_fees.platform_fees import execute as platform_fees

		course = make_course("_Test Kept Tier")
		subscribe(course, 1)
		self.assertEqual(frappe.db.get_value("App Course", course, "tier"), "1–100")
		# A schedule entered later for the same term would put 1 student in another tier: the label stays.
		other = frappe._dict(from_students=1, to_students=None)
		with patch("imed_erp.imederp.report.platform_fees.platform_fees.get_tier", return_value=other):
			rows = {r["name"]: r for r in platform_fees({"period": frappe.db.get_value("App Course", course, "period")})[1]}
		self.assertEqual(rows[course]["tier"], "1–100")
