# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A library's counters for the day on one screen (PRN-01): every machine of the branch in service, each opening
# from the machine's last reading, saved once into one Printer Reading per machine. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Daily Counter Reading"

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading import get_machines

# Linked records already exist on the site (the libraries' machines come from setup_library.py); without this list
# Frappe builds ERPNext's "_Test ..." records and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Cost Center", "Daily Counter Reading", "Printer Reading", "Printing Machine"]

AZARITA = "مكتبة الأزاريطة - MMG"
SARA = "sara@imed.local"


class IntegrationTestDailyCounterReading(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("daily_counters")
		# Azarita's three machines (1 Epson, 2 Riso), from setup_library.py; no reading yet in this test.
		self.machines = frappe.get_all("Printing Machine", filters={"cost_center": AZARITA, "disabled": 0}, pluck="name")
		frappe.db.delete("Printer Reading", {"machine": ["in", self.machines]})

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
