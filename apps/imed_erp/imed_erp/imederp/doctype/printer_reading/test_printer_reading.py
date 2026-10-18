# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Printer readings (PRN-01/02): a reading is of one printing machine, in its library; it starts where the machine's
# last reading ended, its counter only goes up, and sheets used = closing - opening, compared with sheets sold.
# Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Printer Reading"

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.printer_reading.printer_reading import get_opening

# The cost centers and machines already exist on the site or are made here. Without this Frappe builds ERPNext's
# "_Test ..." records for them and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Cost Center", "Printer Reading", "Printing Machine"]

MAWASAH = "مكتبة المواساة - MMG"


class IntegrationTestPrinterReading(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("reading_test")
		self.machine = make_machine()

	def tearDown(self):
		frappe.db.rollback(save_point="reading_test")

	def reading(self, closing, opening=None, date="2026-10-07", sold=None, machine=None, submit=True, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Printer Reading",
				"machine": machine or self.machine,
				"reading_date": date,
				"opening_reading": opening,
				"closing_reading": closing,
				"sold_sheets": sold,
				**values,
			}
		).insert()
		if submit:
			doc.submit()
		return doc

	def test_consumed_and_variance(self):
		# Card PRN definition of done: a machine used 500 sheets and 480 were sold, 20 sheets short.
		reading = self.reading(1500, opening=1000, sold=480)
		self.assertEqual((reading.consumed, reading.variance), (500, 20))

	def test_each_reading_starts_where_the_last_ended(self):
		first = self.reading(1500, opening=1000)
		self.assertEqual(get_opening(self.machine), 1500)
		# Whatever is typed, the opening is the machine's last closing reading.
		second = self.reading(1800, opening=1, date="2026-10-08")
		self.assertEqual((second.opening_reading, second.consumed), (first.closing_reading, 300))
		# Each machine has its own counter.
		other = make_machine("_Test Reading Machine 2")
		self.assertIsNone(get_opening(other))
		self.assertEqual(self.reading(40, opening=10, machine=other).opening_reading, 10)

	def test_a_counter_only_goes_up(self):
		self.reading(1500, opening=1000)
		self.assertRaisesRegex(frappe.ValidationError, "below the opening", self.reading, 1400, date="2026-10-08")
		self.assertRaisesRegex(frappe.ValidationError, "cannot be dated before", self.reading, 1600, date="2026-10-06")
		self.reading(1500, date="2026-10-08")  # nothing printed: allowed

	def test_a_draft_takes_the_reading_submitted_before_it(self):
		self.reading(1000, opening=900)
		draft = self.reading(1200, date="2026-10-08", submit=False)
		self.reading(1300, date="2026-10-08")
		# Submitted after another reading of the machine, it starts from that one: 1200 is now below it.
		self.assertRaisesRegex(frappe.ValidationError, "below the opening", draft.submit)

	def test_the_library_is_the_machine_s(self):
		reading = self.reading(1500, opening=1000, branch="مكتبة الأزاريطة - MMG")
		self.assertEqual(reading.branch, MAWASAH)

	def test_a_machine_out_of_service_takes_no_reading(self):
		frappe.db.set_value("Printing Machine", self.machine, "disabled", 1)
		self.assertRaisesRegex(frappe.ValidationError, "out of service", self.reading, 1500, opening=1000)

	def test_only_the_latest_reading_is_cancelled(self):
		first = self.reading(1500, opening=1000)
		second = self.reading(1800, date="2026-10-08")
		self.assertRaisesRegex(frappe.ValidationError, "later reading", first.cancel)
		second.cancel()
		first.reload()
		first.cancel()
		self.assertIsNone(get_opening(self.machine))


def make_machine(name="_Test Reading Machine"):
	if frappe.db.exists("Printing Machine", name):
		return name
	return (
		frappe.get_doc(
			{
				"doctype": "Printing Machine",
				"machine_name": name,
				"cost_center": MAWASAH,
				"machine_type": "Riso",
				"warehouse": "المخزن المركزي بالمواساة - MMG",
			}
		)
		.insert()
		.name
	)
