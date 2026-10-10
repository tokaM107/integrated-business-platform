# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Buying paper and materials (LIB-07, ACC-12), set up by setup/setup_buying.py: the library buys directly,
# with one purchase invoice that updates stock. Real A4 paper item, real store (Mawasah's raw materials);
# everything made here is rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_buying

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

# A test module outside a doctype folder builds no "_Test ..." records, so it needs (and may have) no
# IGNORE_TEST_RECORD_DEPENDENCIES; keep it here, not under a doctype.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
PAPER = "A4-PAPER"
STORE = f"خامات المواساة - {ABBR}"
BOX = "كرتونة"
SHIPPING = f"مصروفات الشحن والنقل - {ABBR}"
MAIN_TREASURY = f"الخزينة الرئيسية - {ABBR}"
# Sara runs Azarita's library: she pays only from its cash box or the group's wallets (imederp/treasuries.py).
BRANCH_MANAGER = "sara@imed.local"
AZARITA = f"مكتبة الأزاريطة - {ABBR}"
AZARITA_CASH = f"خزينة مكتبة الأزاريطة - {ABBR}"


def labels_of(report):
	from frappe.desk.query_report import run

	result = run(report, filters={"company": COMPANY, "report_date": today(), "party_type": "Supplier"})
	return [c["label"] for c in result["columns"] if isinstance(c, dict)]


class IntegrationTestBuying(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.supplier = (
			frappe.get_doc(
				{"doctype": "Supplier", "supplier_name": "_Test Paper Supplier", "supplier_group": "موردي الورق والخامات"}
			)
			.insert()
			.name
		)

	def tearDown(self):
		frappe.set_user("Administrator")

	def stock(self):
		"""Sheets in the store and their total value."""
		row = frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": STORE}, ["actual_qty", "stock_value"])
		return tuple(flt(v) for v in row) if row else (0.0, 0.0)

	def buy(self, boxes, rate, **values):
		invoice = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": COMPANY,
				"supplier": values.pop("supplier", self.supplier),
				"posting_date": today(),
				"set_warehouse": STORE,
				"items": [{"item_code": PAPER, "qty": boxes, "uom": BOX, "rate": rate, "warehouse": STORE}],
				**values,
			}
		).insert()
		invoice.submit()
		return invoice

	def test_a_new_purchase_invoice_updates_stock(self):
		self.assertEqual(frappe.new_doc("Purchase Invoice").update_stock, 1)

		before = self.stock()
		self.buy(2, 650)
		self.assertEqual(self.stock(), (before[0] + 5000, before[1] + 1300))

	def test_shipping_is_added_to_the_cost_of_the_paper(self):
		# Two boxes at 650 (0.26 a sheet) and 100 for shipping: 1,400 for 5,000 sheets, 0.28 a sheet once
		# the shipping is added with a Landed Cost Voucher.
		before = self.stock()
		invoice = self.buy(2, 650)
		voucher = frappe.get_doc(
			{
				"doctype": "Landed Cost Voucher",
				"company": COMPANY,
				"posting_date": today(),
				"distribute_charges_based_on": "Amount",
				"purchase_receipts": [
					{
						"receipt_document_type": "Purchase Invoice",
						"receipt_document": invoice.name,
						"supplier": self.supplier,
						"grand_total": invoice.grand_total,
					}
				],
				"taxes": [{"description": "شحن الورق", "amount": 100, "expense_account": SHIPPING}],
			}
		)
		voucher.get_items_from_purchase_receipts()
		voucher.insert()
		voucher.submit()

		self.assertEqual(self.stock(), (before[0] + 5000, before[1] + 1400))
		if before == (0.0, 0.0):
			rate = frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": STORE}, "valuation_rate")
			self.assertAlmostEqual(flt(rate), 0.28, places=4)

	def pay(self, invoice, amount, treasury, **values):
		"""A payment to the supplier against `invoice`, from `treasury`; not saved."""
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		payment = get_payment_entry("Purchase Invoice", invoice.name)
		payment.update({"paid_from": treasury, "paid_amount": amount, "received_amount": amount, **values})
		payment.references[0].allocated_amount = amount
		return payment

	def test_paying_part_of_a_credit_purchase(self):
		# Two boxes on 30 days' credit: 1,300 owed. 650 paid from the main treasury leaves 650.
		invoice = self.buy(2, 650, payment_terms_template="آجل 30 يوم")
		self.assertEqual(invoice.outstanding_amount, 1300)

		payment = self.pay(invoice, 650, MAIN_TREASURY).insert()
		payment.submit()
		self.assertEqual(payment.payment_type, "Pay")
		self.assertEqual(frappe.db.get_value("Purchase Invoice", invoice.name, "outstanding_amount"), 650)

	def test_payables_report_shows_what_is_left_in_arabic(self):
		from frappe.desk.query_report import run

		# Its own supplier: the other tests' purchases stay on the class supplier until the class rolls back.
		supplier = frappe.get_doc(
			{"doctype": "Supplier", "supplier_name": "_Test Payables Supplier", "supplier_group": "موردي الورق والخامات"}
		).insert()
		invoice = self.buy(2, 650, supplier=supplier.name, payment_terms_template="آجل 30 يوم")
		payment = self.pay(invoice, 650, MAIN_TREASURY).insert()
		payment.submit()

		lang = frappe.local.lang
		frappe.local.lang = "ar"
		try:
			for report in ("Accounts Payable", "Accounts Payable Summary"):
				with self.subTest(report):
					result = run(report, filters={"company": COMPANY, "report_date": today(), "party_type": "Supplier"})
					rows = [r for r in result["result"] if isinstance(r, dict) and r.get("party") == supplier.name]
					self.assertEqual(sum(flt(r["outstanding"]) for r in rows), 650)
					labels = [c["label"] for c in result["columns"] if isinstance(c, dict)]
					self.assertIn("المبلغ المستحق", labels)
			# ERPNext's own Arabic for these two is wrong; translations/ar.csv corrects it.
			self.assertIn("تاريخ الاستحقاق", labels_of("Accounts Payable"))
		finally:
			frappe.local.lang = lang

	def test_branch_manager_pays_a_supplier_only_from_her_cash_box(self):
		# The main store's invoices are the accountant's (Sara has no access to its warehouse), so her
		# payment is made to the supplier directly, not against an invoice.
		def payment(treasury):
			return frappe.get_doc(
				{
					"doctype": "Payment Entry",
					"payment_type": "Pay",
					"company": COMPANY,
					"posting_date": today(),
					"party_type": "Supplier",
					"party": self.supplier,
					"paid_from": treasury,
					"paid_to": frappe.get_cached_value("Company", COMPANY, "default_payable_account"),
					"paid_amount": 200,
					"received_amount": 200,
					"cost_center": AZARITA,
				}
			)

		frappe.set_user(BRANCH_MANAGER)
		for treasury in (MAIN_TREASURY, f"خزينة مكتبة المواساة - {ABBR}"):
			with self.subTest(treasury):
				self.assertRaisesRegex(frappe.ValidationError, "treasury", payment(treasury).insert)
		payment(AZARITA_CASH).insert().submit()
