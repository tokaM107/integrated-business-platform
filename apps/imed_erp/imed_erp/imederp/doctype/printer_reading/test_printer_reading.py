# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Printer readings (PRN-01/02): sheets used = closing - opening, compared with sheets sold; libraries only.
# Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Printer Reading"

import frappe
from frappe.tests import IntegrationTestCase

# The cost centers already exist on the site. Without this Frappe builds ERPNext's "_Test ..." records for
# them and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Cost Center", "Printer Reading"]


class IntegrationTestPrinterReading(IntegrationTestCase):
	def make_reading(self, branch="مكتبة المواساة - MMG", opening=1000, closing=1500, sold=480):
		return frappe.get_doc(
			{
				"doctype": "Printer Reading",
				"branch": branch,
				"machine": "Riso 1",
				"reading_date": "2026-10-07",
				"opening_reading": opening,
				"closing_reading": closing,
				"sold_sheets": sold,
			}
		).insert()

	def test_consumed_and_variance(self):
		reading = self.make_reading()
		self.assertEqual(reading.consumed, 500)
		self.assertEqual(reading.variance, 20)

	def test_rejects_wrong_readings_and_branches(self):
		for title, values in (
			("closing below opening", {"opening": 1500, "closing": 1000}),
			("not a library", {"branch": "قاعات Imed - MMG"}),
			("a group", {"branch": "مكتبات 2Be Doctor - MMG"}),
		):
			with self.subTest(title):
				self.assertRaises(frappe.ValidationError, self.make_reading, **values)
