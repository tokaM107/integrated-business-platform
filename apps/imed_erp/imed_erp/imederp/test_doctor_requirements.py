# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The doctors' requirements left after the statement (the dues and debts reports are Eman's, test_doctor_reports):
# the doctor's agreements on his file (DOC-29), his statement sent after a settlement (DOC-23), old editions not
# fully sold (DOC-21) and the owner's share planned against what the sales brought (DOC-27). Real stores and
# accounts; rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_doctor_requirements

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp.testing import ledger_entry
from imed_erp.imederp import test_edition_sales
from imed_erp.imederp.doctype.book_edition.test_book_edition import PAPER_COST, make_agreement
from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import get_doctor_summary
from imed_erp.imederp.report.owner_share_plan_vs_actual.owner_share_plan_vs_actual import execute as owner_share
from imed_erp.imederp.report.unsold_editions.unsold_editions import execute as unsold
from imed_erp.imederp.test_edition_sales import COMPANY, EDITIONS, MAWASAH, RAGHAD
from imed_erp.imederp.testing import fund_cash_boxes

LEDGER = "Doctor Ledger Entry"
TREASURY = "الخزينة الرئيسية - MMG"
ACCOUNTANT = "accountant@imed.local"


class IntegrationTestDoctorReports(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# A payout leaves a cash box: the box holds the cash first (cash_balance.py).
		fund_cash_boxes()
		helpers = test_edition_sales.IntegrationTestEditionSales
		cls.items = [helpers.make_item(f"_Test Reports Book {n}") for n in (1, 2)]
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
				"customer_name": "_Test Reports Buyer",
				"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0],
			}
		).insert().name
		cls.term1 = helpers.make_period("_Test Reports Term 1", "2026-01-01", "2026-06-30")
		cls.term2 = helpers.make_period("_Test Reports Term 2", "2026-07-01", "2026-12-31")
		cls.agreement = make_agreement("Books", 80)
		cls.doctor = frappe.db.get_value("Doctor Agreement", cls.agreement, "doctor")

	def setUp(self):
		frappe.db.savepoint("reports_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="reports_test")

	@patch(PAPER_COST, return_value=0.30)
	def edition(self, _, item=None, period=None, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Book Edition",
				"edition_name": f"_Test Reports Edition {frappe.generate_hash(length=6)}",
				"agreement": self.agreement,
				"item_code": item or self.items[0],
				"cost_center": MAWASAH,
				"edition_date": "2026-03-01",
				"period": period or self.term2,
				"pages": 100,
				"doctor_qty": 50,
				"extra_qty": 10,
				**values,
			}
		).insert()
		doc.submit()
		return doc

	def sell(self, item, qty, rate=200):
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": self.customer,
				"cost_center": MAWASAH,
				"update_stock": 1,
				"set_warehouse": EDITIONS,
				"items": [{"item_code": item, "qty": qty, "rate": rate, "warehouse": EDITIONS, "cost_center": MAWASAH}],
			}
		).insert()
		invoice.submit()
		return invoice

	def entry(self, entry_type, amount, **values):
		doc = frappe.get_doc(
			ledger_entry({"agreement": self.agreement, "entry_type": entry_type, "amount": amount, "entry_date": today(), **values})
		).insert()
		doc.submit()
		return doc

	# ---------- DOC-29: the doctor's file ----------

	def test_the_doctor_s_file_lists_his_agreements_apart(self):
		app = make_agreement("App", 0)
		frappe.db.set_value("Doctor Agreement", app, "doctor", self.doctor)
		self.entry("Accrual", 100)
		summary = {row["agreement"]: row for row in get_doctor_summary(self.doctor)}
		self.assertEqual(summary[self.agreement]["direction"], "Owed to Doctor")
		self.assertFalse(summary[self.agreement]["owed_by_doctor"])
		self.assertEqual(summary[app]["agreement_type"], "App")
		# A branch manager adding a customer sees none of it.
		frappe.set_user(RAGHAD)
		self.assertEqual(get_doctor_summary(self.doctor), [])

	def test_a_doctor_below_zero_shows_as_owing(self):
		balance = flt(frappe.db.get_value("Doctor Agreement", self.agreement, "balance"))
		# A deduction by hand, approved: the only way a books doctor goes below zero (owner, 21 Oct 2026).
		self.entry("Adjustment", -(balance + 50))
		[row] = [row for row in get_doctor_summary(self.doctor) if row["agreement"] == self.agreement]
		self.assertEqual((row["balance"], row["direction"], row["owed_by_doctor"]), (50, "Owed by Doctor", True))

	# ---------- DOC-23: the statement goes to the doctor ----------

	def test_a_settlement_sends_the_doctor_his_statement(self):
		frappe.db.set_value("Customer", self.doctor, "email_id", "doctor@example.com")
		self.entry("Accrual", 500, period=self.term2)
		with patch("frappe.sendmail") as sendmail:
			self.entry("Payout", 100, period=self.term2, treasury=TREASURY)
		[call] = sendmail.call_args_list
		self.assertEqual((call.kwargs["recipients"], call.kwargs["reference_name"]), (["doctor@example.com"], self.agreement))
		self.assertIn(self.term2, call.kwargs["subject"])
		self.assertIn("Balance at the End of the Period", call.kwargs["message"])

		# Sales do not send one each.
		self.edition()
		with patch("frappe.sendmail") as sendmail:
			self.sell(self.items[0], 1)
		sendmail.assert_not_called()

	def test_with_no_email_on_file_the_accountant_is_told(self):
		frappe.db.set_value("Customer", self.doctor, "email_id", None)
		self.entry("Accrual", 500, period=self.term2)
		with patch("frappe.sendmail") as sendmail:
			self.entry("Payout", 100, period=self.term2, treasury=TREASURY)
		sendmail.assert_not_called()
		self.assertTrue(
			frappe.db.exists("Notification Log", {"for_user": ACCOUNTANT, "subject": ["like", "%no email on file%"]})
		)

	# ---------- DOC-21: old editions not fully sold ----------

	def test_old_editions_with_copies_left_are_listed_before_the_next_module(self):
		old = self.edition(period=self.term1, doctor_qty=10, extra_qty=5)
		self.sell(self.items[0], 12)
		current = self.edition(item=self.items[1])
		rows = {row["edition"]: row for row in unsold({"before": today()})[1]}
		self.assertEqual(
			(rows[old.name]["remaining_qty"], rows[old.name]["doctor_left"], rows[old.name]["library_left"]), (3, 0, 3)
		)
		self.assertNotIn(current.name, rows)
		# Carried forward to the current term, it is not old any more.
		from imed_erp.imederp.doctype.book_edition.book_edition import carry_forward

		carry_forward(old.name, self.term2)
		self.assertNotIn(old.name, {row["edition"] for row in unsold({"before": today()})[1]})

	# ---------- DOC-27: the owner's share planned and actual ----------

	def test_owner_share_planned_against_actual(self):
		# Sold at 20 over the calculated price (set by hand) and once at a 30 discount: the owner's share differs
		# from the plan by exactly that.
		edition = self.edition()
		price = flt(edition.calculated_price)
		self.sell(self.items[0], 3, rate=price + 20)
		self.sell(self.items[0], 1, rate=price - 30)
		[row] = [row for row in owner_share({})[1] if row["edition"] == edition.name]
		planned_per_copy = flt(edition.owner_share) * edition.pages
		self.assertEqual(row["sold_qty"], 4)
		self.assertAlmostEqual(row["planned"], planned_per_copy * 4, places=2)
		self.assertAlmostEqual(row["difference"], 3 * 20 - 30, places=2)

	def test_no_email_account_does_not_stop_the_payout(self):
		# Found with the demo data: with no outgoing email account the payout failed; it goes through and the
		# accountant is told the statement was not sent.
		frappe.db.set_value("Customer", self.doctor, "email_id", "doctor@example.com")
		self.entry("Accrual", 500, period=self.term2)
		with patch("frappe.sendmail", side_effect=frappe.OutgoingEmailError("no account")):
			payout = self.entry("Payout", 100, period=self.term2, treasury=TREASURY)
		self.assertEqual(payout.docstatus, 1)
		self.assertTrue(
			frappe.db.exists("Notification Log", {"for_user": ACCOUNTANT, "subject": ["like", "%no outgoing email account%"]})
		)

