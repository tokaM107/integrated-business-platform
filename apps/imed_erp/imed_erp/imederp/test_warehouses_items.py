# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Warehouses and items (LIB-02, LIB-04, LIB-06, LIB-08): the warehouse tree, the five item groups, the
# product fields, reorder levels per item and warehouse, the store keepers' warehouse permissions and
# the Mawasah -> Azarita stock transfer.
# Uses the real warehouses, groups and users made by setup/setup_core.py, setup_library.py and
# setup_users.py; everything the tests create is rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_warehouses_items
#
# Units of measure, conversion factors and valuation are not tested here: every quantity is in the
# item's stock UOM.

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from imed_erp.imederp.stock_reorder import get_reorder_alerts

COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"


def wh(name):
	return f"{name} - {ABBR}"


ROOT = wh("كل المخازن")
MAWASAH = wh("المخزن المركزي بالمواساة")
MAWASAH_STORE = wh("خامات المواساة")
MAWASAH_EDITIONS = wh("إصدارات الأطباء — المواساة")
DAMAGED = wh("التالف — المواساة")
AZARITA = wh("مخزن الأزاريطة")
AZARITA_STORE = wh("خامات الأزاريطة")
AZARITA_EDITIONS = wh("إصدارات الأطباء — الأزاريطة")
CENTER = wh("مخزن سنتر Imed — أدوات مكتبية")

RAGHAD = "raghad@imed.local"
SARA = "sara@imed.local"

INVENTORY_GROUPS = ["ورق", "أحبار", "كتب وكشاكيل", "مستهلكات", "خامات تجليد"]


def make_item(code, group="ورق", **extra):
	return frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": group,
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"include_item_in_manufacturing": 0,
			"item_defaults": [{"company": COMPANY, "default_warehouse": MAWASAH_STORE}],
			**extra,
		}
	).insert()


def stock_entry(purpose, rows, submit=True):
	doc = frappe.get_doc(
		{"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": purpose, "purpose": purpose, "items": rows}
	)
	doc.insert()
	if submit:
		doc.submit()
	return doc


