# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The Daily Printing report (PRN-01, PRN-02, PRN-09): each machine's consumption, its share of the day's printing,
# of what was sold and of the shortfall in sheets and money, adding up to the library's day. Real machines (from
# setup_library.py) and real sales; rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_daily_printing

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days

from imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading import get_machines
from imed_erp.imederp.report.daily_printing.daily_printing import execute

AZARITA = "مكتبة الأزاريطة - MMG"
COMPANY = "Mohamed Mamdouh group"
SARA, RAGHAD = "sara@imed.local", "raghad@imed.local"
PAPER = "imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading.get_paper_cost"
# A fixed day with nothing else on it, so whatever the site holds (other days' counters and sales) stays out.
DAY = "2026-10-05"


class IntegrationTestDailyPrinting(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("daily_printing")
		self.machines = sorted(frappe.get_all("Printing Machine", filters={"cost_center": AZARITA, "disabled": 0}, pluck="name"))
		frappe.db.delete("Printer Reading", {"machine": ["in", self.machines]})
		frappe.db.delete("Daily Counter Reading", {"branch": AZARITA})
		# Sales of the test days made by anyone else (demo data) are left out.
		frappe.db.delete("Sales Invoice", {"posting_date": ["in", [DAY, add_days(DAY, -1)]], "cost_center": AZARITA})

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="daily_printing")

	@patch(PAPER, return_value=0.30)
	def day(self, consumed, _, date=None, start=1000, faults=None):
		"""The day's counters at Azarita: each machine, from `start`, up by its consumption; `faults` is
		{machine index: what happened}."""
		doc = frappe.new_doc("Daily Counter Reading")
		doc.update({"branch": AZARITA, "reading_date": date or DAY})
		for i, (row, used) in enumerate(zip(get_machines(AZARITA), consumed)):
			opening = row["opening_reading"] if row["opening_reading"] is not None else start
			row.update({"opening_reading": opening, "closing_reading": opening + used})
			if faults and i in faults:
				row.update({"fault": 1, "fault_note": faults[i]})
			doc.append("machines", row)
		doc.insert()
		doc.submit()
		return doc

	def sell(self, sheets, date=None, rate=1):
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": frappe.get_all("Customer", filters={"customer_group": ["!=", "طبيب"]}, pluck="name", limit=1)[0],
				"cost_center": AZARITA,
				"set_posting_time": 1,
				"posting_date": date or DAY,
				"items": [{"item_code": "PRINT-SVC", "qty": sheets, "rate": rate, "cost_center": AZARITA}],
			}
		).insert()
		invoice.submit()

	def report(self, **filters):
		return execute({"from_date": DAY, "to_date": DAY, "branch": AZARITA, **filters})[1]

	def test_each_machine_and_the_library_s_day(self):
		# 500 printed (300 + 150 + 50) and 480 sold: each machine takes its share of the sales by its share of
		# the printing (60%, 30%, 10%), and the machines add up to the day.
		self.sell(480)
		day = self.day([300, 150, 50])
		rows = self.report()
		machines, [total] = [r for r in rows if not r.get("is_total")], [r for r in rows if r.get("is_total")]
		self.assertEqual([r["machine"] for r in machines], [row.machine for row in day.machines])
		self.assertEqual([(r["consumed"], r["utilization"], r["sold"], r["variance"]) for r in machines],
			[(300, 60, 288, 12), (150, 30, 144, 6), (50, 10, 48, 2)])
		self.assertEqual((total["consumed"], total["sold"], total["variance"]), (500, 480, 20))
		self.assertAlmostEqual(sum(r["variance_value"] for r in machines), total["variance_value"], places=1)
		costs = {row.machine: row.cost_per_sheet for row in day.machines}
		for r in machines:
			self.assertAlmostEqual(r["variance_value"], round(r["variance"] * costs[r["machine"]], 2), places=2)

	def test_a_day_nothing_was_printed_shares_the_sales_equally(self):
		self.sell(30)
		self.day([0, 0, 0])
		machines = [r for r in self.report() if not r.get("is_total")]
		self.assertEqual([r["sold"] for r in machines], [10, 10, 10])
		self.assertEqual([r["variance"] for r in machines], [-10, -10, -10])

	def test_dates_and_branches(self):
		self.day([10, 10, 10], date=add_days(DAY, -1))
		self.day([20, 20, 20])
		self.assertEqual({r["reading_date"] for r in self.report()}, {frappe.utils.getdate(DAY)})
		# Two days: each day's 3 machines and total, then the period (a heading, 3 machines, a total).
		self.assertEqual(len(self.report(from_date=add_days(DAY, -1))), 13)
		self.assertEqual(self.report(branch="مكتبة المواساة - MMG"), [])
		# Another library's day is not in Azarita's.
		self.assertEqual({r.get("branch") for r in self.report() if r.get("branch")}, {AZARITA})

	def test_a_branch_manager_sees_her_own_library(self):
		self.day([10, 10, 10])
		frappe.set_user(SARA)
		self.assertEqual(len(self.report()), 4)
		frappe.set_user(RAGHAD)
		self.assertEqual(self.report(), [])

	def test_breakdowns(self):
		# PRN-09: a machine that broke down is ticked on the day's screen with what happened.
		self.day([100, 0, 50], faults={1: "Paper jam, technician called"})
		machines = [r for r in self.report() if not r.get("is_total")]
		self.assertEqual([r["fault"] for r in machines], [None, "Paper jam, technician called", None])

	def test_the_margin_on_a_sheet(self):
		# PRN-08: 400 sheets sold at 1 and 100 on offer at 0.70 is 470, 0.94 a sheet on average, against what a
		# printed sheet cost.
		self.sell(400)
		self.sell(100, rate=0.70)
		day = self.day([300, 150, 50])
		[total] = [r for r in self.report() if r.get("is_total")]
		self.assertEqual((day.sales_value, day.average_price), (470, 0.94))
		self.assertAlmostEqual(day.margin_per_sheet, round(0.94 - day.cost_per_sheet, 4), places=4)
		self.assertEqual((total["average_price"], total["margin_per_sheet"]), (day.average_price, day.margin_per_sheet))

	def test_a_month_by_machine(self):
		# PRN-03, PRN-09: over a period, each machine's printing, its share, its days broken down and the shortfall.
		first_day = add_days(DAY, -1)
		self.sell(100, date=first_day)
		self.day([100, 50, 50], date=first_day, faults={2: "Drum"})
		self.day([200, 100, 0], faults={2: "Drum again"})
		rows = self.report(from_date=first_day)
		heading = next(i for i, r in enumerate(rows) if r.get("machine_type") == "The Period")
		period, total = rows[heading + 1 : heading + 4], rows[heading + 4]
		self.assertEqual([r["consumed"] for r in period], [300, 150, 50])
		self.assertEqual([r["utilization"] for r in period], [60, 30, 10])
		self.assertEqual([r["fault"] for r in period], [None, None, "2 days"])
		self.assertEqual((total["consumed"], total["sold"], total["variance"]), (500, 100, 400))
		days = [r for r in rows[:heading] if r.get("is_total")]
		self.assertAlmostEqual(total["variance_value"], sum(d["variance_value"] for d in days), places=1)

