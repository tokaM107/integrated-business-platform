# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Paper units and cost: paper is bought by the box and stocked in sheets (1 ream = 500, 1 box = 2,500),
# valued at moving average (setup_core.py). Buys through real Purchase Receipts on the real A4 paper item,
# in Mawasah's raw materials store; everything made here is rolled back afterwards.
#
# The receipts never set a conversion factor: ERPNext must take it from the item, as it does on the screen.
# A factor of 1 would bring a box in as a single sheet.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_paper_stock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

# A test module outside a doctype folder builds no "_Test ..." records, so it needs (and may have) no
# IGNORE_TEST_RECORD_DEPENDENCIES; keep it here, not under a doctype.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
PAPER = "A4-PAPER"
STORE = f"خامات المواساة - {ABBR}"
SHEET, REAM, BOX = "ورقة", "رزمة", "كرتونة"


class IntegrationTestPaperStock(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.supplier = (
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": "_Test Paper Supplier",
					"supplier_group": frappe.get_all("Supplier Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				}
			)
			.insert()
			.name
		)

	def stock(self):
		"""Sheets in the store and their total value, before or after a receipt."""
		row = frappe.db.get_value(
			"Bin", {"item_code": PAPER, "warehouse": STORE}, ["actual_qty", "stock_value"], as_dict=True
		)
		return (flt(row.actual_qty), flt(row.stock_value)) if row else (0.0, 0.0)

	def receive(self, *rows):
		"""Submit a purchase receipt; each row is (qty, rate per unit, uom or None for the item's default)."""
		receipt = frappe.get_doc(
			{
				"doctype": "Purchase Receipt",
				"company": COMPANY,
				"supplier": self.supplier,
				"posting_date": today(),
				"set_warehouse": STORE,
				"items": [
					{"item_code": PAPER, "qty": qty, "rate": rate, **({"uom": uom} if uom else {})}
					for qty, rate, uom in rows
				],
			}
		).insert()
		receipt.submit()
		return receipt

	def assert_stock(self, before, sheets, value):
		qty, total = self.stock()
		self.assertEqual(qty - before[0], sheets)
		self.assertAlmostEqual(total - before[1], value, places=2)
		# Moving average: every sheet in the store costs the same, the store's value over its sheets.
		self.assertAlmostEqual(
			flt(frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": STORE}, "valuation_rate")),
			total / qty,
			places=4,
		)

	def test_item_keeps_its_conversion_factors(self):
		item = frappe.get_doc("Item", PAPER)
		self.assertEqual(item.stock_uom, SHEET)
		self.assertEqual({d.uom: d.conversion_factor for d in item.uoms}, {SHEET: 1, REAM: 500, BOX: 2500})
		self.assertEqual(item.valuation_method, "Moving Average")
		self.assertEqual(item.purchase_uom, BOX)

	def test_two_boxes_are_5000_sheets_at_the_box_price(self):
		# The task's acceptance test: two boxes at 650 each.
		before = self.stock()
		receipt = self.receive((2, 650, BOX))

		row = receipt.items[0]
		self.assertEqual(row.conversion_factor, 2500)
		self.assertEqual(row.stock_uom, SHEET)
		self.assertEqual(row.stock_qty, 5000)
		self.assertAlmostEqual(flt(row.valuation_rate), 0.26, places=4)
		self.assertAlmostEqual(flt(row.valuation_rate) * row.stock_qty, 1300, places=2)
		self.assert_stock(before, 5000, 1300)

	def test_bought_by_the_box_when_no_unit_is_chosen(self):
		# A quantity typed without a unit is boxes, not sheets.
		before = self.stock()
		row = self.receive((2, 650, None)).items[0]

		self.assertEqual(row.uom, BOX)
		self.assertEqual(row.stock_qty, 5000)
		self.assert_stock(before, 5000, 1300)

	def test_a_ream_is_500_sheets(self):
		before = self.stock()
		row = self.receive((1, 130, REAM)).items[0]

		self.assertEqual(row.conversion_factor, 500)
		self.assertAlmostEqual(flt(row.valuation_rate), 0.26, places=4)
		self.assert_stock(before, 500, 130)

	def test_boxes_at_two_prices_average_out(self):
		# A box at 650 then one at 700: with nothing else in the store, every sheet costs 0.27.
		before = self.stock()
		self.receive((1, 650, BOX))
		self.receive((1, 700, BOX))

		self.assert_stock(before, 5000, 1350)
		if before == (0.0, 0.0):
			rate = frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": STORE}, "valuation_rate")
			self.assertAlmostEqual(flt(rate), 0.27, places=4)

	def test_edition_paper_is_the_average_plus_waste(self):
		# An edition printed in Mawasah costs its paper at the store's moving average plus the waste rate.
		from imed_erp.imederp.doctype.book_edition.book_edition import get_paper_cost
		from imed_erp.imederp.doctype.printing_cost_settings.printing_cost_settings import get_rates

		self.receive((1, 650, BOX))
		rate = flt(frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": STORE}, "valuation_rate"))
		waste = get_rates().waste_per_sheet
		self.assertAlmostEqual(get_paper_cost(f"مكتبة المواساة - {ABBR}"), rate + waste, places=4)

	def test_reams_and_boxes_are_whole_numbers(self):
		for uom in (REAM, BOX):
			with self.subTest(uom):
				self.assertTrue(frappe.db.get_value("UOM", uom, "must_be_whole_number"))

	def test_reorder_of_2000_sheets_asks_for_one_box(self):
		# ERPNext's daily reorder turns the sheets short into the purchase unit; a box is not split, so
		# 2,000 sheets (0.8 of a box) become one box.
		from erpnext.stock.reorder_item import create_material_request

		item = frappe.get_cached_doc("Item", PAPER)
		frappe.local.reorder_email_notify = 0
		try:
			requests = create_material_request(
				{
					"Purchase": {
						COMPANY: [
							{
								"item_code": PAPER,
								"warehouse": STORE,
								"reorder_qty": 2000,
								"original_reorder_qty": 2000,
								"reorder_level": 2000,
								"projected_on_hand": 0,
								"item_details": frappe._dict(
									name=PAPER,
									item_name=item.item_name,
									item_group=item.item_group,
									description=item.description,
									stock_uom=item.stock_uom,
									purchase_uom=item.purchase_uom,
								),
							}
						]
					}
				}
			)
		finally:
			del frappe.local.reorder_email_notify

		self.assertEqual(len(requests), 1)
		row = requests[0].items[0]
		self.assertEqual((row.uom, row.qty, row.stock_qty), (BOX, 1, 2500))
