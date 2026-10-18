# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A printing machine works in a library, is an Epson or a Riso, and takes its ink cost per sheet from its type
# unless one is given for it (PRN-01, PRN-08). Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Printing Machine"

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from imed_erp.imederp.doctype.printing_cost_settings.printing_cost_settings import get_machine_ink

# Linked records already exist on the site; without this list Frappe builds ERPNext's "_Test ..." records and
# commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Cost Center", "Warehouse"]

AZARITA = "مكتبة الأزاريطة - MMG"
AZARITA_STORE = "مخزن الأزاريطة - MMG"
RATES = "imed_erp.imederp.doctype.printing_cost_settings.printing_cost_settings.get_rates"


class IntegrationTestPrintingMachine(IntegrationTestCase):
	def machine(self, machine_type="Riso", **values):
		return frappe.get_doc(
			{
				"doctype": "Printing Machine",
				"machine_name": f"_Test Machine {frappe.generate_hash(length=6)}",
				"cost_center": AZARITA,
				"warehouse": AZARITA_STORE,
				"machine_type": machine_type,
				**values,
			}
		)

	def test_the_ink_cost_comes_from_the_type(self):
		# Riso ink costs more (PRN-08); the rates are on Printing Cost Settings.
		epson, riso = self.machine("Epson").insert(), self.machine("Riso").insert()
		self.assertEqual(flt(epson.ink_per_sheet), get_machine_ink("Epson"))
		self.assertEqual(flt(riso.ink_per_sheet), get_machine_ink("Riso"))
		self.assertGreater(flt(riso.ink_per_sheet), flt(epson.ink_per_sheet))

	def test_an_assumed_rate_until_the_owner_gives_one(self):
		# With nothing saved on the settings yet, the defaults on the screen: 0.05 and 0.10.
		with patch.object(frappe.get_cached_doc("Printing Cost Settings"), "get", return_value=None):
			self.assertEqual((get_machine_ink("Epson"), get_machine_ink("Riso")), (0.05, 0.10))

	def test_a_rate_given_for_the_machine_stays(self):
		machine = self.machine("Riso", ink_per_sheet=0.12).insert()
		self.assertEqual(flt(machine.ink_per_sheet), 0.12)
		machine.machine_type = "Epson"
		machine.save()
		self.assertEqual(flt(machine.ink_per_sheet), 0.12)

	def test_the_type_s_rate_follows_a_change_of_type(self):
		machine = self.machine("Riso").insert()
		machine.machine_type = "Epson"
		machine.save()
		self.assertEqual(flt(machine.ink_per_sheet), get_machine_ink("Epson"))

	def test_a_machine_works_in_a_library(self):
		for branch in ("قاعات Imed - MMG", "مكتبات 2Be Doctor - MMG"):
			with self.subTest(branch):
				self.assertRaises(frappe.ValidationError, self.machine(cost_center=branch).insert)
		self.assertRaises(frappe.MandatoryError, self.machine(cost_center=None).insert)

	def test_what_cannot_be(self):
		self.assertRaisesRegex(frappe.ValidationError, "future", self.machine(last_maintenance=add_days(today(), 1)).insert)
		self.assertRaisesRegex(frappe.ValidationError, "negative", self.machine(ink_per_sheet=-0.01).insert)
		self.assertRaises(frappe.ValidationError, self.machine(machine_type="HP").insert)
		self.machine(last_maintenance=today(), model="Riso SF 5030").insert()

	def test_out_of_service(self):
		machine = self.machine().insert()
		self.assertEqual(frappe.get_meta("Printing Machine").get_field("disabled").label, "Out of Service")
		machine.disabled = 1
		machine.save()
