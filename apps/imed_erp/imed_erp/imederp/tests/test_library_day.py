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
			if d.get("kind") == "center":
				continue
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

	def test_the_center_store_holds_every_ink_and_what_it_sent_on(self):
		if not library_day.center_store():
			self.skipTest("no center store on this site")
		for asked in ("سنتر", "السنتر", "Imed center"):
			days = library_day.day_report(asked)
			self.assertEqual([d.get("kind") for d in days], ["center"])
		center = days[0]
		inks = frappe.get_all("Item", filters={"item_group": library_day.INK_GROUP, "disabled": 0, "is_stock_item": 1}, pluck="item_name")
		self.assertTrue(set(inks) <= {r["item"] for r in center["supplies"]})
		for row in center["supplies"]:
			self.assertGreaterEqual(row["sent_to_libraries_that_day"], 0)
		# Asked for a library, the center does not come with it.
		self.assertNotIn("center", [d.get("kind") for d in library_day.day_report("الأزاريطة")])
		self.assertIn("center", [d.get("kind") for d in library_day.day_report()])

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
