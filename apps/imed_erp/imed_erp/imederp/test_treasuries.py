# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A branch manager's money moves only through their own business's cash box or the group's wallets
# (imederp/treasuries.py, owner's decision of 8 Oct 2026): on a purchase paid on the spot and on a sale paid at
# the counter too, not only on journal and payment entries. Real items, stores and accounts; rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_treasuries

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

# A test module outside a doctype folder builds no "_Test ..." records, so it needs (and may have) no
# IGNORE_TEST_RECORD_DEPENDENCIES; keep it here, not under a doctype.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
SARA = "sara@imed.local"
AZARITA = f"مكتبة الأزاريطة - {ABBR}"
AZARITA_STORE = f"خامات الأزاريطة - {ABBR}"
AZARITA_CASH = f"خزينة مكتبة الأزاريطة - {ABBR}"
MAIN_TREASURY = f"الخزينة الرئيسية - {ABBR}"
MAWASAH_CASH = f"خزينة مكتبة المواساة - {ABBR}"


class IntegrationTestTreasuries(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "_Test Treasury Supplier",
				"supplier_group": frappe.get_all("Supplier Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
			}
		).insert().name
		cls.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test Treasury Customer",
				"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0],
			}
		).insert().name

	def tearDown(self):
		frappe.set_user("Administrator")

	def purchase_paid_from(self, treasury):
		return frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": COMPANY,
				"supplier": self.supplier,
				"posting_date": today(),
				"update_stock": 1,
				"set_warehouse": AZARITA_STORE,
				"cost_center": AZARITA,
				"is_paid": 1,
				"mode_of_payment": "Cash",
				"cash_bank_account": treasury,
				"paid_amount": 650,
				"items": [
					{"item_code": "A4-PAPER", "qty": 1, "uom": "كرتونة", "rate": 650, "warehouse": AZARITA_STORE, "cost_center": AZARITA}
				],
			}
		)

	def sale_paid_by(self, mode):
		return frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": self.customer,
				"posting_date": today(),
				"cost_center": AZARITA,
				"is_pos": 1,
				"items": [{"item_code": "BINDING-SVC", "qty": 1, "rate": 20, "cost_center": AZARITA}],
				"payments": [{"mode_of_payment": mode, "amount": 20}],
			}
		)

	def test_branch_manager_pays_a_purchase_only_from_her_cash_box(self):
		frappe.set_user(SARA)
		for treasury in (MAIN_TREASURY, MAWASAH_CASH):
			with self.subTest(treasury):
				self.assertRaisesRegex(frappe.ValidationError, "not your business's treasury", self.purchase_paid_from(treasury).insert)
		self.purchase_paid_from(AZARITA_CASH).insert()

	def test_branch_manager_takes_a_sale_only_into_her_cash_box(self):
		frappe.set_user(SARA)
		self.assertRaisesRegex(frappe.ValidationError, "not your business's treasury", self.sale_paid_by("نقدي — مكتبة المواساة").insert)
		for mode in ("نقدي — مكتبة الأزاريطة", "InstaPay"):
			with self.subTest(mode):
				self.sale_paid_by(mode).insert()

	def test_the_accountant_pays_from_any_treasury(self):
		frappe.set_user("accountant@imed.local")
		self.purchase_paid_from(MAIN_TREASURY).insert()

	def test_every_money_document_checks_the_treasury(self):
		events = frappe.get_hooks("doc_events", app_name="imed_erp")
		for doctype in ("Journal Entry", "Payment Entry", "Purchase Invoice", "Sales Invoice", "POS Invoice"):
			with self.subTest(doctype):
				self.assertIn("imed_erp.imederp.treasuries.check_entry_treasuries", events[doctype]["validate"])
