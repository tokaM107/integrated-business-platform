# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A doctor's ledger has no company or cost center, so the month lock (CORE-09) uses the default company:
# no entry is saved or cancelled in a closed month. An accrual names the invoice line it comes from, and a line
# is counted once (DOC-07). Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Doctor Ledger Entry"

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement, make_doctor

# Linked records already exist on the site or are made by the tests; without this list Frappe builds
# ERPNext's "_Test ..." records and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Academic Period",
	"Book Edition",
	"Customer",
	"Doctor Agreement",
	"Doctor Ledger Entry",
	"Journal Entry",
	"Sales Invoice",
]

COMPANY = "Mohamed Mamdouh group"
MAWASAH = "مكتبة المواساة - MMG"


class IntegrationTestDoctorLedgerEntry(IntegrationTestCase):
	def new_entry(self, entry_date, **values):
		return frappe.get_doc(
			{
				"doctype": "Doctor Ledger Entry",
				"agreement": make_agreement("Books"),
				"entry_date": entry_date,
				"entry_type": "Accrual",
				"amount": 100,
				**values,
			}
		)

	def draft_sale(self, lines=1):
		"""A draft sale with `lines` rows: the ledger only needs its invoice and line names."""
		item = frappe.get_all("Item", filters={"is_sales_item": 1, "disabled": 0, "has_variants": 0}, pluck="name", limit=1)[0]
		return frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": make_doctor(),
				"cost_center": MAWASAH,
				"items": [{"item_code": item, "qty": 1, "rate": 100, "cost_center": MAWASAH} for _ in range(lines)],
			}
		).insert()

	def test_an_invoice_line_is_counted_once(self):
		sale = self.draft_sale()
		line = {"sales_invoice": sale.name, "invoice_item": sale.items[0].name}
		first = self.new_entry(today(), **line).insert()
		self.assertRaisesRegex(frappe.ValidationError, "already in the doctor's ledger", self.new_entry(today(), **line).insert)

		# Once the first is cancelled (its sale was cancelled), the line may be counted again.
		first.submit()
		first.cancel()
		self.new_entry(today(), **line).insert()

	def test_an_invoice_line_is_on_its_invoice(self):
		one, other = self.draft_sale(), self.draft_sale()
		entry = self.new_entry(today(), sales_invoice=other.name, invoice_item=one.items[0].name)
		self.assertRaisesRegex(frappe.ValidationError, "is not on invoice", entry.insert)

	def test_the_source_is_filled_by_the_system(self):
		meta = frappe.get_meta("Doctor Ledger Entry")
		for field in ("sales_invoice", "invoice_item", "journal_entry"):
			with self.subTest(field):
				self.assertTrue(meta.get_field(field).read_only)
				self.assertTrue(meta.get_field(field).no_copy)

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