def qty(item_code, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


class IntegrationTestWarehousesItems(IntegrationTestCase):
	# Each test is undone on its own: the class-level rollback alone would leave one test's items in the
	# next, and a refused document would leave its half-written stock in the open transaction (a real
	# request is rolled back when it fails).
	def setUp(self):
		frappe.db.savepoint("warehouses_items_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="warehouses_items_test")

	# ---------- Warehouses ----------
	def test_warehouse_tree(self):
		expected = {
			MAWASAH: (ROOT, 1),
			MAWASAH_STORE: (MAWASAH, 0),
			MAWASAH_EDITIONS: (MAWASAH, 0),
			DAMAGED: (MAWASAH, 0),
			AZARITA: (ROOT, 1),
			AZARITA_STORE: (AZARITA, 0),
			AZARITA_EDITIONS: (AZARITA, 0),
			CENTER: (ROOT, 0),
		}
		for name, (parent, is_group) in expected.items():
			row = frappe.db.get_value("Warehouse", name, ["parent_warehouse", "is_group", "company"], as_dict=True)
			self.assertTrue(row, f"{name} missing")
			self.assertEqual((row.parent_warehouse, row.is_group, row.company), (parent, is_group, COMPANY), name)

	def test_azarita_is_not_inside_mawasah(self):
		under_mawasah = frappe.db.get_descendants("Warehouse", MAWASAH)
		self.assertIn(DAMAGED, under_mawasah)
		for name in (AZARITA, AZARITA_STORE, AZARITA_EDITIONS, CENTER):
			self.assertNotIn(name, under_mawasah)

	def test_every_leaf_has_its_own_stock_account(self):
		for name in (MAWASAH_STORE, MAWASAH_EDITIONS, DAMAGED, AZARITA_STORE, AZARITA_EDITIONS, CENTER):
			account = frappe.db.get_value("Warehouse", name, "account")
			self.assertTrue(account, f"{name} has no stock account")
			self.assertEqual(frappe.db.get_value("Account", account, "account_type"), "Stock")

	# ---------- Item groups ----------
	def test_inventory_groups_exist_once(self):
		for group in INVENTORY_GROUPS:
			self.assertEqual(frappe.db.count("Item Group", {"item_group_name": group}), 1, group)
		self.assertEqual(frappe.db.get_value("Item Group", "كتب", "parent_item_group"), "كتب وكشاكيل")
		self.assertEqual(frappe.db.get_value("Item Group", "مذكرات", "parent_item_group"), "كتب وكشاكيل")
		self.assertEqual(frappe.db.get_value("Item", "A4-PAPER", "item_group"), "ورق")

	# ---------- Item fields (LIB-06) ----------
	def test_book_stores_isbn_author_classification_and_prices(self):
		book = make_item(
			"TEST-WH-BOOK",
			group="كتب",
			custom_author="Test Author",
			valuation_rate=100,
			standard_rate=150,
			barcodes=[{"barcode": "9780306406157", "barcode_type": "ISBN"}],
		)
		book.reload()
		self.assertEqual(book.custom_author, "Test Author")
		self.assertEqual(book.item_group, "كتب")
		self.assertEqual(flt(book.valuation_rate), 100)
		self.assertEqual((book.barcodes[0].barcode, book.barcodes[0].barcode_type), ("9780306406157", "ISBN"))
		self.assertEqual(frappe.db.get_value("Item Barcode", {"barcode": "9780306406157"}, "parent"), book.name)
		price = frappe.db.get_value("Item Price", {"item_code": book.name, "selling": 1}, "price_list_rate")
		self.assertEqual(flt(price), 150)

	def test_isbn_and_author_are_optional(self):
		paper = make_item("TEST-WH-PAPER", valuation_rate=1)
		self.assertFalse(paper.custom_author)
		self.assertFalse(paper.barcodes)
		meta = frappe.get_meta("Item")
		self.assertFalse(meta.get_field("custom_author").reqd)
		self.assertFalse(meta.get_field("barcodes").reqd)

	def test_wrong_isbn_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_item("TEST-WH-BADISBN", group="كتب", barcodes=[{"barcode": "9780306406158", "barcode_type": "ISBN"}])

	# ---------- Reorder levels (LIB-04) ----------
	def paper_with_levels(self, code="TEST-WH-A4"):
		return make_item(
			code,
			reorder_levels=[
				{"warehouse": MAWASAH_STORE, "warehouse_reorder_level": 1000, "warehouse_reorder_qty": 2000, "material_request_type": "Purchase"},
				{"warehouse": AZARITA_STORE, "warehouse_reorder_level": 500, "warehouse_reorder_qty": 500, "material_request_type": "Transfer"},
			],
		)

	def test_reorder_level_per_warehouse(self):
		item = self.paper_with_levels()
		levels = {
			r.warehouse: flt(r.warehouse_reorder_level)
			for r in frappe.get_all("Item Reorder", filters={"parent": item.name}, fields=["warehouse", "warehouse_reorder_level"])
		}
		self.assertEqual(levels, {MAWASAH_STORE: 1000, AZARITA_STORE: 500})

		# Changing one warehouse's level leaves the other's alone.
		item.reorder_levels[1].warehouse_reorder_level = 600
		item.save()
		self.assertEqual(
			flt(frappe.db.get_value("Item Reorder", {"parent": item.name, "warehouse": MAWASAH_STORE}, "warehouse_reorder_level")), 1000
		)
		self.assertEqual(
			flt(frappe.db.get_value("Item Reorder", {"parent": item.name, "warehouse": AZARITA_STORE}, "warehouse_reorder_level")), 600
		)

	def test_one_level_per_warehouse_and_no_group(self):
		item = self.paper_with_levels()
		item.append(
			"reorder_levels",
			{"warehouse": AZARITA_STORE, "warehouse_reorder_level": 10, "warehouse_reorder_qty": 10, "material_request_type": "Purchase"},
		)
		self.assertRaises(frappe.ValidationError, item.save)
		item.reload()
		item.append(
			"reorder_levels",
			{"warehouse": AZARITA, "warehouse_reorder_level": 10, "warehouse_reorder_qty": 10, "material_request_type": "Purchase"},
		)
		self.assertRaises(frappe.ValidationError, item.save)

	def test_alert_uses_each_warehouse_own_stock(self):
		item = self.paper_with_levels()
		stock_entry(
			"Material Receipt",
			[
				{"item_code": item.name, "qty": 1500, "t_warehouse": MAWASAH_STORE, "basic_rate": 1},
				{"item_code": item.name, "qty": 600, "t_warehouse": AZARITA_STORE, "basic_rate": 1},
			],
		)
		self.assertEqual(get_reorder_alerts(), [])

		# Azarita drops to 450 (below its 500) while the total, 1,950, is far above both levels.
		before = frappe.db.count("Notification Log", {"for_user": SARA})
		stock_entry("Material Issue", [{"item_code": item.name, "qty": 150, "s_warehouse": AZARITA_STORE}])
		alerts = [(a.warehouse, a.actual_qty, a.reorder_level) for a in get_reorder_alerts() if a.item_code == item.name]
		self.assertEqual(alerts, [(AZARITA_STORE, 450, 500)])

		# The alert went to Sara (Azarita) and Raghad (who supplies it), once.
		self.assertEqual(frappe.db.count("Notification Log", {"for_user": SARA}), before + 1)
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": RAGHAD, "subject": ["like", f"%{item.name}%"]}))
		stock_entry("Material Issue", [{"item_code": item.name, "qty": 10, "s_warehouse": AZARITA_STORE}])
		self.assertEqual(frappe.db.count("Notification Log", {"for_user": SARA}), before + 1)

		# Mawasah reaching exactly its level counts too; Sara is not told about Mawasah.
		stock_entry("Material Issue", [{"item_code": item.name, "qty": 500, "s_warehouse": MAWASAH_STORE}])
		self.assertIn((MAWASAH_STORE, 1000, 1000), [(a.warehouse, a.actual_qty, a.reorder_level) for a in get_reorder_alerts()])
		self.assertFalse(frappe.db.exists("Notification Log", {"for_user": SARA, "subject": ["like", f"%{MAWASAH_STORE}%"]}))
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": RAGHAD, "subject": ["like", f"%{MAWASAH_STORE}%"]}))

		# Sara's report lists Azarita only, and she cannot ask for Mawasah.
		frappe.set_user(SARA)
		self.assertEqual({a.warehouse for a in get_reorder_alerts()}, {AZARITA_STORE})
		self.assertRaises(frappe.PermissionError, get_reorder_alerts, MAWASAH)

	# ---------- Permissions ----------
	def test_raghad_and_sara_warehouses(self):
		for warehouse in (MAWASAH, MAWASAH_STORE, DAMAGED, AZARITA_STORE):
			self.assertTrue(frappe.has_permission("Warehouse", "read", doc=warehouse, user=RAGHAD), warehouse)
		for warehouse in (AZARITA, AZARITA_STORE, AZARITA_EDITIONS):
			self.assertTrue(frappe.has_permission("Warehouse", "read", doc=warehouse, user=SARA), warehouse)
		for warehouse in (MAWASAH, MAWASAH_STORE, MAWASAH_EDITIONS, DAMAGED, CENTER):
			self.assertFalse(frappe.has_permission("Warehouse", "read", doc=warehouse, user=SARA), warehouse)

	def test_sara_cannot_touch_mawasah_through_the_api(self):
		item = make_item("TEST-WH-PERM")
		stock_entry("Material Receipt", [{"item_code": item.name, "qty": 100, "t_warehouse": MAWASAH_STORE, "basic_rate": 1}])
		frappe.set_user(SARA)
		# Read Mawasah's stock.
		self.assertRaises(frappe.PermissionError, frappe.client.get, "Warehouse", MAWASAH_STORE)
		bins = frappe.get_list("Bin", filters={"item_code": item.name}, pluck="warehouse")
		self.assertNotIn(MAWASAH_STORE, bins)
		# Take stock out of Mawasah, or move it from Mawasah to Azarita herself.
		for rows in (
			[{"item_code": item.name, "qty": 1, "s_warehouse": MAWASAH_STORE}],
			[{"item_code": item.name, "qty": 1, "s_warehouse": MAWASAH_STORE, "t_warehouse": AZARITA_STORE}],
		):
			purpose = "Material Transfer" if "t_warehouse" in rows[0] else "Material Issue"
			with self.assertRaises(frappe.PermissionError):
				frappe.client.insert(
					{"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": purpose, "purpose": purpose, "items": rows}
				)
		self.assertEqual(qty(item.name, MAWASAH_STORE), 100)

	# ---------- Transfer Mawasah -> Azarita (LIB-08) ----------
	def test_transfer_moves_stock_without_creating_any(self):
		item = make_item("TEST-WH-MOVE")
		stock_entry(
			"Material Receipt",
			[
				{"item_code": item.name, "qty": 1000, "t_warehouse": MAWASAH_STORE, "basic_rate": 1},
				{"item_code": item.name, "qty": 200, "t_warehouse": AZARITA_STORE, "basic_rate": 1},
			],
		)

		# Raghad sends 100 to Azarita.
		frappe.set_user(RAGHAD)
		transfer = stock_entry(
			"Material Transfer", [{"item_code": item.name, "qty": 100, "s_warehouse": MAWASAH_STORE, "t_warehouse": AZARITA_STORE}]
		)
		frappe.set_user("Administrator")

		self.assertEqual(qty(item.name, MAWASAH_STORE), 900)
		self.assertEqual(qty(item.name, AZARITA_STORE), 300)
		self.assertEqual(qty(item.name, MAWASAH_STORE) + qty(item.name, AZARITA_STORE), 1200)

		# Traceable: one ledger line out of Mawasah and one into Azarita, both on the transfer.
		moves = frappe.get_all(
			"Stock Ledger Entry",
			filters={"voucher_no": transfer.name, "is_cancelled": 0},
			fields=["warehouse", "actual_qty"],
		)
		self.assertEqual(sorted((m.warehouse, m.actual_qty) for m in moves), sorted([(MAWASAH_STORE, -100), (AZARITA_STORE, 100)]))
		self.assertEqual(transfer.purpose, "Material Transfer")
		self.assertEqual(transfer.owner, RAGHAD)
		# Not a purchase: no supplier document, and the stock value only moves between the two stock accounts.
		gl = frappe.get_all("GL Entry", filters={"voucher_no": transfer.name, "is_cancelled": 0}, fields=["account", "debit", "credit"])
		self.assertEqual(sum(g.debit - g.credit for g in gl), 0)
		self.assertTrue(all(frappe.db.get_value("Account", g.account, "account_type") == "Stock" for g in gl))

	def test_cannot_transfer_more_than_available(self):
		item = make_item("TEST-WH-SHORT")
		stock_entry("Material Receipt", [{"item_code": item.name, "qty": 50, "t_warehouse": MAWASAH_STORE, "basic_rate": 1}])
		frappe.db.savepoint("before_transfer")
		with self.assertRaises(frappe.ValidationError):
			stock_entry(
				"Material Transfer", [{"item_code": item.name, "qty": 51, "s_warehouse": MAWASAH_STORE, "t_warehouse": AZARITA_STORE}]
			)
		# What the request does when the transfer is refused.
		frappe.db.rollback(save_point="before_transfer")
		self.assertEqual(qty(item.name, MAWASAH_STORE), 50)
		self.assertEqual(qty(item.name, AZARITA_STORE), 0)
