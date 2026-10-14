# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The doctor's amount on every copy sold goes to his ledger (DOC-07, LIB-05; imederp/doctor_accrual.py): one entry
# per invoice line, never twice, cancelled with the sale and taken back by a credit note. Real stores and
# accounts; rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_doctor_accrual

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate

from imed_erp.imederp.doctor_accrual import accrue
from imed_erp.imederp.doctype.book_edition.test_book_edition import PAPER_COST, make_agreement
from imed_erp.imederp.sales_cancellation import cancel_with_reason
from imed_erp.imederp import test_edition_sales
from imed_erp.imederp.test_edition_sales import COMPANY, EDITIONS, MAWASAH, RAGHAD

LEDGER = "Doctor Ledger Entry"


class IntegrationTestDoctorAccrual(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.items = [test_edition_sales.IntegrationTestEditionSales.make_item(f"_Test Accrual Book {n}") for n in (1, 2)]
		receipt = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": COMPANY,
				"items": [{"item_code": item, "qty": 100, "basic_rate": 60, "t_warehouse": EDITIONS} for item in cls.items],
			}
		).insert()
		receipt.submit()
		cls.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test Accrual Buyer",
				"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0],
			}
		).insert().name
		cls.term = test_edition_sales.IntegrationTestEditionSales.make_period("_Test Accrual Term", "2026-09-01", "2026-12-31")
		cls.service = frappe.get_all("Item", filters={"is_stock_item": 0, "is_sales_item": 1, "disabled": 0}, pluck="name", limit=1)[0]

	def setUp(self):
		frappe.db.savepoint("accrual_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="accrual_test")

	@patch(PAPER_COST, return_value=0.30)
	def edition(self, _, item=None, amount_per_copy=80):
		doc = frappe.get_doc(
			{
				"doctype": "Book Edition",
				"edition_name": f"_Test Accrual Edition {frappe.generate_hash(length=6)}",
				"agreement": make_agreement("Books", amount_per_copy),
				"item_code": item or self.items[0],
				"cost_center": MAWASAH,
				"edition_date": "2026-09-15",
				"period": self.term,
				"pages": 100,
				"doctor_qty": 50,
				"extra_qty": 0,
			}
		).insert()
		doc.submit()
		return doc

	def sell(self, rows):
		"""A submitted sale at Mawasah of (item, qty) rows."""
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": self.customer,
				"cost_center": MAWASAH,
				"update_stock": 1,
				"set_warehouse": EDITIONS,
				"items": [
					{"item_code": item, "qty": qty, "rate": 150, "warehouse": EDITIONS, "cost_center": MAWASAH}
					for item, qty in rows
				],
			}
		).insert()
		invoice.submit()
		return invoice

	def entries(self, invoice):
		return frappe.get_all(
			LEDGER,
			filters={"sales_invoice": invoice, "docstatus": 1},
			fields=["name", "agreement", "period", "entry_type", "edition", "qty", "amount", "invoice_item", "entry_date"],
			order_by="creation",
		)

	def balance(self, agreement):
		return flt(frappe.db.get_value("Doctor Agreement", agreement, "balance"))

	def test_three_copies_at_80_owe_the_doctor_240(self):
		# Card A8's definition of done: an edition at 80 a copy, 3 copies sold, 240 in the doctor's ledger.
		edition = self.edition()
		before = self.balance(edition.agreement)
		sale = self.sell([(self.items[0], 3)])
		[entry] = self.entries(sale.name)
		self.assertEqual(
			(entry.agreement, entry.period, entry.entry_type, entry.edition, entry.qty, entry.amount, entry.invoice_item, entry.entry_date),
			(edition.agreement, self.term, "Accrual", edition.name, 3, 240, sale.items[0].name, getdate(sale.posting_date)),
		)
		self.assertEqual(self.balance(edition.agreement) - before, 240)

	def test_counting_an_invoice_again_adds_nothing(self):
		edition = self.edition()
		before = self.balance(edition.agreement)
		sale = self.sell([(self.items[0], 3)])
		accrue(frappe.get_doc("Sales Invoice", sale.name))
		accrue(frappe.get_doc("Sales Invoice", sale.name))
		self.assertEqual([e.amount for e in self.entries(sale.name)], [240])
		self.assertEqual(self.balance(edition.agreement) - before, 240)

	def test_one_entry_per_line(self):
		# Two lines of the same edition are two entries, each keyed by its own line; a line with no edition (a
		# service) adds nothing.
		first = self.edition()
		second = self.edition(item=self.items[1], amount_per_copy=70)
		sale = self.sell([(self.items[0], 2), (self.items[0], 1), (self.items[1], 4), (self.service, 1)])
		self.assertEqual(
			[(e.edition, e.amount, e.invoice_item) for e in self.entries(sale.name)],
			[
				(first.name, 160, sale.items[0].name),
				(first.name, 80, sale.items[1].name),
				(second.name, 280, sale.items[2].name),
			],
		)

	def test_a_cancelled_sale_takes_its_amount_back(self):
		edition = self.edition()
		before = self.balance(edition.agreement)
		sale = self.sell([(self.items[0], 3)])
		[entry] = self.entries(sale.name)
		cancel_with_reason("Sales Invoice", sale.name, "Test: wrong copies")
		self.assertEqual(frappe.db.get_value(LEDGER, entry.name, "docstatus"), 2)
		self.assertEqual(self.balance(edition.agreement), before)

	def test_copies_returned_are_taken_off(self):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		edition = self.edition()
		before = self.balance(edition.agreement)
		sale = self.sell([(self.items[0], 3)])
		credit = make_sales_return(sale.name)
		credit.items[0].qty = -1
		credit.insert()
		credit.submit()
		[entry] = self.entries(credit.name)
		self.assertEqual((entry.entry_type, entry.qty, entry.amount, entry.edition), ("Adjustment", -1, -80, edition.name))
		self.assertEqual(self.balance(edition.agreement) - before, 160)

	def test_a_branch_manager_s_sale_posts_to_the_ledger_she_cannot_read(self):
		edition = self.edition()
		frappe.set_user(RAGHAD)
		self.assertFalse(frappe.has_permission(LEDGER, "read"))
		sale = self.sell([(self.items[0], 2)])
		frappe.set_user("Administrator")
		self.assertEqual([e.amount for e in self.entries(sale.name)], [160])
