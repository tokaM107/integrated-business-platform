# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The opening count sheet is checked row by row before it becomes the opening balance, which is only ever made as a
# draft (imederp/opening_stock.py). Real items and stores; the sheets are test files. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_opening_stock

import csv
import os
import tempfile

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.opening_stock import COLUMNS, check_rows, make_drafts, read_sheet

# A test module outside a doctype folder builds no "_Test ..." records; keep it here, not under a doctype.
COMPANY = "Mohamed Mamdouh group"
PAPER = "A4-PAPER"
MAWASAH_RAW = "خامات المواساة - MMG"
AZARITA_RAW = "خامات الأزاريطة - MMG"
DAMAGED = "التالف — المواساة - MMG"
DATE = "2026-10-15"


class IntegrationTestOpeningStock(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("opening_test")

	def tearDown(self):
		frappe.db.rollback(save_point="opening_test")

	def sheet(self, rows):
		"""Rows written to a CSV the way the libraries fill the template, then read back."""
		handle, path = tempfile.mkstemp(suffix=".csv")
		with os.fdopen(handle, "w", encoding="utf-8", newline="") as f:
			writer = csv.DictWriter(f, fieldnames=COLUMNS)
			writer.writeheader()
			for row in rows:
				writer.writerow({column: row.get(column, "") for column in COLUMNS})
		try:
			return check_rows(read_sheet(path), COMPANY, DATE)
		finally:
			os.remove(path)

	def row(self, **values):
		return {"warehouse": MAWASAH_RAW, "item_code": PAPER, "count_uom": "كرتونة", "counted_qty": "2", "valuation_rate": "650", **values}

	def test_a_good_row_is_converted_to_the_stock_unit(self):
		[row] = self.sheet([self.row()])
		self.assertEqual(row.errors, [])
		# 2 boxes of 2,500 sheets at 650 a box: 5,000 sheets at 0.26, 1,300 in all.
		self.assertEqual((row.stock_qty, round(row.stock_rate, 4), row.value), (5000, 0.26, 1300))

	def test_the_store_may_be_named_without_the_company_abbreviation(self):
		[row] = self.sheet([self.row(warehouse="خامات المواساة")])
		self.assertEqual((row.errors, row.warehouse), ([], MAWASAH_RAW))

	def test_bad_rows_are_refused_with_the_reason(self):
		cases = {
			"not found": self.row(item_code="NO-SUCH-ITEM"),
			"Store": self.row(warehouse="المخزن المركزي بالمواساة - MMG"),  # a group
			"negative": self.row(counted_qty="-3"),
			"not a number": self.row(counted_qty="ten"),
			"whole": self.row(counted_qty="1.5"),
			"never guessed": self.row(valuation_rate=""),
			"not a unit": self.row(count_uom="Kg"),
			"is empty": self.row(warehouse=""),
		}
		rows = self.sheet(list(cases.values()))
		for (expected, _row), checked in zip(cases.items(), rows):
			self.assertTrue(any(expected in error for error in checked.errors), (expected, checked.errors))

	def test_a_count_of_nothing_needs_no_cost(self):
		[row] = self.sheet([self.row(counted_qty="0", valuation_rate="")])
		self.assertEqual((row.errors, row.stock_qty, row.value), ([], 0, 0))

	def test_arabic_digits_and_thousands_separators(self):
		[row] = self.sheet([self.row(counted_qty="٢", valuation_rate="٦٥٠٫٥"), ])
		self.assertEqual((row.errors, row.stock_qty, row.value), ([], 5000, 1301))
		# Counted in the paper's own stock unit, whatever it is on this site (ورقة since setup_core.py; QA-37).
		sheet_unit = frappe.db.get_value("Item", PAPER, "stock_uom")
		[row] = self.sheet([self.row(count_uom=sheet_unit, counted_qty="1,250", valuation_rate="0.26")])
		self.assertEqual((row.errors, row.stock_qty), ([], 1250))

	def test_the_same_item_and_store_twice_is_refused(self):
		rows = self.sheet([self.row(), self.row(counted_qty="1")])
		self.assertEqual(rows[0].errors, [])
		self.assertIn("line 2", rows[1].errors[0])

	def test_the_damaged_store_is_counted_at_zero_value(self):
		[with_cost, without] = self.sheet(
			[self.row(warehouse=DAMAGED, valuation_rate="650"), self.row(warehouse=DAMAGED, item_code="BOOK", count_uom="Nos", valuation_rate="")]
		)
		self.assertTrue(any("zero value" in e for e in with_cost.errors))
		self.assertEqual((without.errors, without.value), ([], 0))

	def test_stock_already_recorded_is_shown_with_the_difference(self):
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": COMPANY,
				"posting_date": "2026-10-01",
				"set_posting_time": 1,
				"items": [{"item_code": PAPER, "qty": 1000, "basic_rate": 0.3, "t_warehouse": AZARITA_RAW}],
			}
		).insert()
		entry.submit()
		[row] = self.sheet([self.row(warehouse=AZARITA_RAW)])
		self.assertEqual(row.errors, [])
		self.assertGreaterEqual(row.recorded_qty, 1000)
		self.assertTrue(any("already recorded" in w for w in row.warnings))

	def test_drafts_one_per_branch_never_submitted_never_twice(self):
		rows = self.sheet([self.row(), self.row(warehouse=AZARITA_RAW, counted_qty="1")])
		made = make_drafts(rows, COMPANY, DATE)
		self.assertEqual(len(made), 2)
		for name in made:
			doc = frappe.get_doc("Stock Reconciliation", name)
			self.assertEqual((doc.docstatus, doc.purpose, doc.custom_count_type), (0, "Opening Stock", "Opening"))
			self.assertEqual(frappe.db.get_value("Account", doc.expense_account, "account_type"), "Temporary")
		self.assertEqual(
			{frappe.db.get_value("Stock Reconciliation", n, "cost_center") for n in made},
			{"مكتبة المواساة - MMG", "مكتبة الأزاريطة - MMG"},
		)
		self.assertFalse(frappe.db.exists("Stock Ledger Entry", {"voucher_no": ["in", made]}))
		# The same sheet again: both stores already have an opening balance.
		again = self.sheet([self.row(), self.row(warehouse=AZARITA_RAW, counted_qty="1")])
		self.assertTrue(all(any("already has an opening balance" in e for e in r.errors) for r in again))
		self.assertRaises(frappe.ValidationError, make_drafts, again, COMPANY, DATE)
