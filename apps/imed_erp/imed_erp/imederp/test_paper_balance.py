# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# PRN-04: the paper of each store in sheets, and in boxes and reams. Rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_paper_balance

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.report.paper_balance.paper_balance import execute, in_boxes_and_reams

COMPANY = "Mohamed Mamdouh group"
AZARITA_STORE = "خامات الأزاريطة - MMG"
MAWASAH_STORE = "خامات المواساة - MMG"


class IntegrationTestPaperBalance(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("paper_balance")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="paper_balance")

	def test_sheets_in_boxes_and_reams(self):
		# A box is 5 reams of 500 (requirements PRN-04).
		self.assertEqual(in_boxes_and_reams(11030, 2500, 500), (4, 2, 30))
		self.assertEqual(in_boxes_and_reams(2500, 2500, 500), (1, 0, 0))
		self.assertEqual(in_boxes_and_reams(499, 2500, 500), (0, 0, 499))
		self.assertEqual(in_boxes_and_reams(0, 2500, 500), (0, 0, 0))

	def test_each_store_and_a_received_box(self):
		before = {r["warehouse"]: r for r in execute()[1]}.get(AZARITA_STORE, {"sheets": 0})
		receipt = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": COMPANY,
				"items": [{"item_code": "A4-PAPER", "qty": 1, "uom": "كرتونة", "basic_rate": 650, "t_warehouse": AZARITA_STORE}],
			}
		).insert()
		receipt.submit()
		row = {r["warehouse"]: r for r in execute()[1]}[AZARITA_STORE]
		self.assertEqual(row["sheets"], before["sheets"] + 2500)
		self.assertEqual(row["boxes"] * 2500 + row["reams"] * 500 + row["loose"], row["sheets"])

	def test_sara_sees_her_own_stores(self):
		frappe.set_user("sara@imed.local")
		self.assertNotIn(MAWASAH_STORE, [r["warehouse"] for r in execute()[1]])
