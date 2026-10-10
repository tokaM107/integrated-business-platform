# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Buying paper and materials (LIB-07, ACC-12), set up by setup/setup_buying.py: the library buys directly,
# with one purchase invoice that updates stock. Real A4 paper item, real store (Mawasah's raw materials);
# everything made here is rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_buying

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

# A test module outside a doctype folder builds no "_Test ..." records, so it needs (and may have) no
# IGNORE_TEST_RECORD_DEPENDENCIES; keep it here, not under a doctype.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
PAPER = "A4-PAPER"
STORE = f"خامات المواساة - {ABBR}"
BOX = "كرتونة"
SHIPPING = f"مصروفات الشحن والنقل - {ABBR}"


class IntegrationTestBuying(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.supplier = (
			frappe.get_doc(
				{"doctype": "Supplier", "supplier_name": "_Test Paper Supplier", "supplier_group": "موردي الورق والخامات"}
			)
			.insert()
			.name
		)

	def stock(self):
		"""Sheets in the store and their total value."""
		row = frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": STORE}, ["actual_qty", "stock_value"])
		return tuple(flt(v) for v in row) if row else (0.0, 0.0)

	def buy(self, boxes, rate, **values):
		invoice = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": COMPANY,
				"supplier": self.supplier,
				"posting_date": today(),
				"set_warehouse": STORE,
				"items": [{"item_code": PAPER, "qty": boxes, "uom": BOX, "rate": rate, "warehouse": STORE}],
				**values,
			}
		).insert()
		invoice.submit()
		return invoice

	def test_a_new_purchase_invoice_updates_stock(self):
		self.assertEqual(frappe.new_doc("Purchase Invoice").update_stock, 1)

		before = self.stock()
		self.buy(2, 650)
		self.assertEqual(self.stock(), (before[0] + 5000, before[1] + 1300))

	def test_shipping_is_added_to_the_cost_of_the_paper(self):
		# Two boxes at 650 (0.26 a sheet) and 100 for shipping: 1,400 for 5,000 sheets, 0.28 a sheet once
		# the shipping is added with a Landed Cost Voucher.
		before = self.stock()
		invoice = self.buy(2, 650)
		voucher = frappe.get_doc(
			{
				"doctype": "Landed Cost Voucher",
				"company": COMPANY,
				"posting_date": today(),
				"distribute_charges_based_on": "Amount",
				"purchase_receipts": [
					{
						"receipt_document_type": "Purchase Invoice",
						"receipt_document": invoice.name,
						"supplier": self.supplier,
						"grand_total": invoice.grand_total,
					}
				],
				"taxes": [{"description": "شحن الورق", "amount": 100, "expense_account": SHIPPING}],
			}
		)
		voucher.get_items_from_purchase_receipts()
		voucher.insert()
		voucher.submit()

		self.assertEqual(self.stock(), (before[0] + 5000, before[1] + 1400))
		if before == (0.0, 0.0):
			rate = frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": STORE}, "valuation_rate")
			self.assertAlmostEqual(flt(rate), 0.28, places=4)
