# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The Stock Count Variance report (LIB-03, PRN-06) on real stores and the real A4 paper and book items; every
# count made here is rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_stock_count_variance

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp.report.stock_count_variance.stock_count_variance import execute

# A test module outside a doctype folder builds no "_Test ..." records, so it needs (and may have) no
# IGNORE_TEST_RECORD_DEPENDENCIES; keep it here, not under a doctype.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
PAPER = "A4-PAPER"
BOOK = "BOOK"
MAWASAH_STORE = f"خامات المواساة - {ABBR}"
AZARITA_STORE = f"خامات الأزاريطة - {ABBR}"
MAWASAH = f"مكتبة المواساة - {ABBR}"
AZARITA = f"مكتبة الأزاريطة - {ABBR}"
RAGHAD = "raghad@imed.local"
SARA = "sara@imed.local"


def receive(item_code, qty, rate, store):
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": COMPANY,
			"items": [{"item_code": item_code, "qty": qty, "basic_rate": rate, "t_warehouse": store}],
		}
	).insert()
	entry.submit()


def on_hand(item_code, store):
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": store}, "actual_qty"))


def count(store, rows, user, submit=True):
	"""A Stock Count by `user`: rows of (item, sheets short)."""
	frappe.set_user(user)
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Stock Count",
				"store": store,
				"items": [{"item_code": item, "counted_qty": on_hand(item, store) - short} for item, short in rows],
			}
		).insert()
		if submit:
			doc.submit()
		return doc
	finally:
		frappe.set_user("Administrator")


class IntegrationTestStockCountVariance(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Mawasah: 5,000 sheets and 10 books; Raghad counts 100 sheets short and the books right.
		# Azarita: 2,500 sheets; Sara counts them right. A draft and a cancelled count do not show.
		receive(PAPER, 5000, 0.26, MAWASAH_STORE)
		receive(BOOK, 10, 50, MAWASAH_STORE)
		receive(PAPER, 2500, 0.26, AZARITA_STORE)
		cls.rate = flt(frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": MAWASAH_STORE}, "valuation_rate"))
		cls.mawasah = count(MAWASAH_STORE, [(PAPER, 100), (BOOK, 0)], RAGHAD)
		cls.azarita = count(AZARITA_STORE, [(PAPER, 0)], SARA)
		count(MAWASAH_STORE, [(BOOK, 1)], RAGHAD, submit=False)
		cancelled = count(AZARITA_STORE, [(PAPER, 5)], SARA)
		cancelled.cancel()

	def tearDown(self):
		frappe.set_user("Administrator")

	def run_report(self, **filters):
		columns, data, _message, _chart, summary = execute({"from_date": today(), "to_date": today(), **filters})
		return data, {s["label"]: s["value"] for s in summary}

	def test_every_item_counted_shows_with_its_difference(self):
		data, summary = self.run_report()
		rows = {(row.stock_count, row.item_code): row for row in data}
		self.assertEqual(len(rows), 3)

		paper = rows[(self.mawasah.name, PAPER)]
		self.assertEqual(
			(paper.branch, paper.store, paper.counted_by, paper.difference_qty),
			(MAWASAH, MAWASAH_STORE, RAGHAD, -100),
		)
		self.assertEqual(paper.counted_qty, paper.recorded_qty - 100)
		self.assertAlmostEqual(flt(paper.difference_value), -100 * self.rate, places=2)
		self.assertEqual(rows[(self.mawasah.name, BOOK)].difference_qty, 0)
		# Sara's count found nothing, and it shows all the same.
		self.assertEqual(rows[(self.azarita.name, PAPER)].difference_qty, 0)

		self.assertEqual((summary["Counts"], summary["Items with a Difference"]), (2, 1))
		self.assertAlmostEqual(summary["Shortage Value"], -100 * self.rate, places=2)
		self.assertEqual(summary["Surplus Value"], 0)

	def test_shortage_of_100_sheets_is_26(self):
		data, _summary = self.run_report(only_differences=1)
		self.assertEqual([(row.item_code, row.difference_qty) for row in data], [(PAPER, -100)])
		if self.rate == 0.26:
			self.assertAlmostEqual(flt(data[0].difference_value), -26, places=2)

	def test_filters_by_branch_store_and_who_counted(self):
		self.assertEqual({row.branch for row in self.run_report(branch=AZARITA)[0]}, {AZARITA})
		# A group stands for every branch under it.
		libraries = frappe.db.get_value("Cost Center", MAWASAH, "parent_cost_center")
		self.assertEqual(len(self.run_report(branch=libraries)[0]), 3)
		self.assertEqual({row.store for row in self.run_report(store=MAWASAH_STORE)[0]}, {MAWASAH_STORE})
		self.assertEqual({row.counted_by for row in self.run_report(counted_by=SARA)[0]}, {SARA})
		self.assertEqual(self.run_report(from_date="2026-01-01", to_date="2026-01-31")[0], [])

	def test_a_branch_manager_sees_only_her_branch(self):
		frappe.set_user(RAGHAD)
		self.assertEqual({row.branch for row in self.run_report()[0]}, {MAWASAH})
		frappe.set_user(SARA)
		self.assertEqual({row.branch for row in self.run_report()[0]}, {AZARITA})
