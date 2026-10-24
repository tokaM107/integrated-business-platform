# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# BA Plus's daily file (INT-05, APP-13, INT-06, INT-07, INT-01): courses and subscriptions by their BA Plus ids, once
# however often the file comes, each failed row with its reason, nothing of it kept, and the fees and the doctor's
# account counted once. Synthetic rows only; everything is rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_app_import

import itertools
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp import app_import
from imed_erp.imederp.doctype.app_course.test_app_course import make_term
from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement
from imed_erp.imederp.doctype.platform_fee_schedule.test_platform_fee_schedule import make_schedule

# A test module outside a doctype folder builds no "_Test ..." records; keep it here, not under a doctype.
APP = "تطبيق BA Plus - MMG"
LIBRARY = "مكتبة المواساة - MMG"
# A subscription is never dated after today. The tests' term holds it, and so may the site's own terms: the
# import takes the one term a date falls in (app_import.term_of, tested on its own below), so the other tests
# point it at the tests' term.
DATE = "2026-10-15"
BLOCKS = itertools.count(1)


class IntegrationTestAppImport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_schedule()
		cls.term_of = patch.object(app_import, "term_of", return_value=make_term())
		cls.term_of.start()
		if not frappe.db.exists("Customer Group", app_import.STUDENT_GROUP):
			frappe.get_doc(
				{"doctype": "Customer Group", "customer_group_name": app_import.STUDENT_GROUP, "parent_customer_group": "All Customer Groups"}
			).insert()
		cls.agreement = make_agreement("App", 95)
		doc = frappe.get_doc("Doctor Agreement", cls.agreement)
		doc.ba_plus_doctor_id = "DR-1"
		doc.save()

	@classmethod
	def tearDownClass(cls):
		cls.term_of.stop()
		super().tearDownClass()

	def setUp(self):
		# The tests of a class share one transaction, rolled back at its end: each takes its own ids and phones.
		self.block = next(BLOCKS)

	def tearDown(self):
		frappe.set_user("Administrator")

	def sid(self, i):
		return f"B{self.block}-S-{i}"

	def cid(self, course):
		return f"B{self.block}-{course}"

	def rows(self, n, courses=("C-1",), doctor_id="DR-1", start=1, date=DATE):
		"""n subscriptions spread over the courses in turn, each a new student."""
		return [
			{
				"subscription_id": self.sid(i),
				"subscription_date": date,
				"course_id": self.cid(courses[(i - start) % len(courses)]),
				"course_name": f"_Test Imported {self.cid(courses[(i - start) % len(courses)])}",
				"doctor_id": doctor_id,
				"student_phone": f"015{self.block:03d}{i:05d}",
				"student_name": f"_Test Imported Student {self.block}-{i}",
			}
			for i in range(start, start + n)
		]

	def course(self, course):
		return frappe.db.get_value(
			"App Course", {"import_key": f"ba_plus:{self.cid(course)}"}, ["name", "course_name", "subscriptions", "platform_fee_total"], as_dict=True
		)

	def subscription(self, i):
		return frappe.get_doc("App Subscription", {"import_key": f"ba_plus:{self.sid(i)}"})

	def books(self):
		"""What is posted for the doctor: his ledger, its journal entries, their GL rows, his balance, his subscriptions."""
		entries = frappe.get_all("Doctor Ledger Entry", filters={"agreement": self.agreement, "docstatus": 1}, fields=["journal_entry"])
		journal_entries = [e.journal_entry for e in entries if e.journal_entry]
		return (
			len(entries),
			len(set(journal_entries)),
			frappe.db.count("GL Entry", {"voucher_no": ("in", journal_entries or [""]), "is_cancelled": 0}),
			frappe.db.get_value("Doctor Agreement", self.agreement, "balance"),
			frappe.db.count("App Subscription", {"agreement": self.agreement, "docstatus": 1}),
		)

	# ---------- the definition of done ----------

	def test_ten_subscriptions_in_two_courses(self):
		before = self.books()
		log = app_import.import_rows(self.rows(10, ("C-1", "C-2")), file_name="ba_plus_2026-10-15.csv", content="file")
		self.assertEqual(
			(log.status, log.rows_read, log.inserted, log.records_created, log.skipped, log.changed, log.failed),
			("Completed", 10, 10, 12, 0, 0, 0),  # 2 courses and 10 students made on the way
		)
		self.assertEqual((log.source_system, log.file_name, log.run_by), ("ba_plus", "ba_plus_2026-10-15.csv", "Administrator"))
		self.assertTrue(log.file_hash)
		# 5 students each, 250 a student (the first tier).
		for course in ("C-1", "C-2"):
			values = self.course(course)
			self.assertEqual((values.subscriptions, values.platform_fee_total), (5, 1250))
			self.assertEqual(frappe.db.get_value("App Course", values.name, "import_log"), log.name)
		subscription = self.subscription(1)
		self.assertEqual(
			(subscription.docstatus, subscription.source, subscription.external_id, subscription.cost_center, subscription.import_log),
			(1, "Imported", self.sid(1), APP, log.name),
		)
		self.assertEqual(self.books()[3], before[3] + 2500)

	def test_the_same_file_again_adds_nothing(self):
		data = self.rows(10, ("C-1", "C-2"))
		app_import.import_rows(data)
		before = self.books()
		log = app_import.import_rows(data)
		self.assertEqual((log.status, log.inserted, log.skipped, log.records_created, log.failed), ("Completed", 0, 10, 0, 0))
		# No subscription, ledger entry, journal entry, GL row or fee twice.
		self.assertEqual(self.books(), before)
		self.assertEqual(frappe.db.count("App Course", {"import_key": ("like", f"ba_plus:{self.cid('C-')}%")}), 2)

	def test_an_unknown_doctor_fails_its_row_and_the_others_go_on(self):
		data = self.rows(10, ("C-1", "C-2"))
		data[4]["doctor_id"] = "DR-UNKNOWN"
		log = app_import.import_rows(data)
		self.assertEqual((log.status, log.inserted, log.failed), ("Completed with Errors", 9, 1))
		[error] = log.errors
		# The header is line 1, so the fifth row is line 6.
		self.assertEqual((error.row_no, error.external_id, error.kind), (6, self.sid(5), "Failed"))
		self.assertIn("DR-UNKNOWN", error.reason)
		self.assertFalse(frappe.db.exists("App Subscription", {"import_key": f"ba_plus:{self.sid(5)}"}))

	def test_one_course_for_many_subscriptions(self):
		log = app_import.import_rows(self.rows(6, ("C-9",)))
		self.assertEqual(frappe.db.count("App Course", {"import_key": f"ba_plus:{self.cid('C-9')}"}), 1)
		self.assertEqual(self.course("C-9").subscriptions, 6)
		self.assertEqual(log.records_created, 7)  # the course once, 6 students

	def test_a_change_in_the_source_is_listed_not_written(self):
		app_import.import_rows(self.rows(3))
		data = self.rows(3)
		data[1]["subscription_date"] = "2026-10-16"
		data[2]["course_name"] = "_Test Renamed in BA Plus"
		before = self.books()
		log = app_import.import_rows(data + self.rows(1, start=4))
		# Row 2 changed; row 3's course was renamed (the course is listed, the row itself is skipped); 1 new.
		self.assertEqual((log.status, log.inserted, log.skipped, log.changed), ("Completed with Errors", 1, 2, 2))
		self.assertEqual(
			{(e.external_id, e.kind) for e in log.errors},
			{(self.sid(2), "Changed in Source"), (self.cid("C-1"), "Changed in Source")},
		)
		# Nothing overwritten: the date and the course's name are as first imported.
		self.assertEqual(str(self.subscription(2).subscription_date), DATE)
		self.assertEqual(self.course("C-1").course_name, f"_Test Imported {self.cid('C-1')}")
		# Only the new student was posted.
		self.assertEqual(self.books()[3], before[3] + 250)

	def test_a_failed_row_leaves_nothing_behind(self):
		# A new course and a bad phone on its first row: the course is made again, once, by the next row.
		data = self.rows(2, ("C-NEW",))
		data[0]["student_phone"] = "not a phone"
		log = app_import.import_rows(data)
		self.assertEqual((log.inserted, log.failed, log.records_created), (1, 1, 2))
		self.assertEqual(frappe.db.count("App Course", {"import_key": f"ba_plus:{self.cid('C-NEW')}"}), 1)
		self.assertEqual(self.course("C-NEW").subscriptions, 1)

		alone = self.rows(1, ("C-ALONE",), start=50)
		alone[0]["student_phone"] = "not a phone"
		log = app_import.import_rows(alone)
		self.assertEqual((log.failed, log.records_created), (1, 0))
		self.assertFalse(self.course("C-ALONE"))

	def test_a_course_goes_in_the_one_term_its_date_falls_in(self):
		self.term_of.stop()
		try:
			self.assertRaisesRegex(frappe.ValidationError, "0 terms", app_import.term_of, "1990-06-01")
			for name in ("_Test Import Term A", "_Test Import Term B"):
				frappe.get_doc(
					{"doctype": "Academic Period", "period_name": name, "period_type": "Term", "start_date": "1990-05-01", "end_date": "1990-06-30"}
				).insert()
			self.assertRaisesRegex(frappe.ValidationError, "2 terms", app_import.term_of, "1990-06-01")
			frappe.db.set_value("Academic Period", "_Test Import Term B", {"start_date": "1990-07-01", "end_date": "1990-08-31"})
			self.assertEqual(app_import.term_of("1990-06-01"), "_Test Import Term A")
		finally:
			self.term_of.start()

	# ---------- the cost center and the imported records ----------

	def test_a_subscription_is_always_on_the_apps_cost_center(self):
		app_import.import_rows(self.rows(1))
		student = frappe._dict(self.rows(1, start=70)[0])
		doc = frappe.get_doc(
			{
				"doctype": "App Subscription",
				"student": app_import.find_or_make_student(student, app_import.normalize_phone(student.student_phone))[0],
				"course": self.course("C-1").name,
				"subscription_date": DATE,
				"cost_center": LIBRARY,
			}
		).insert()
		self.assertEqual(doc.cost_center, APP)

	def test_an_imported_record_is_changed_only_in_ba_plus(self):
		app_import.import_rows(self.rows(1))
		subscription = self.subscription(1)
		subscription.withdrawn = 1
		self.assertRaisesRegex(frappe.ValidationError, "imported", subscription.save)
		course = frappe.get_doc("App Course", self.course("C-1").name)
		course.course_name = "_Test Renamed Here"
		self.assertRaisesRegex(frappe.ValidationError, "imported", course.save)
		# Closing it to new students is the ERP's own.
		course.reload()
		course.status = "Closed"
		course.save()
		# A record entered by hand cannot claim to be imported.
		manual = frappe.get_doc(
			{
				"doctype": "App Course",
				"course_name": f"_Test Manual {self.block}",
				"agreement": self.agreement,
				"period": make_term(),
				"source": "Imported",
				"external_id": "FAKE",
				"import_key": "ba_plus:FAKE",
			}
		).insert()
		self.assertEqual((manual.source, manual.import_key), ("Manual", None))

	# ---------- the log ----------

	def test_the_log_is_written_only_by_the_import(self):
		log = frappe.get_doc({"doctype": "Integration Import Log", "source_system": "ba_plus", "status": "Completed"})
		self.assertRaises(frappe.PermissionError, log.insert)
		written = frappe.get_doc("Integration Import Log", app_import.import_rows(self.rows(1)).name)
		written.status = "Failed"
		self.assertRaises(frappe.PermissionError, written.save)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Integration Import Log", written.name)

	def test_a_run_the_database_drops_is_logged_as_failed(self):
		def rollback(save_point=None, **kwargs):
			if save_point:
				raise Exception("Deadlock found when trying to get lock")
			# The whole run's rollback: the test's own records are rolled back at the class's end.

		with patch.object(app_import, "import_row", side_effect=Exception("boom")), patch.object(
			frappe.db, "rollback", side_effect=rollback
		), patch.object(frappe.db, "commit"):
			log = app_import.import_rows(self.rows(3))
		self.assertEqual((log.status, log.rows_read, log.inserted, log.records_created), ("Failed", 1, 0, 0))
		self.assertIn("Deadlock", log.message)

	def test_who_may_import(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, app_import.import_rows, self.rows(1))

	def test_a_file_without_a_column_is_refused(self):
		self.assertRaisesRegex(frappe.ValidationError, "student_phone", app_import.import_content, "subscription_id,course_id\nS-1,C-1\n")

	def test_a_file_is_read_from_csv(self):
		header = ",".join(app_import.COLUMNS)
		lines = [",".join(r[c] for c in app_import.COLUMNS) for r in self.rows(2)]
		log = app_import.import_content(("\n".join([header, *lines]) + "\n").encode("utf-8-sig"), file_name="app.csv")
		self.assertEqual((log.inserted, log.file_name), (2, "app.csv"))

	# ---------- the doctor's BA Plus id ----------

	def test_a_ba_plus_id_names_one_agreement(self):
		other = frappe.get_doc("Doctor Agreement", make_agreement("App", 96))
		other.ba_plus_doctor_id = "DR-1"
		self.assertRaisesRegex(frappe.ValidationError, "already on agreement", other.save)
		books = frappe.get_doc("Doctor Agreement", make_agreement("Books", 97))
		books.ba_plus_doctor_id = "DR-BOOKS"
		books.save()
		self.assertIsNone(books.ba_plus_doctor_id)

	# ---------- the integrations screen (INT-09) ----------

	def csv(self, data):
		return ("\n".join([",".join(app_import.COLUMNS), *(",".join(r[c] for c in app_import.COLUMNS) for r in data)]) + "\n").encode()

	def status(self):
		from imed_erp.imederp.report.integration_status.integration_status import execute

		return {row["system"]: row for row in execute()[1]}

	def test_the_screen_shows_each_systems_last_import(self):
		good = app_import.import_content(self.csv(self.rows(3)), file_name="good.csv")
		rows = self.status()
		self.assertEqual(set(rows), {"ba_plus", "library_pos", "booking"})
		ba_plus = rows["ba_plus"]
		self.assertEqual((ba_plus["log"], ba_plus["inserted"], ba_plus["failed"]), (good.name, 3, 0))
		self.assertIn("no import reads", rows["library_pos"]["note"].lower())

		# A later run that failed as a whole does not hide the last one that went through.
		with patch.object(app_import, "import_row", side_effect=Exception("boom")), patch.object(
			frappe.db, "rollback", side_effect=lambda save_point=None, **kw: (_ for _ in ()).throw(Exception("Deadlock")) if save_point else None
		), patch.object(frappe.db, "commit"):
			failed = app_import.import_rows(self.rows(1, start=10), file_name="dropped.csv")
		ba_plus = self.status()["ba_plus"]
		self.assertEqual((ba_plus["log"], ba_plus["last_run_status"]), (good.name, "Failed"))
		self.assertIn("failed", ba_plus["note"])
		self.assertEqual(frappe.db.get_value("Integration Import Log", failed.name, "status"), "Failed")

	def test_a_period_imported_again_brings_in_only_what_failed(self):
		from imed_erp.imederp.report.integration_status.integration_status import reimport_period

		# The file's 3rd row has a doctor id not yet written on any agreement: it fails.
		data = self.rows(4)
		data[2].update(doctor_id="DR-LATE", course_id=self.cid("C-LATE"), course_name="_Test Late Doctor's Course")
		first = app_import.import_content(self.csv(data), file_name="day.csv")
		self.assertEqual((first.inserted, first.failed), (3, 1))
		self.assertEqual(frappe.db.get_value("Integration Import Log", first.name, "file_content"), self.csv(data).decode())
		before = self.books()

		# The accountant writes the id on the agreement, then imports the day again.
		late = frappe.get_doc("Doctor Agreement", make_agreement("App", 98))
		late.ba_plus_doctor_id = "DR-LATE"
		late.save()
		today = frappe.utils.today()
		[run] = [r for r in reimport_period("ba_plus", today, today) if r["from"] == first.name]
		self.assertEqual((run["inserted"], run["skipped"], run["failed"]), (1, 3, 0))
		# The three already in were not posted again.
		self.assertEqual(self.books(), before)
		self.assertTrue(frappe.db.exists("App Subscription", {"import_key": f"ba_plus:{self.sid(3)}", "agreement": late.name}))

	def test_a_period_imported_again_runs_each_file_once(self):
		from imed_erp.imederp.report.integration_status.integration_status import reimport_period

		content = self.csv(self.rows(2))
		first = app_import.import_content(content, file_name="twice.csv")
		app_import.import_content(content, file_name="twice-again.csv")
		today = frappe.utils.today()
		runs = [r for r in reimport_period("ba_plus", today, today)]
		hashes = [frappe.db.get_value("Integration Import Log", r["from"], "file_hash") for r in runs]
		self.assertEqual(len(hashes), len(set(hashes)))
		self.assertEqual(hashes.count(frappe.db.get_value("Integration Import Log", first.name, "file_hash")), 1)

	def test_who_may_import_a_period_again(self):
		from imed_erp.imederp.report.integration_status.integration_status import reimport_period

		today = frappe.utils.today()
		self.assertRaisesRegex(frappe.ValidationError, "No import reads", reimport_period, "library_pos", today, today)
		self.assertRaisesRegex(frappe.ValidationError, "No file", reimport_period, "ba_plus", "1990-01-01", "1990-01-02")
		frappe.set_user("sara@imed.local")
		self.assertRaises(frappe.PermissionError, reimport_period, "ba_plus", today, today)
