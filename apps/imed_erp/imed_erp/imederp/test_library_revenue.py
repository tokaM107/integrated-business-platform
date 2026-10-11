# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Each library's sales must land on its own revenue account without anyone changing it by hand.
# Uses the real items and accounts made by setup/setup_core.py and setup/setup_coa.py; rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_library_revenue

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
AZARITA = f"مكتبة الأزاريطة - {ABBR}"
MAWASAH = f"مكتبة المواساة - {ABBR}"
HALLS = f"قاعات Imed - {ABBR}"


class IntegrationTestLibraryRevenue(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.customer = (
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "Test Library Revenue Student",
					"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name")[0],
					"territory": frappe.get_all("Territory", filters={"is_group": 0}, pluck="name")[0],
				}
			)
			.insert()
			.name
		)

	def make_invoice(self, cost_center, item_code="PRINT-SVC"):
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": self.customer,
				"posting_date": nowdate(),
				"due_date": nowdate(),
				"cost_center": cost_center,
				"items": [{"item_code": item_code, "qty": 100, "rate": 1, "cost_center": cost_center}],
			}
		).insert()
		invoice.submit()
		return invoice

	def revenue_credited(self, invoice):
		"""Income account -> amount credited by the invoice."""
		return dict(
			frappe.db.sql(
				"""select gl.account, sum(gl.credit - gl.debit)
				from `tabGL Entry` gl join `tabAccount` acc on acc.name = gl.account
				where gl.voucher_no = %s and acc.root_type = 'Income' and gl.is_cancelled = 0
				group by gl.account""",
				invoice.name,
			)
		)

	def test_azarita_sale_goes_to_azarita_revenue(self):
		# The item's default is Mawasah revenue; selling it in Azarita must not leave it there.
		invoice = self.make_invoice(AZARITA)

		self.assertEqual(invoice.items[0].income_account, f"إيراد مكتبة الأزاريطة - {ABBR}")
		self.assertEqual(self.revenue_credited(invoice), {f"إيراد مكتبة الأزاريطة - {ABBR}": 100})

	def test_mawasah_sale_stays_on_mawasah_revenue(self):
		invoice = self.make_invoice(MAWASAH)

		self.assertEqual(self.revenue_credited(invoice), {f"إيراد مكتبة المواساة - {ABBR}": 100})

	def test_other_businesses_are_left_alone(self):
		# A hall hour is not a library sale; its own revenue account must not be touched.
		invoice = self.make_invoice(HALLS, item_code="HALL-HOUR")

		self.assertEqual(self.revenue_credited(invoice), {f"إيراد القاعات - {ABBR}": 100})

	def test_hall_cash_goes_to_the_centers_cash_box(self):
		# Cash for a hall goes to the center's cash box, not ERPNext's main "Cash" (CORE-03).
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": self.customer,
				"posting_date": nowdate(),
				"due_date": nowdate(),
				"cost_center": HALLS,
				"is_pos": 1,
				"items": [{"item_code": "HALL-HOUR", "qty": 1, "rate": 100, "cost_center": HALLS}],
				"payments": [{"mode_of_payment": "نقدي — قاعات Imed", "amount": 100}],
			}
		).insert()
		invoice.submit()

		entries = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": invoice.name, "account": f"خزينة سنتر Imed - {ABBR}", "is_cancelled": 0},
			fields=["debit", "credit"],
		)
		self.assertEqual(sum(e.debit - e.credit for e in entries), 100)

	def test_each_business_has_cash_into_its_own_cash_box(self):
		# Set up by setup/setup_library.py; the cash boxes are the ones in imederp/treasuries.py.
		from imed_erp.imederp.treasuries import BUSINESS_TREASURY

		for business in ("قاعات Imed", "استوديو X", "تطبيق BA Plus"):
			with self.subTest(business):
				account = frappe.db.get_value(
					"Mode of Payment Account",
					{"parent": f"نقدي — {business}", "company": COMPANY},
					"default_account",
				)
				self.assertEqual(account, f"{BUSINESS_TREASURY[business]} - {ABBR}")
