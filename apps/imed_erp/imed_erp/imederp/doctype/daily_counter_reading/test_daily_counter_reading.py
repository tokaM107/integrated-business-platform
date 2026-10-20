# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A library's counters for the day on one screen (PRN-01): every machine of the branch in service, each opening
# from the machine's last reading, saved once into one Printer Reading per machine; what they printed is set
# against the printing and copying the library sold that day (PRN-02). Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Daily Counter Reading"

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days

from imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading import get_machines
from imed_erp.imederp.doctype.printing_cost_settings.printing_cost_settings import get_rates
from imed_erp.imederp.sales_cancellation import cancel_with_reason

# Linked records already exist on the site (the libraries' machines come from setup_library.py); without this list
# Frappe builds ERPNext's "_Test ..." records and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Cost Center", "Daily Counter Reading", "Printer Reading", "Printing Machine"]

AZARITA = "مكتبة الأزاريطة - MMG"
MAWASAH = "مكتبة المواساة - MMG"
COMPANY = "Mohamed Mamdouh group"
# A fixed day with nothing else on it, so whatever the site holds (other days' counters and sales) stays out.
DAY = "2026-10-09"
# The store's paper price (0.26) plus waste (0.04), fixed for these tests; test_paper_stock.py reads it from a real
# purchase.
PAPER = "imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading.get_paper_cost"
SARA = "sara@imed.local"


