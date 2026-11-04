# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A library's shared account and its screen مكتبتي (imederp/library_desk.py; owner, 4 Nov 2026): what it holds, a
# count, something finished, a request; its own library and store only, and no money. The role, its rights, the
# account and the ink items are made here and rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_library_desk

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from imed_erp.imederp import library_desk as desk

ACCOUNT = "_lib_mawasah@imed.test"
LIBRARY = "مكتبة المواساة - MMG"
STORE = "خامات المواساة - MMG"
INK = "_TEST-INK-RISO"


class IntegrationTestLibraryDesk(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("library_desk")
		from frappe.permissions import add_permission

		if not frappe.db.exists("Role", desk.ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": desk.ROLE, "desk_access": 1}).insert(ignore_permissions=True)
		for doctype, rights in desk.STAFF_RIGHTS.items():
			name = frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": desk.ROLE, "permlevel": 0})
			if not name:
				from frappe.permissions import setup_custom_perms

				setup_custom_perms(doctype)
				name = add_permission(doctype, desk.ROLE, 0)
			frappe.db.set_value("Custom DocPerm", name, rights)
			frappe.clear_cache(doctype=doctype)
		if not frappe.db.exists("Item Group", "أحبار"):
			frappe.get_doc({"doctype": "Item Group", "item_group_name": "أحبار", "parent_item_group": frappe.db.get_value("Item Group", "ورق", "parent_item_group") or "All Item Groups"}).insert()
		if not frappe.db.exists("Item", INK):
			frappe.get_doc({"doctype": "Item", "item_code": INK, "item_name": "حبر ريزو تجربة", "item_group": "أحبار", "stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": 3000}).insert()
		if not frappe.db.exists("User", ACCOUNT):
			frappe.get_doc({"doctype": "User", "email": ACCOUNT, "first_name": "مكتبة المواساة", "send_welcome_email": 0, "roles": [{"role": desk.ROLE}]}).insert(ignore_permissions=True)
		for allow, value in (("Company", "Mohamed Mamdouh group"), ("Cost Center", LIBRARY), ("Warehouse", STORE)):
			frappe.get_doc({"doctype": "User Permission", "user": ACCOUNT, "allow": allow, "for_value": value, "apply_to_all_doctypes": 1}).insert(ignore_permissions=True)
		frappe.clear_cache(user=ACCOUNT)
		# Paper as on a real site: it has a price (0.26 a sheet) before a library first counts it.
		if not flt(frappe.db.get_value("Item", "A4-PAPER", "valuation_rate")):
			frappe.db.set_value("Item", "A4-PAPER", "valuation_rate", 0.26)
			frappe.clear_document_cache("Item", "A4-PAPER")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="library_desk")
		frappe.clear_cache()

	def held(self, item=INK):
		return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": STORE}, "actual_qty"))

	def test_the_screen_shows_the_library_its_supplies_and_what_it_holds(self):
		frappe.set_user(ACCOUNT)
		shown = desk.get_desk()
		self.assertEqual((shown["library"], shown["store"]), (LIBRARY, STORE))
		codes = {i["item_code"] for i in shown["items"]}
		self.assertIn(INK, codes)
		self.assertIn("A4-PAPER", codes)
		self.assertNotIn("PRINT-SVC", codes)  # services are not supplies

	def test_the_library_enters_what_it_holds_then_takes_off_what_finishes(self):
		frappe.set_user(ACCOUNT)
		desk.count({INK: 5})
		self.assertEqual(self.held(), 5)
		self.assertEqual(frappe.db.get_value("Stock Count", {"store": STORE, "docstatus": 1}, "count_type", order_by="creation desc"), "Periodic (Consumables)")
		done = desk.used_up(INK, 2)
		self.assertEqual(done["qty"], 3)
		self.assertEqual(self.held(), 3)
		# The finished bottles are posted by the system in the library's name, on its cost center.
		entry = frappe.get_doc("Stock Entry", done["entry"])
		self.assertEqual((entry.stock_entry_type, entry.items[0].s_warehouse, entry.items[0].cost_center, entry.docstatus), ("Material Issue", STORE, LIBRARY, 1))
		# Never more than the store holds; never a non-supply.
		self.assertRaises(frappe.ValidationError, desk.used_up, INK, 10)
		self.assertRaises(frappe.ValidationError, desk.used_up, "PRINT-SVC", 1)
		self.assertRaises(frappe.ValidationError, desk.count, {INK: -1})

	def test_mawasah_asks_for_ink_as_a_purchase_request(self):
		frappe.set_user(ACCOUNT)
		asked = desk.ask_for(INK, 4, "خلص الأسود")
		doc = frappe.get_doc("Material Request", asked["request"])
		self.assertEqual((doc.material_request_type, doc.docstatus, doc.items[0].qty, doc.items[0].warehouse), ("Purchase", 1, 4, STORE))
		self.assertIn(asked["request"], [r["name"] for r in desk.get_desk()["requests"]])

	def test_the_account_sees_no_money_and_no_other_library(self):
		frappe.set_user(ACCOUNT)
		for doctype in ("Sales Invoice", "GL Entry", "Payment Entry", "Expense", "Treasury Close", "Journal Entry", "Stock Entry", "Account"):
			self.assertFalse(frappe.has_permission(doctype, "read"), doctype)
		# Its own library and store only.
		self.assertEqual(frappe.get_list("Cost Center", filters={"name": "مكتبة الأزاريطة - MMG"}, pluck="name"), [])
		self.assertEqual(frappe.get_list("Warehouse", filters={"name": "خامات الأزاريطة - MMG"}, pluck="name"), [])
		self.assertEqual(frappe.get_list("Cost Center", filters={"name": LIBRARY}, pluck="name"), [LIBRARY])

	def test_only_the_library_s_account_uses_the_screen(self):
		frappe.set_user("hr@imed.local")
		self.assertRaises(frappe.PermissionError, desk.get_desk)
		self.assertRaises(frappe.PermissionError, desk.used_up, INK, 1)

	def test_paper_is_counted_and_taken_off_in_boxes(self):
		""""A box finished" takes off a box (2,500 sheets), not a sheet."""
		frappe.set_user(ACCOUNT)
		paper = next(i for i in desk.get_desk()["items"] if i["item_code"] == "A4-PAPER")
		box, factor = desk.screen_unit("A4-PAPER")  # the site's own name for the 2,500-sheet unit
		self.assertEqual((paper["unit"], factor), (box, 2500))
		desk.count({"A4-PAPER": 3})
		self.assertEqual(self.held("A4-PAPER"), 7500)
		self.assertEqual(desk.used_up("A4-PAPER", 1)["qty"], 2)
		self.assertEqual(self.held("A4-PAPER"), 5000)
		asked = frappe.get_doc("Material Request", desk.ask_for("A4-PAPER", 2)["request"])
		self.assertEqual((asked.items[0].uom, asked.items[0].stock_qty), (box, 5000))

	def test_an_item_with_no_price_is_refused_clearly_on_its_first_count(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Item", INK, "valuation_rate", 0)
		frappe.clear_document_cache("Item", INK)
		frappe.set_user(ACCOUNT)
		self.assertRaisesRegex(frappe.ValidationError, "no price", desk.count, {INK: 2})

