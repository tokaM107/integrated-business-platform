# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Stock counts (LIB-03, PRN-06) on ERPNext's Stock Reconciliation, with the app's count type and who counted
# (imederp/stock_count.py, fields from setup/setup_library.py). Real A4 paper item, real store (Mawasah's raw
# materials); everything made here is rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_stock_count

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp.stock_count import DAILY, OPENING, PERIODIC, check_count_type

# A test module outside a doctype folder builds no "_Test ..." records, so it needs (and may have) no
# IGNORE_TEST_RECORD_DEPENDENCIES; keep it here, not under a doctype.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
PAPER = "A4-PAPER"
STORE = f"خامات المواساة - {ABBR}"
STOCK_DIFFERENCES = f"فروقات الجرد - {ABBR}"
ACCOUNTANT = "accountant@imed.local"
RAGHAD = "raghad@imed.local"


class IntegrationTestStockCount(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def on_hand(self):
		"""Sheets in the store and the price of one."""
		row = frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": STORE}, ["actual_qty", "valuation_rate"])
		return tuple(flt(v) for v in row) if row else (0.0, 0.0)

	def receive_two_boxes(self):
		# 2 boxes at 650: 5,000 sheets at 0.26 when the store was empty.
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": COMPANY,
				"items": [{"item_code": PAPER, "qty": 2, "uom": "كرتونة", "basic_rate": 650, "t_warehouse": STORE}],
			}
		).insert()
		entry.submit()

	def count(self, sheets, **values):
		"""A count of the store's paper; not saved."""
		return frappe.get_doc(
			{
				"doctype": "Stock Reconciliation",
				"company": COMPANY,
				"posting_date": today(),
				# Filled in by the screen; ERPNext has no server default for it.
				"purpose": "Stock Reconciliation",
				"items": [{"item_code": PAPER, "warehouse": STORE, "qty": sheets}],
				**values,
			}
		)

	def test_count_type_and_counted_by_fields(self):
		meta = frappe.get_meta("Stock Reconciliation")
		self.assertEqual(meta.get_field("custom_count_type").options.split("\n"), [DAILY, PERIODIC, OPENING])
		self.assertEqual(meta.get_field("custom_counted_by").options, "User")

	def test_a_new_count_is_daily_and_counted_by_who_makes_it(self):
		frappe.set_user(ACCOUNTANT)
		new = frappe.new_doc("Stock Reconciliation")
		self.assertEqual((new.custom_count_type, new.custom_counted_by), (DAILY, ACCOUNTANT))

		# Made in code, without the screen, the field's default still fills it in. ERPNext saves only a count that
		# finds a difference, so this one is a sheet short.
		self.receive_as_administrator()
		frappe.set_user(ACCOUNTANT)
		count = self.count(self.on_hand()[0] - 1).insert()
		self.assertEqual((count.custom_count_type, count.custom_counted_by), (DAILY, ACCOUNTANT))

	def receive_as_administrator(self):
		user = frappe.session.user
		frappe.set_user("Administrator")
		self.receive_two_boxes()
		frappe.set_user(user)

	def test_who_counted_can_be_someone_else(self):
		# Raghad counts the library's paper; the accountant records it.
		self.receive_two_boxes()
		frappe.set_user(ACCOUNTANT)
		count = self.count(self.on_hand()[0] - 1, custom_counted_by=RAGHAD).insert()
		self.assertEqual(count.custom_counted_by, RAGHAD)

	def test_opening_count_is_erpnexts_opening_stock(self):
		# Opening Stock is always an opening count; an opening count under another purpose is refused, so
		# an opening balance never lands on the stock differences account.
		count = self.count(10, purpose="Opening Stock", custom_count_type=DAILY)
		check_count_type(count)
		self.assertEqual(count.custom_count_type, OPENING)

		self.receive_two_boxes()
		count = self.count(self.on_hand()[0] - 1, custom_count_type=OPENING)
		self.assertRaisesRegex(frappe.ValidationError, "opening", count.insert)
		count.custom_count_type = DAILY
		count.insert()

	def test_shortage_of_100_sheets_is_26_on_stock_differences(self):
		# 5,000 sheets recorded, 4,900 counted: a shortage of 100 sheets, 26 at 0.26 a sheet, posted to the
		# stock differences account.
		self.receive_two_boxes()
		recorded, rate = self.on_hand()
		count = self.count(recorded - 100, custom_count_type=PERIODIC).insert()
		count.submit()

		row = count.items[0]
		self.assertEqual(flt(row.quantity_difference), -100)
		self.assertAlmostEqual(flt(row.amount_difference), -100 * rate, places=2)
		if recorded == 5000:
			self.assertAlmostEqual(flt(row.amount_difference), -26, places=2)
		self.assertEqual(self.on_hand()[0], recorded - 100)

		posted = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": count.name, "account": STOCK_DIFFERENCES, "is_cancelled": 0},
			fields=["debit", "credit"],
		)
		self.assertAlmostEqual(sum(flt(g.debit) - flt(g.credit) for g in posted), 100 * rate, places=2)

	def test_stock_reconciliation_keeps_all_its_hooks(self):
		# hooks.py lists each doctype once; a second "Stock Reconciliation" entry would silently replace these.
		events = frappe.get_hooks("doc_events", app_name="imed_erp")["Stock Reconciliation"]
		self.assertIn("imed_erp.imederp.stock_count.check_count_type", events["validate"])
		self.assertIn("imed_erp.imederp.stock_reorder.alert_on_reorder_level", events["on_submit"])
		self.assertIn("imed_erp.imederp.no_delete.block_delete_of_posted", events["on_trash"])
