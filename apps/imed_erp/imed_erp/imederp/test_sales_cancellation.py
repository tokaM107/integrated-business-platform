# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A sale is cancelled only with its reason and only by those allowed to (ACC-06, SEC-03;
# imederp/sales_cancellation.py); the counter's receipt (SEC-06, MMG Sales Invoice). Real items, stores and
# accounts; rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_sales_cancellation

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp.sales_cancellation import REASON_FIELD, cancel_with_reason
from imed_erp.imederp.testing import fund_cash_boxes

# A test module outside a doctype folder builds no "_Test ..." records; keep it here, not under a doctype.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
MAWASAH = f"مكتبة المواساة - {ABBR}"
EDITIONS = f"إصدارات الأطباء — المواساة - {ABBR}"
POS_PROFILE = "نقطة بيع مكتبة المواساة"
CASH = "نقدي — مكتبة المواساة"
CASH_BOX = f"خزينة مكتبة المواساة - {ABBR}"
RAGHAD = "raghad@imed.local"
SARA = "sara@imed.local"
ACCOUNTANT = "accountant@imed.local"


class IntegrationTestSalesCancellation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Cancelling a cash sale takes its cash back out of the box (cash_balance.py): the box holds it first.
		fund_cash_boxes()
		cls.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test Cancellation Customer",
				"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0],
			}
		).insert().name
		receipt = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": COMPANY,
				# Enough for every test's sale of 2: the store holds nothing else on a clean site.
				"items": [{"item_code": "BOOK", "qty": 100, "basic_rate": 40, "t_warehouse": EDITIONS}],
			}
		).insert()
		receipt.submit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def sell(self, user=RAGHAD):
		"""A sale at Mawasah's counter, as the point of sale makes it: 2 books at 150 and 3 bindings at 5, paid in
		cash with 350 given, so 35 back."""
		frappe.set_user(user)
		try:
			invoice = frappe.get_doc(
				{
					"doctype": "Sales Invoice",
					"company": COMPANY,
					"customer": self.customer,
					"posting_date": today(),
					"is_pos": 1,
					"pos_profile": POS_PROFILE,
					"update_stock": 1,
					"set_warehouse": EDITIONS,
					"cost_center": MAWASAH,
					"items": [
						{"item_code": "BOOK", "qty": 2, "rate": 150, "warehouse": EDITIONS, "cost_center": MAWASAH},
						{"item_code": "BINDING-SVC", "qty": 3, "rate": 5, "cost_center": MAWASAH},
					],
					"payments": [{"mode_of_payment": CASH, "amount": 350}],
				}
			)
			invoice.insert()
			invoice.submit()
			return invoice
		finally:
			frappe.set_user("Administrator")

	def books(self):
		return flt(frappe.db.get_value("Bin", {"item_code": "BOOK", "warehouse": EDITIONS}, "actual_qty"))

	def balance(self, account, invoice):
		return flt(
			frappe.db.sql(
				"select sum(debit - credit) from `tabGL Entry` where account=%s and voucher_no=%s", (account, invoice)
			)[0][0]
		)

	def test_the_sale_totals_and_posts(self):
		before = self.books()
		invoice = self.sell()
		self.assertEqual([flt(row.amount) for row in invoice.items], [300, 15])
		self.assertEqual(
			[flt(invoice.get(f)) for f in ("total", "grand_total", "paid_amount", "change_amount", "outstanding_amount")],
			[315, 315, 350, 35, 0],
		)
		self.assertEqual(self.books(), before - 2)
		self.assertEqual(self.balance(CASH_BOX, invoice.name), 315)

	def test_a_cancel_without_a_reason_is_refused(self):
		invoice = self.sell()
		self.assertRaisesRegex(frappe.ValidationError, "reason", frappe.get_doc("Sales Invoice", invoice.name).cancel)
		for blank in ("", "   "):
			self.assertRaises(frappe.ValidationError, cancel_with_reason, "Sales Invoice", invoice.name, blank)
		self.assertEqual(frappe.db.get_value("Sales Invoice", invoice.name, "docstatus"), 1)

	def test_a_cancel_with_its_reason_reverses_the_sale_and_keeps_the_reason(self):
		before = self.books()
		invoice = self.sell()
		frappe.set_user(ACCOUNTANT)
		# Frappe keeps no history while testing (Document.save: ignore_version = frappe.in_test); keep it here.
		with patch.object(frappe, "in_test", False):
			cancel_with_reason("Sales Invoice", invoice.name, "  Sold to the wrong customer  ")
		frappe.set_user("Administrator")

		self.assertEqual(
			frappe.db.get_value("Sales Invoice", invoice.name, ["docstatus", REASON_FIELD, "modified_by"]),
			(2, "Sold to the wrong customer", ACCOUNTANT),
		)
		# ERPNext's own reversal: the books are back in the store, the cash box and the revenue net to zero.
		self.assertEqual(self.books(), before)
		self.assertEqual(self.balance(CASH_BOX, invoice.name), 0)
		self.assertFalse(frappe.db.exists("GL Entry", {"voucher_no": invoice.name, "is_cancelled": 0}))
		# The history keeps who cancelled it and why (SEC-01).
		versions = frappe.get_all(
			"Version", filters={"ref_doctype": "Sales Invoice", "docname": invoice.name}, fields=["owner", "data"]
		)
		cancelled = [v for v in versions if '"docstatus",1,2' in v.data.replace(" ", "")]
		self.assertEqual(len(cancelled), 1, versions)
		self.assertEqual(cancelled[0].owner, ACCOUNTANT)
		self.assertIn("Sold to the wrong customer", cancelled[0].data)

	def test_an_amendment_starts_without_the_reason(self):
		invoice = self.sell()
		cancel_with_reason("Sales Invoice", invoice.name, "Wrong quantity")
		# The form's Amend copies the invoice without it (frappe.model.copy_doc); so does the server's copy.
		amended = frappe.copy_doc(frappe.get_doc("Sales Invoice", invoice.name), ignore_no_copy=False)
		amended.amended_from = invoice.name
		self.assertFalse(amended.get(REASON_FIELD))

	def test_a_branch_manager_cannot_cancel(self):
		invoice = self.sell()
		frappe.set_user(RAGHAD)
		self.assertRaises(frappe.PermissionError, cancel_with_reason, "Sales Invoice", invoice.name, "Mistake")
		doc = frappe.get_doc("Sales Invoice", invoice.name)
		doc.set(REASON_FIELD, "Mistake")
		self.assertRaises(frappe.PermissionError, doc.cancel)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Sales Invoice", invoice.name, ["docstatus", REASON_FIELD]), (1, None))

	# ---------- Returns (QA-04) ----------

	def make_return(self, invoice, user, reason=None):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		frappe.set_user(user)
		try:
			credit = make_sales_return(invoice.name)
			credit.return_reason = reason
			# The cash goes back out of the box, without the change given on the sale.
			credit.change_amount = credit.base_change_amount = 0
			for payment in credit.payments:
				payment.amount = payment.base_amount = credit.grand_total or -315
			credit.insert()
			credit.submit()
			return credit
		finally:
			frappe.set_user("Administrator")

	def test_qa04_a_branch_manager_cannot_return_a_sale(self):
		before = self.books()
		invoice = self.sell()
		self.assertRaisesRegex(frappe.PermissionError, "Only the owner or the accountant", self.make_return, invoice, RAGHAD, "Mistake")
		# Nothing was reversed: the books stay sold and the cash stays in the box.
		self.assertEqual(self.books(), before - 2)
		self.assertFalse(frappe.db.exists("Sales Invoice", {"return_against": invoice.name}))

	def test_qa04_a_return_needs_its_reason(self):
		invoice = self.sell()
		for blank in (None, "  ", "<b></b>"):
			with self.subTest(blank):
				self.assertRaisesRegex(frappe.ValidationError, "reason", self.make_return, invoice, ACCOUNTANT, blank)

	def test_qa04_the_accountant_returns_a_sale_with_its_reason(self):
		before = self.books()
		invoice = self.sell()
		credit = self.make_return(invoice, ACCOUNTANT, "  <i>Wrong book</i> given  ")
		self.assertEqual((credit.docstatus, credit.return_reason), (1, "Wrong book given"))
		self.assertEqual(self.books(), before)

	def test_another_branch_cannot_see_the_sale(self):
		invoice = self.sell()
		frappe.set_user(SARA)
		self.assertRaises(frappe.PermissionError, cancel_with_reason, "Sales Invoice", invoice.name, "Mistake")

	def test_only_a_submitted_sale_is_cancelled(self):
		frappe.set_user(RAGHAD)
		draft = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": self.customer,
				"cost_center": MAWASAH,
				"items": [{"item_code": "BINDING-SVC", "qty": 1, "rate": 5, "cost_center": MAWASAH}],
			}
		).insert()
		frappe.set_user("Administrator")
		self.assertRaises(frappe.ValidationError, cancel_with_reason, "Sales Invoice", draft.name, "Mistake")
		self.assertRaises(frappe.ValidationError, cancel_with_reason, "Payment Entry", "anything", "Mistake")

	def test_the_receipt_in_arabic(self):
		invoice = self.sell()
		frappe.local.lang = "ar"
		try:
			html = frappe.get_print("Sales Invoice", invoice.name, print_format="MMG Sales Invoice")
		finally:
			frappe.local.lang = "en"
		for text in (
			'dir="rtl"',
			"فاتورة مبيعات",
			invoice.name,
			"مكتبة المواساة",  # the branch
			"الكمية",
			"سعر الوحدة",
			"الإجمالي",
			"الدفع",
			CASH,
			"الباقي للعميل",
			"فقط ثلاثمائة و خمسة عشر جنيه مصري لا غير",
		):
			self.assertIn(text, html)
		for row in invoice.items:
			self.assertIn(row.item_name, html)

	def test_sec10_names_on_the_receipt_are_printed_as_text(self):
		# A value written without Frappe's cleaning (db_set, an import) must not run in the printed receipt.
		invoice = self.sell()
		frappe.db.set_value("Sales Invoice", invoice.name, "customer_name", '<img src=x onerror="alert(1)">Ali')
		html = frappe.get_print("Sales Invoice", invoice.name, print_format="MMG Sales Invoice")
		self.assertNotIn('<img src=x onerror="alert(1)">', html)
		self.assertIn("&lt;img src=x", html)

	def test_the_reason_is_kept_as_plain_text(self):
		invoice = self.sell()
		self.assertRaises(frappe.ValidationError, cancel_with_reason, "Sales Invoice", invoice.name, "<b> </b>")
		self.assertRaises(frappe.ValidationError, cancel_with_reason, "Sales Invoice", invoice.name, "x" * 1001)
		cancel_with_reason("Sales Invoice", invoice.name, '<img src=x onerror="alert(1)">Wrong <b>customer</b>')
		self.assertEqual(frappe.db.get_value("Sales Invoice", invoice.name, REASON_FIELD), "Wrong customer")
