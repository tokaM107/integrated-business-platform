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
MAWASAH = f"مكتبة المواساة - {ABBR}"
AZARITA_STORE = f"خامات الأزاريطة - {ABBR}"
AZARITA = f"مكتبة الأزاريطة - {ABBR}"
STOCK_DIFFERENCES = f"فروقات الجرد - {ABBR}"
ACCOUNTANT = "accountant@imed.local"
RAGHAD = "raghad@imed.local"
# Sara runs Azarita's library, Raghad Mawasah's (User Permissions on their branch's cost center and stores).
SARA = "sara@imed.local"
BOOK = "BOOK"


class IntegrationTestStockCount(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def on_hand(self, store=STORE):
		"""Sheets in the store and the price of one."""
		row = frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": store}, ["actual_qty", "valuation_rate"])
		return tuple(flt(v) for v in row) if row else (0.0, 0.0)

	def receive(self, item_code, qty, rate, store=STORE):
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": COMPANY,
				"items": [{"item_code": item_code, "qty": qty, "basic_rate": rate, "t_warehouse": store}],
			}
		).insert()
		entry.submit()

	def stock_count(self, rows, store=STORE, user=RAGHAD):
		"""A Stock Count by `user` of `store`: rows of (item, counted); saved, not submitted."""
		current = frappe.session.user
		frappe.set_user(user)
		try:
			return frappe.get_doc(
				{
					"doctype": "Stock Count",
					"store": store,
					"items": [{"item_code": item, "counted_qty": counted} for item, counted in rows],
				}
			).insert()
		finally:
			frappe.set_user(current)

	def receive_two_boxes(self, store=STORE):
		# 2 boxes at 650: 5,000 sheets at 0.26 when the store was empty.
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": COMPANY,
				"items": [{"item_code": PAPER, "qty": 2, "uom": "كرتونة", "basic_rate": 650, "t_warehouse": store}],
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

	def test_the_company_posts_differences_to_stock_differences(self):
		self.assertEqual(
			frappe.get_cached_value("Company", COMPANY, "stock_adjustment_account"), STOCK_DIFFERENCES
		)

	def test_shortage_of_100_sheets_is_26_on_stock_differences(self):
		# 5,000 sheets recorded, 4,900 counted: a shortage of 100 sheets, 26 at 0.26 a sheet, posted to the
		# stock differences account on Mawasah's library, whose store was counted.
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

		self.assertEqual((count.expense_account, count.cost_center), (STOCK_DIFFERENCES, MAWASAH))
		posted = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": count.name, "is_cancelled": 0},
			fields=["account", "cost_center", "debit", "credit"],
		)
		loss = [g for g in posted if g.account == STOCK_DIFFERENCES]
		self.assertAlmostEqual(sum(flt(g.debit) - flt(g.credit) for g in loss), 100 * rate, places=2)
		self.assertEqual({g.cost_center for g in posted}, {MAWASAH})

	def test_each_branchs_difference_is_its_own(self):
		self.receive_two_boxes(AZARITA_STORE)
		count = self.count(self.on_hand(AZARITA_STORE)[0] - 10)
		count.items[0].warehouse = AZARITA_STORE
		count.insert()
		self.assertEqual(count.cost_center, AZARITA)

		# A cost center typed by hand is put right: the store decides.
		count.cost_center = MAWASAH
		count.save()
		self.assertEqual(count.cost_center, AZARITA)

	def test_one_count_one_branch(self):
		self.receive_two_boxes()
		self.receive_two_boxes(AZARITA_STORE)
		count = self.count(self.on_hand()[0] - 1)
		count.append("items", {"item_code": PAPER, "warehouse": AZARITA_STORE, "qty": self.on_hand(AZARITA_STORE)[0] - 1})
		self.assertRaisesRegex(frappe.ValidationError, "one branch", count.insert)

	def test_stock_reconciliation_keeps_all_its_hooks(self):
		# hooks.py lists each doctype once; a second "Stock Reconciliation" entry would silently replace these.
		events = frappe.get_hooks("doc_events", app_name="imed_erp")["Stock Reconciliation"]
		self.assertIn("imed_erp.imederp.stock_count.check_count_type", events["validate"])
		self.assertIn("imed_erp.imederp.stock_count.set_branch_cost_center", events["validate"])
		self.assertIn("imed_erp.imederp.stock_reorder.alert_on_reorder_level", events["on_submit"])
		self.assertIn("imed_erp.imederp.no_delete.block_delete_of_posted", events["on_trash"])

	def test_a_count_with_no_difference_is_kept(self):
		# The library counted and everything matched: the count is on record, and nothing is posted.
		self.receive_two_boxes()
		count = self.stock_count([(PAPER, self.on_hand()[0])])
		frappe.set_user(RAGHAD)
		count.submit()
		self.assertEqual((count.docstatus, count.counted_by, count.branch), (1, RAGHAD, MAWASAH))
		self.assertEqual((count.items_with_difference, count.total_difference_value), (0, 0))
		self.assertFalse(count.stock_reconciliation)

	def test_every_item_counted_stays_on_the_count(self):
		# Paper is 100 sheets short, the books match. The count keeps both; ERPNext's reconciliation, made on
		# submit, has only the paper and posts the 26 to stock differences on Mawasah's library.
		self.receive_two_boxes()
		self.receive(BOOK, 10, 50)
		sheets, rate = self.on_hand()
		count = self.stock_count([(PAPER, sheets - 100), (BOOK, 10)])
		self.assertEqual([(r.item_code, r.difference_qty) for r in count.items], [(PAPER, -100), (BOOK, 0)])
		self.assertAlmostEqual(count.total_difference_value, -100 * rate, places=2)

		frappe.set_user(RAGHAD)
		count.submit()
		frappe.set_user("Administrator")
		self.assertEqual((count.items_counted, count.items_with_difference), (2, 1))
		reconciliation = frappe.get_doc("Stock Reconciliation", count.stock_reconciliation)
		self.assertEqual([r.item_code for r in reconciliation.items], [PAPER])
		self.assertEqual(
			(reconciliation.cost_center, reconciliation.custom_counted_by, reconciliation.custom_count_type),
			(MAWASAH, RAGHAD, DAILY),
		)
		loss = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": reconciliation.name, "account": STOCK_DIFFERENCES, "is_cancelled": 0},
			fields=["debit", "credit", "cost_center"],
		)
		self.assertAlmostEqual(sum(flt(g.debit) - flt(g.credit) for g in loss), 100 * rate, places=2)
		self.assertEqual({g.cost_center for g in loss}, {MAWASAH})
		self.assertEqual(self.on_hand()[0], sheets - 100)

	def test_a_branch_manager_counts_only_her_branch(self):
		self.receive_two_boxes(AZARITA_STORE)
		sheets = self.on_hand(AZARITA_STORE)[0]
		self.assertRaisesRegex(
			frappe.ValidationError, "not a store of your branch", self.stock_count, [(PAPER, sheets)], AZARITA_STORE, RAGHAD
		)
		count = self.stock_count([(PAPER, sheets)], AZARITA_STORE, SARA)
		self.assertEqual(count.branch, AZARITA)

	def test_a_counts_reconciliation_is_cancelled_only_with_the_count(self):
		self.receive_two_boxes()
		count = self.stock_count([(PAPER, self.on_hand()[0] - 1)])
		count.submit()
		reconciliation = frappe.get_doc("Stock Reconciliation", count.stock_reconciliation)
		self.assertRaisesRegex(frappe.ValidationError, "Cancel the count", reconciliation.cancel)

		# Branch managers count; cancelling is the accountant's.
		frappe.set_user(RAGHAD)
		self.assertRaises(frappe.PermissionError, frappe.get_doc("Stock Count", count.name).cancel)
		frappe.set_user(ACCOUNTANT)
		frappe.get_doc("Stock Count", count.name).cancel()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Stock Reconciliation", reconciliation.name, "docstatus"), 2)