class IntegrationTestDailyCounterReading(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("daily_counters")
		# Azarita's three machines (1 Epson, 2 Riso), from setup_library.py; no reading yet in this test.
		self.machines = frappe.get_all("Printing Machine", filters={"cost_center": AZARITA, "disabled": 0}, pluck="name")
		frappe.db.delete("Printer Reading", {"machine": ["in", self.machines]})
		frappe.db.delete("Daily Counter Reading", {"branch": AZARITA})
		frappe.db.delete("Sales Invoice", {"posting_date": ["in", [DAY, add_days(DAY, -1)]], "cost_center": AZARITA})

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="daily_counters")

	def sheet(self, closings, date="2026-10-07", openings=None, submit=True, **values):
		doc = frappe.new_doc("Daily Counter Reading")
		doc.update({"branch": AZARITA, "reading_date": date, **values})
		for row in get_machines(AZARITA):
			if row["machine"] in closings:
				row["closing_reading"] = closings[row["machine"]]
				if openings and row["machine"] in openings:
					row["opening_reading"] = openings[row["machine"]]
				doc.append("machines", row)
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def test_sara_records_her_three_machines_at_once(self):
		# Card PRN definition of done: Sara records the counters of Azarita's 3 machines on one screen.
		self.assertEqual(len(self.machines), 3)
		frappe.set_user(SARA)
		first, second, third = sorted(self.machines)
		sheet = self.sheet({first: 1500, second: 800, third: 300}, openings={first: 1000, second: 500, third: 100})
		frappe.set_user("Administrator")
		readings = {
			r.machine: r
			for r in frappe.get_all(
				"Printer Reading",
				filters={"daily_counter_reading": sheet.name, "docstatus": 1},
				fields=["machine", "opening_reading", "closing_reading", "consumed", "branch", "owner"],
			)
		}
		self.assertEqual({m: r.consumed for m, r in readings.items()}, {first: 500, second: 300, third: 200})
		self.assertEqual({r.branch for r in readings.values()}, {AZARITA})
		self.assertEqual({r.owner for r in readings.values()}, {SARA})
		self.assertTrue(all(row.printer_reading for row in sheet.machines))

	def test_the_next_day_starts_where_the_last_ended(self):
		first, second, third = sorted(self.machines)
		self.sheet({first: 1500, second: 800, third: 300}, openings={first: 1000, second: 500, third: 100})
		self.assertEqual({row["machine"]: row["opening_reading"] for row in get_machines(AZARITA)}, {first: 1500, second: 800, third: 300})
		# Typed openings are ignored once a machine has a reading.
		sheet = self.sheet({first: 1600, second: 800, third: 350}, date="2026-10-08", openings={first: 1})
		self.assertEqual([row.consumed for row in sorted(sheet.machines, key=lambda r: r.machine)], [100, 0, 50])

	def test_a_reading_lower_than_the_last_is_refused(self):
		first, second, third = sorted(self.machines)
		self.sheet({first: 1500, second: 800, third: 300}, openings={first: 1000, second: 500, third: 100})
		self.assertRaisesRegex(
			frappe.ValidationError, "counter only goes up", self.sheet, {first: 1400, second: 800, third: 300}, date="2026-10-08"
		)

	def test_every_machine_once_a_day(self):
		first, second, third = sorted(self.machines)
		openings = {first: 1, second: 1, third: 1}
		self.assertRaisesRegex(frappe.ValidationError, "missing", self.sheet, {first: 10, second: 10}, openings=openings)
		self.sheet({first: 10, second: 10, third: 10}, openings=openings)
		self.assertRaisesRegex(frappe.ValidationError, "already has its counters", self.sheet, {first: 20, second: 20, third: 20})
		# A machine out of service is left out.
		frappe.db.set_value("Printing Machine", third, "disabled", 1)
		self.sheet({first: 20, second: 20}, date="2026-10-08")

	def test_a_first_reading_needs_its_opening(self):
		first, second, third = sorted(self.machines)
		self.assertRaisesRegex(frappe.ValidationError, "first reading", self.sheet, {first: 10, second: 10, third: 10})

	def test_cancelled_with_its_readings_and_only_from_here(self):
		first, second, third = sorted(self.machines)
		sheet = self.sheet({first: 10, second: 10, third: 10}, openings={first: 1, second: 1, third: 1})
		reading = frappe.get_doc("Printer Reading", sheet.machines[0].printer_reading)
		self.assertRaisesRegex(frappe.ValidationError, "Cancel that instead", reading.cancel)
		sheet.cancel()
		self.assertEqual(
			set(frappe.get_all("Printer Reading", filters={"daily_counter_reading": sheet.name}, pluck="docstatus")), {2}
		)

	def test_a_library_only(self):
		self.assertRaises(frappe.ValidationError, self.sheet, {}, branch="قاعات Imed - MMG")

	# ---------- PRN-02: what was sold, from the day's sales ----------

	def sell(self, rows, library=AZARITA, date=None, is_return=False):
		"""A submitted sale of (service, sheets) rows at the library."""
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": frappe.get_all("Customer", filters={"customer_group": ["!=", "طبيب"]}, pluck="name", limit=1)[0],
				"cost_center": library,
				"set_posting_time": 1,
				"posting_date": date or DAY,
				"items": [{"item_code": item, "qty": qty, "rate": 1, "cost_center": library} for item, qty in rows],
			}
		)
		invoice.insert()
		invoice.submit()
		return invoice

	def test_sold_sheets_come_from_the_day_s_sales(self):
		# Card PRN definition of done: the machines printed 500 sheets and 480 were sold, 20 short.
		first, second, third = sorted(self.machines)
		self.sell([("PRINT-SVC", 300), ("COPY-SVC", 100)])
		self.sell([("COPY-SVC", 80)])
		# Not counted: another library's sale, another day's, and nothing typed is kept.
		self.sell([("PRINT-SVC", 1000)], library=MAWASAH)
		self.sell([("PRINT-SVC", 1000)], date=add_days(DAY, -1))
		sheet = self.sheet(
			{first: 1300, second: 650, third: 150}, date=DAY, openings={first: 1000, second: 500, third: 100}, sold_sheets=1
		)
		self.assertEqual((sheet.total_consumed, sheet.sold_sheets, sheet.variance), (500, 480, 20))

	def test_a_later_sale_of_the_day_is_taken_in(self):
		first, second, third = sorted(self.machines)
		sheet = self.sheet({first: 1300, second: 650, third: 150}, date=DAY, openings={first: 1000, second: 500, third: 100})
		self.assertEqual((sheet.sold_sheets, sheet.variance), (0, 500))
		late = self.sell([("COPY-SVC", 30)])
		self.assertEqual(frappe.db.get_value("Daily Counter Reading", sheet.name, ["sold_sheets", "variance"]), (30, 470))
		cancel_with_reason("Sales Invoice", late.name, "Test: wrong service")
		self.assertEqual(frappe.db.get_value("Daily Counter Reading", sheet.name, ["sold_sheets", "variance"]), (0, 500))

	def test_a_refund_takes_no_sheets_back(self):
		# The paper was printed and the counters counted it.
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		first, second, third = sorted(self.machines)
		sale = self.sell([("COPY-SVC", 50)])
		refund = make_sales_return(sale.name)
		refund.return_reason = "_Test returned by the accountant"
		refund.insert()
		refund.submit()
		sheet = self.sheet({first: 1050, second: 500, third: 100}, date=DAY, openings={first: 1000, second: 500, third: 100})
		self.assertEqual((sheet.sold_sheets, sheet.variance), (50, 0))

	# ---------- PRN-08/09: the variance in money ----------

	def ink(self, machine):
		return frappe.db.get_value("Printing Machine", machine, "ink_per_sheet")

	@patch(PAPER, return_value=0.30)
	def test_the_variance_in_money(self, _):
		# 20 sheets short x what a printed sheet cost: paper and waste + the machine's ink + overheads, the Epson
		# (cheaper ink) and the Risos weighted by what each printed (300, 150 and 50 sheets).
		first, second, third = sorted(self.machines)  # Epson, Riso, Riso
		self.sell([("PRINT-SVC", 480)])
		sheet = self.sheet({first: 1300, second: 650, third: 150}, date=DAY, openings={first: 1000, second: 500, third: 100})
		overheads = get_rates().overheads_per_sheet
		costs = {row.machine: row.cost_per_sheet for row in sheet.machines}
		for machine in self.machines:
			self.assertAlmostEqual(costs[machine], 0.30 + self.ink(machine) + overheads, places=4)
		self.assertLess(costs[first], costs[second])
		expected = round((300 * costs[first] + 150 * costs[second] + 50 * costs[third]) / 500, 4)
		self.assertAlmostEqual(sheet.cost_per_sheet, expected, places=4)
		self.assertEqual(sheet.variance, 20)
		self.assertAlmostEqual(sheet.variance_value, round(20 * expected, 2), places=2)

	@patch(PAPER, return_value=0.30)
	def test_the_cost_stays_as_submitted(self, _):
		# A later sale takes the same cost per sheet, even after the rates changed.
		first, second, third = sorted(self.machines)
		sheet = self.sheet({first: 1300, second: 650, third: 150}, date=DAY, openings={first: 1000, second: 500, third: 100})
		cost = sheet.cost_per_sheet
		frappe.db.set_value("Printing Machine", second, "ink_per_sheet", 5)
		self.sell([("COPY-SVC", 100)])
		self.assertEqual(
			frappe.db.get_value("Daily Counter Reading", sheet.name, ["cost_per_sheet", "variance", "variance_value"]),
			(cost, 400, round(400 * cost, 2)),
		)

	@patch(PAPER, return_value=0.30)
	def test_a_day_nothing_was_printed(self, _):
		first, second, third = sorted(self.machines)
		sheet = self.sheet({first: 1000, second: 500, third: 100}, date=DAY, openings={first: 1000, second: 500, third: 100})
		self.assertAlmostEqual(sheet.cost_per_sheet, round(sum(r.cost_per_sheet for r in sheet.machines) / 3, 4), places=4)
		self.assertEqual((sheet.variance, sheet.variance_value), (0, 0))

	@patch(PAPER, return_value=0)
	def test_with_no_paper_price_it_says_so(self, _):
		first, second, third = sorted(self.machines)
		with patch("frappe.msgprint") as msgprint:
			self.sheet({first: 1010, second: 500, third: 100}, date=DAY, openings={first: 1000, second: 500, third: 100})
		self.assertIn("no paper price", str(msgprint.call_args))

	def test_a_breakdown_says_what_happened(self):
		first, second, third = sorted(self.machines)
		doc = frappe.new_doc("Daily Counter Reading")
		doc.update({"branch": AZARITA, "reading_date": "2026-10-07"})
		for row in get_machines(AZARITA):
			row.update({"opening_reading": 1, "closing_reading": 1})
			if row["machine"] == third:
				row["fault"] = 1
			doc.append("machines", row)
		self.assertRaisesRegex(frappe.ValidationError, "say what happened", doc.insert)
		doc.machines[-1].fault_note = "Paper jam"
		doc.insert()


	def test_sec08_another_library_s_machines_and_counters_are_not_shown(self):
		from imed_erp.imederp.doctype.printer_reading.printer_reading import get_opening

		mawasah_machine = frappe.get_all("Printing Machine", filters={"cost_center": MAWASAH}, pluck="name", limit=1)
		frappe.set_user(SARA)
		self.assertTrue(get_machines(AZARITA))
		self.assertRaises(frappe.PermissionError, get_machines, MAWASAH)
		if mawasah_machine:
			self.assertRaises(frappe.PermissionError, get_opening, mawasah_machine[0])
		get_opening(self.machines[0])
