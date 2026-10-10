# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A doctor's ledger has no company or cost center, so the month lock (CORE-09) uses the default company:
# no entry is saved or cancelled in a closed month. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Doctor Ledger Entry"

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement

# Linked records already exist on the site or are made by the tests; without this list Frappe builds
# ERPNext's "_Test ..." records and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Academic Period",
	"Book Edition",
	"Customer",
	"Doctor Agreement",
	"Doctor Ledger Entry",
]


class IntegrationTestDoctorLedgerEntry(IntegrationTestCase):
	def new_entry(self, entry_date):
		return frappe.get_doc(
			{
				"doctype": "Doctor Ledger Entry",
				"agreement": make_agreement("Books"),
				"entry_date": entry_date,
				"entry_type": "Accrual",
				"amount": 100,
			}
		)

	def close_month(self):
		return frappe.get_doc(
			{
				"doctype": "Accounting Period",
				"period_name": "_Test Closed Month",
				"start_date": "2026-08-01",
				"end_date": "2026-08-31",
				"company": frappe.defaults.get_global_default("company"),
				"closed_documents": [{"document_type": "Doctor Ledger Entry", "closed": 1}],
			}
		).insert()

	def test_no_entry_saved_in_a_closed_month(self):
		period = self.close_month()
		try:
			self.assertRaises(frappe.ValidationError, self.new_entry("2026-08-15").insert)
			self.new_entry("2026-09-15").insert()
		finally:
			frappe.delete_doc("Accounting Period", period.name)

	def test_no_entry_cancelled_in_a_closed_month(self):
		entry = self.new_entry("2026-08-15").insert()
		entry.submit()
		period = self.close_month()
		try:
			self.assertRaises(frappe.ValidationError, entry.cancel)
			self.assertEqual(frappe.db.get_value("Doctor Ledger Entry", entry.name, "docstatus"), 1)
		finally:
			frappe.delete_doc("Accounting Period", period.name)
		# Once the month is open again, the entry is cancelled as usual.
		entry.reload()
		entry.cancel()
