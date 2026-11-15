# The center's store, kept by the owner (imederp/center_store.py; the owner, 15 Nov 2026: the dearer ink is at the
# center and the owner is in charge of it): he counts it and sends from it to a library; the owner's day report then
# shows the center's ink sent and the library's ink held. Everything made here is rolled back.
#
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_center_store
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from imed_erp.imederp import center_store, library_day, owner_periods

INK = "_TEST-INK-CENTER"
LIBRARY = "مكتبة الأزاريطة - MMG"


class TestCenterStore(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("center_store")
		self.store = center_store.center_store()
		if not self.store:
			self.skipTest("no center store on this site")
		if not frappe.db.exists("Item", INK):
			frappe.get_doc({"doctype": "Item", "item_code": INK, "item_name": "حبر غالي تجربة", "item_group": center_store.INK_GROUP, "stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": 900}).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="center_store")
		frappe.clear_cache()

	def held(self, store):
		return flt(frappe.db.get_value("Bin", {"item_code": INK, "warehouse": store}, "actual_qty"))

	def test_the_owner_counts_the_center_then_sends_ink_to_a_library(self):
		self.assertIn(INK, [i["item_code"] for i in center_store.get_center()["items"]])
		center_store.count({INK: 6})
		self.assertEqual(self.held(self.store), 6)
		to = library_day.libraries()[LIBRARY]
		before = self.held(to)
		self.assertRaises(frappe.ValidationError, center_store.send, INK, 2, LIBRARY)  # who received it, always
		sent = center_store.send(INK, 2, LIBRARY, "سارة")
		self.assertEqual(sent["left"], 4)
		self.assertEqual(self.held(to), before + 2)
		entry = frappe.get_doc("Stock Entry", sent["entry"])
		self.assertEqual((entry.stock_entry_type, entry.items[0].cost_center, entry.custom_received_by), ("Material Transfer", LIBRARY, "سارة"))
		# The owner's day: the center sent 2 and used none; the library's store holds them, and did not use them.
		center = next(d for d in library_day.day_report("سنتر") if d.get("kind") == "center")
		row = next(r for r in center["supplies"] if r["item"] == "حبر غالي تجربة")
		self.assertEqual((row["on_hand"], row["used_that_day"], row["sent_to_libraries_that_day"]), (4, 0, 2))
		# The owner's page: the center's store last, with the ink.
		stores = owner_periods.stock()
		self.assertEqual(stores[-1]["center"], 1)
		self.assertIn(INK, [r["item_code"] for r in stores[-1]["items"]])

	def test_never_more_than_the_center_holds(self):
		center_store.count({INK: 1})
		self.assertRaises(frappe.ValidationError, center_store.send, INK, 3, LIBRARY, "سارة")
		self.assertRaises(frappe.ValidationError, center_store.send, INK, 1, "مكتبة ليست موجودة", "سارة")
		self.assertRaises(frappe.ValidationError, center_store.send, "A4-PAPER-NOT-HELD", 1, LIBRARY, "سارة")

	def test_only_the_owner_keeps_it(self):
		for user in ("accountant@imed.local", "sara@imed.local", "mowasah@imed.local", "azarita@imed.local"):
			if frappe.db.exists("User", user):
				frappe.set_user(user)
				self.assertRaises(frappe.PermissionError, center_store.get_center)
				self.assertRaises(frappe.PermissionError, center_store.count, {INK: 1})
				self.assertRaises(frappe.PermissionError, center_store.send, INK, 1, LIBRARY, "سارة")
				frappe.set_user("Administrator")
