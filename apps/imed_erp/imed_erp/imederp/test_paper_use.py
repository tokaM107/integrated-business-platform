# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Printing and copying sold take their paper out of the library's store as cost of goods sold
# (imederp/paper_use.py), so a stock count finds only real losses. Real items, stores and accounts; rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_paper_use

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp.sales_cancellation import cancel_with_reason

# A test module outside a doctype folder builds no "_Test ..." records, so it needs (and may have) no
# IGNORE_TEST_RECORD_DEPENDENCIES; keep it here, not under a doctype.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
PAPER = "A4-PAPER"
MAWASAH = f"مكتبة المواساة - {ABBR}"
AZARITA = f"مكتبة الأزاريطة - {ABBR}"
MAWASAH_STORE = f"خامات المواساة - {ABBR}"
AZARITA_STORE = f"خامات الأزاريطة - {ABBR}"
COGS = f"تكلفة البضاعة المباعة - {ABBR}"
RAGHAD = "raghad@imed.local"


class IntegrationTestPaperUse(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test Printing Customer",
				"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0],
			}
		).insert().name

	def tearDown(self):
		frappe.set_user("Administrator")

	def receive(self, sheets, store=MAWASAH_STORE):
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": COMPANY,
				"items": [{"item_code": PAPER, "qty": sheets, "basic_rate": 0.26, "t_warehouse": store}],
			}
		).insert()
		entry.submit()

	def sheets(self, store=MAWASAH_STORE):
		return flt(frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": store}, "actual_qty"))

	def sell(self, rows, library=MAWASAH, user="Administrator"):
		"""A submitted sale of (item, qty) rows in `library`, paid in cash at its counter."""
		frappe.set_user(user)
		try:
			invoice = frappe.get_doc(
				{
					"doctype": "Sales Invoice",
					"company": COMPANY,
					"customer": self.customer,
					"posting_date": today(),
					"cost_center": library,
					"items": [{"item_code": item, "qty": qty, "rate": 1, "cost_center": library} for item, qty in rows],
				}
			).insert()
			invoice.submit()
			return invoice
		finally:
			frappe.set_user("Administrator")

	def cancel(self, invoice):
		# A sale is cancelled with its reason (imederp/sales_cancellation.py), as the Cancel button does.
		cancel_with_reason("Sales Invoice", invoice.name, "Test: sold by mistake")

	def issues(self, invoice):
		return frappe.get_all(
			"Stock Entry", filters={"sales_invoice_no": invoice.name}, fields=["name", "docstatus"], order_by="creation"
		)

	def test_printing_sold_takes_its_paper_as_cost_of_sales(self):
		self.receive(5000)
		before = self.sheets()
		invoice = self.sell([("PRINT-SVC", 300)], user=RAGHAD)
		self.assertEqual(self.sheets(), before - 300)

		[issue] = self.issues(invoice)
		self.assertEqual(issue.docstatus, 1)
		posted = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": issue.name, "account": COGS, "is_cancelled": 0},
			fields=["debit", "credit", "cost_center"],
		)
		rate = flt(frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": MAWASAH_STORE}, "valuation_rate"))
		self.assertAlmostEqual(sum(flt(g.debit) - flt(g.credit) for g in posted), 300 * rate, places=2)
		self.assertEqual({g.cost_center for g in posted}, {MAWASAH})

	def test_each_library_uses_its_own_paper(self):
		self.receive(1000, AZARITA_STORE)
		before = self.sheets(AZARITA_STORE), self.sheets()
		self.sell([("COPY-SVC", 40), ("PRINT-SVC", 10)], library=AZARITA)
		self.assertEqual((self.sheets(AZARITA_STORE), self.sheets()), (before[0] - 50, before[1]))

	def test_binding_takes_no_paper(self):
		self.receive(100)
		before = self.sheets()
		invoice = self.sell([("BINDING-SVC", 2)])
		self.assertEqual((self.sheets(), self.issues(invoice)), (before, []))

	def test_the_paper_goes_back_only_with_the_sale(self):
		self.receive(500)
		before = self.sheets()
		invoice = self.sell([("PRINT-SVC", 100)])
		[issue] = self.issues(invoice)
		self.assertRaisesRegex(frappe.ValidationError, "Cancel the invoice", frappe.get_doc("Stock Entry", issue.name).cancel)

		self.cancel(invoice)
		self.assertEqual(frappe.db.get_value("Stock Entry", issue.name, "docstatus"), 2)
		self.assertEqual(self.sheets(), before)

	def test_a_sale_beyond_the_paper_in_store_waits_for_the_accountant(self):
		# The sale stands; the issue is a draft until the missing paper is received or the count corrected.
		self.receive(10, AZARITA_STORE)
		before = self.sheets(AZARITA_STORE)
		invoice = self.sell([("PRINT-SVC", before + 50)], library=AZARITA)
		self.assertEqual(invoice.docstatus, 1)
		[issue] = self.issues(invoice)
		self.assertEqual(issue.docstatus, 0)
		self.assertEqual(self.sheets(AZARITA_STORE), before)
		# The accountant is told.
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": "accountant@imed.local", "document_name": issue.name}))

		# Once the paper arrives, the draft is submitted as it is, dated the day it is submitted.
		self.receive(500, AZARITA_STORE)
		draft = frappe.get_doc("Stock Entry", issue.name)
		draft.submit()
		self.assertEqual(self.sheets(AZARITA_STORE), before + 500 - (before + 50))

	def test_a_sale_beyond_the_paper_left_as_draft_goes_with_the_sale(self):
		self.receive(10, AZARITA_STORE)
		before = self.sheets(AZARITA_STORE)
		invoice = self.sell([("PRINT-SVC", before + 50)], library=AZARITA)
		[issue] = self.issues(invoice)
		self.assertEqual(issue.docstatus, 0)

		# Cancelling the sale removes the draft issue.
		self.cancel(invoice)
		self.assertEqual(self.issues(invoice), [])

	def test_a_count_after_printing_finds_no_shortage(self):
		# Before: the sheets printed showed up as a shortage at the next count. Now the store already shows them used.
		self.receive(5000)
		self.sell([("PRINT-SVC", 1200)], user=RAGHAD)
		frappe.set_user(RAGHAD)
		count = frappe.get_doc(
			{"doctype": "Stock Count", "store": MAWASAH_STORE, "items": [{"item_code": PAPER, "counted_qty": self.sheets()}]}
		).insert()
		self.assertEqual(count.items[0].difference_qty, 0)

	def test_sales_invoice_keeps_all_its_hooks(self):
		events = frappe.get_hooks("doc_events", app_name="imed_erp")
		self.assertIn("imed_erp.imederp.paper_use.issue_paper_used", events["Sales Invoice"]["on_submit"])
		self.assertIn("imed_erp.imederp.stock_reorder.alert_on_reorder_level", events["Sales Invoice"]["on_submit"])
		self.assertIn("imed_erp.imederp.paper_use.cancel_paper_used", events["Sales Invoice"]["on_cancel"])
		self.assertIn("imed_erp.imederp.paper_use.block_cancel_of_paper_issue", events["Stock Entry"]["before_cancel"])

	def test_a_branch_manager_sells_services_from_the_desk(self):
		# Services carry no warehouse, so Sara's User Permissions (her branch's stores only) do not stop her.
		self.receive(100, AZARITA_STORE)
		invoice = self.sell([("COPY-SVC", 5), ("BINDING-SVC", 1)], library=AZARITA, user="sara@imed.local")
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual({row.warehouse for row in invoice.items}, {None})

	def test_the_sellers_session_is_kept(self):
		# Inside a web request the session's sid and data are the person's browser session. The paper is issued
		# in the system's name, and her session must come back exactly as it was (frappe.set_user alone wipes
		# them, which logged her out after the request).
		self.receive(500)
		frappe.set_user(RAGHAD)
		session = frappe.local.session
		session.sid, session.data = "browser-session-id", frappe._dict(csrf_token="token", user=RAGHAD)
		data = session.data
		frappe.local.form_dict = frappe._dict(cmd="frappe.client.submit")
		try:
			invoice = frappe.get_doc(
				{
					"doctype": "Sales Invoice",
					"company": COMPANY,
					"customer": self.customer,
					"posting_date": today(),
					"cost_center": MAWASAH,
					"items": [{"item_code": "PRINT-SVC", "qty": 10, "rate": 1, "cost_center": MAWASAH}],
				}
			).insert()
			invoice.submit()
			self.assertEqual([i.docstatus for i in self.issues(invoice)], [1])
			self.assertEqual((frappe.session.user, session.sid), (RAGHAD, "browser-session-id"))
			self.assertIs(session.data, data)
			self.assertEqual(session.data.csrf_token, "token")
			self.assertEqual(frappe.local.form_dict.cmd, "frappe.client.submit")
		finally:
			frappe.set_user("Administrator")

	def test_the_cancel_button_cancels_the_invoice_and_its_paper(self):
		# The form's Cancel first lists submitted documents linked to the invoice, minus the doctypes it is told
		# to skip (sales_invoice.js adds Stock Entry to ERPNext's list). The paper issue is skipped there and
		# goes back with the invoice.
		from frappe.desk.form.linked_with import get_submitted_linked_docs

		self.receive(500)
		before = self.sheets()
		invoice = self.sell([("PRINT-SVC", 100)])
		skipped = ["Journal Entry", "Payment Entry", "Serial and Batch Bundle", "Stock Entry"]
		linked = get_submitted_linked_docs("Sales Invoice", invoice.name, ignore_doctypes_on_cancel_all=skipped)
		self.assertNotIn("Stock Entry", [d["doctype"] for d in linked.get("docs", [])])
		self.cancel(invoice)
		self.assertEqual(self.sheets(), before)
