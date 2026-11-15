# A library's day for the owner (imederp/library_day.py, the owner, 15 Nov 2026: "how much paper Azarita has, how
# much paper and ink it used today"), read from what the library records on مكتبتي.
#
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_library_day
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from imed_erp.imederp import library_day


class TestLibraryDay(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_each_library_its_counters_supplies_and_last_count(self):
		days = library_day.day_report()
		self.assertTrue(days, "no library store on this site")
		for d in days:
			self.assertEqual(d["day"], today())
			self.assertIn(d["counters"]["state"], ("not_recorded", "morning_only", "closed"))
			for row in d["supplies"]:
				self.assertGreaterEqual(row["used_that_day"], 0)
				self.assertIn("on_hand", row)

	def test_a_library_is_found_by_any_part_of_its_name(self):
		names = [lib.rsplit(" - ", 1)[0] for lib in library_day.libraries()]
		for name in names:
			word = name.replace("مكتبة", "").strip()
			self.assertEqual([d["library"] for d in library_day.day_report(word)], [name])
		self.assertRaises(frappe.ValidationError, library_day.day_report, "مكتبة ليست موجودة")

	def test_only_the_owner_reads_it(self):
		for user in ("accountant@imed.local", "sara@imed.local", "mowasah@imed.local"):
			if frappe.db.exists("User", user):
				frappe.set_user(user)
				self.assertRaises(frappe.PermissionError, library_day.get_day)
				frappe.set_user("Administrator")

	def test_the_assistant_answers_it_for_the_owner_only(self):
		from imed_erp.assistant.businesses.imed import ImedIntegration

		owner, branch = frappe._dict(all_companies=True), frappe._dict(all_companies=False)
		self.assertIn("library_supplies_day", [t.name for t in ImedIntegration().tools(owner)])
		self.assertNotIn("library_supplies_day", [t.name for t in ImedIntegration().tools(branch)])
