# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The doctor's statement (DOC-08, DOC-13; report Doctor Statement): one agreement and one period, from the balance
# brought forward to the balance at the end, without the library's profit or a price set by hand. Closing a term or
# module charges the doctor's unsold copies at cost, as drafts to approve (DOC-18, DOC-22). Real stores and
# accounts; rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_doctor_statement

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp import test_edition_sales
from imed_erp.imederp.doctype.book_edition.book_edition import carry_forward, get_copy_cost
from imed_erp.imederp.doctype.book_edition.test_book_edition import PAPER_COST, make_agreement
from imed_erp.imederp.report.doctor_statement.doctor_statement import execute
from imed_erp.imederp.test_edition_sales import COMPANY, EDITIONS, MAWASAH, RAGHAD

LEDGER = "Doctor Ledger Entry"
TREASURY = "الخزينة الرئيسية - MMG"


class IntegrationTestDoctorStatement(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		helpers = test_edition_sales.IntegrationTestEditionSales
		cls.items = [helpers.make_item(f"_Test Statement Book {n}") for n in (1, 2)]
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
				"customer_name": "_Test Statement Buyer",
				"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0],
			}
		).insert().name
		# Today falls in the second term.
		# Inside the company's fiscal year (from 1 Sep 2026); nothing is posted outside it.
		cls.term1 = helpers.make_period("_Test Statement Term 1", "2026-09-01", "2026-09-30")
		cls.term2 = helpers.make_period("_Test Statement Term 2", "2026-10-01", "2026-12-31")
		cls.agreement = make_agreement("Books", 80)

	def setUp(self):
		frappe.db.savepoint("statement_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="statement_test")

	@patch(PAPER_COST, return_value=0.30)
	def edition(self, _, item=None, period=None, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Book Edition",
				"edition_name": f"_Test Statement Edition {frappe.generate_hash(length=6)}",
				"agreement": self.agreement,
				"item_code": item or self.items[0],
				"cost_center": MAWASAH,
				"edition_date": "2026-09-01",
				"period": period or self.term2,
				"pages": 100,
				"doctor_qty": 50,
				"extra_qty": 0,
				**values,
			}
		).insert()
		doc.submit()
		return doc

	def sell(self, item, qty):
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": self.customer,
				"cost_center": MAWASAH,
				"update_stock": 1,
				"set_warehouse": EDITIONS,
				"items": [{"item_code": item, "qty": qty, "rate": 200, "warehouse": EDITIONS, "cost_center": MAWASAH}],
			}
		).insert()
		invoice.submit()
		return invoice

	def entry(self, entry_type, amount, entry_date=None, period=None, remarks=None):
		doc = frappe.get_doc(
			{
				"doctype": LEDGER,
				"agreement": self.agreement,
				"entry_type": entry_type,
				"amount": amount,
				"entry_date": entry_date or today(),
				"period": period,
				"remarks": remarks,
				"treasury": TREASURY if entry_type == "Payout" else None,
			}
		).insert()
		doc.submit()
		return doc

	def statement(self, period=None):
		columns, data, _message, _chart, summary = execute({"agreement": self.agreement, "period": period or self.term2})
		return columns, data, {s["label"]: s["value"] for s in summary}

	def opening(self):
		# Whatever the shared test agreement already holds from before the second term.
		return self.statement()[1][0]["balance"]

	def test_a_term_from_the_balance_brought_forward_to_the_end(self):
		before = self.opening()
		self.entry("Adjustment", 50, "2026-09-15", self.term1, "_Test from the first term")
		first, second = self.edition(), self.edition(item=self.items[1], selling_price=150)
		self.sell(self.items[0], 3)
		sale = self.sell(self.items[0], 2)
		self.sell(self.items[1], 1)
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		credit = make_sales_return(sale.name)
		credit.return_reason = "_Test returned by the accountant"
		credit.items[0].qty = -1
		credit.insert()
		credit.submit()
		# A payout entered with the period, and one entered without it but dated in the term.
		self.entry("Payout", 200, period=self.term2)
		self.entry("Payout", 30, "2026-10-02")

		_columns, data, summary = self.statement()
		opening = before + 50
		self.assertEqual((data[0]["balance"], data[0]["is_total"]), (opening, 1))
		editions = {row["edition"]: row for row in data if row.get("sold_qty") is not None and row.get("selling_price")}
		self.assertEqual(
			{name: (r["sold_qty"], r["selling_price"], r["copy_cost"], r["doctor_share"], r["owed"]) for name, r in editions.items()},
			{
				first.name: (4, first.selling_price, get_copy_cost(first), 80, 320),
				second.name: (1, 150, get_copy_cost(second), 80, 80),
			},
		)
		# By date: the one of 2 October first.
		self.assertEqual([row.get("paid") for row in data if row.get("paid")], [30, 200])
		self.assertEqual(data[-1]["balance"], opening + 320 + 80 - 230)
		self.assertEqual(
			(summary["Balance Brought Forward"], summary["Owed"], summary["Paid / Deducted"]), (opening, 400, 230)
		)

		# The first term shows only its own entry, none of the second's.
		_columns, data, _summary = self.statement(self.term1)
		self.assertEqual([row["description"] for row in data[1:-1]], ["Adjustment — 15-09-2026 — _Test from the first term"])

	def test_qa01_a_settlement_of_the_last_term_recorded_in_this_one_is_brought_forward(self):
		# QA-01: earned in the first term, then paid out and adjusted in the first term's name after the second
		# had started. Both belong to the first term, so the second starts from what is left of it.
		before = self.opening()
		self.entry("Accrual", 1000, "2026-09-10", self.term1)
		self.entry("Payout", 700, "2026-10-10", self.term1)
		self.entry("Adjustment", -300, "2026-10-15", self.term1)
		self.entry("Accrual", 500, "2026-10-05", self.term2)

		_columns, data, summary = self.statement()
		self.assertEqual(summary["Balance Brought Forward"], before)
		self.assertEqual(data[-1]["balance"], before + 500)
		self.assertAlmostEqual(
			flt(frappe.db.get_value("Doctor Agreement", self.agreement, "balance")), data[-1]["balance"], places=2
		)
		# The first term's statement shows them as its own.
		self.assertEqual(self.statement(self.term1)[2]["Paid / Deducted"], 1000)

	def test_the_cost_of_a_copy_leaves_out_the_library_s_side(self):
		# DOC-11: paper 0.30 + ink per sheet x 100 sheets + binding (with the cover). Not the overheads per sheet
		# ("no other operating expense"), the profit, the marketing, the doctor's amount or a price set by hand.
		edition = self.edition(selling_price=999, marketing_cost=5)
		cost = (0.30 + edition.ink_cost) * 100 + edition.binding_cost
		self.assertAlmostEqual(get_copy_cost(edition), cost, places=2)
		self.assertTrue(edition.overhead_cost and edition.owner_share and edition.rounding_diff)
		columns = {c["fieldname"] for c in self.statement()[0]}
		self.assertFalse(columns & {"owner_share", "marketing_cost", "calculated_price", "rounding_diff"})

	def test_copies_carried_forward_are_on_the_statement_of_the_term_they_sell_in(self):
		edition = self.edition(period=self.term1)
		carry_forward(edition.name, self.term2)
		self.sell(self.items[0], 2)
		[entry] = frappe.get_all(LEDGER, filters={"edition": edition.name, "docstatus": 1}, fields=["period", "amount"])
		self.assertEqual((entry.period, entry.amount), (self.term2, 160))
		self.assertIn(edition.name, [row.get("edition") for row in self.statement()[1]])
		self.assertNotIn(edition.name, [row.get("edition") for row in self.statement(self.term1)[1]])

	def test_a_negative_balance_is_a_debt_the_doctor_owes(self):
		# DOC-20: a deduction by hand larger than what he earned leaves the doctor owing the group; the statement says
		# so. (He is never charged for unsold copies: owner, 21 Oct 2026.)
		before = self.opening()
		self.entry("Adjustment", -(before + 100), period=self.term2)
		_columns, data, summary = self.statement()
		self.assertEqual(data[-1]["balance"], -100)
		self.assertEqual(summary["Balance — Owed by Doctor"], 100)

	def test_each_agreement_on_its_own(self):
		other = make_agreement("Books", 70)
		frappe.get_doc(
			{"doctype": LEDGER, "agreement": other, "entry_type": "Accrual", "amount": 999, "entry_date": today(), "period": self.term2}
		).insert().submit()
		self.assertNotIn(999, [row.get("owed") for row in self.statement()[1]])

	def test_only_the_accounts_read_it(self):
		roles = {r.role for r in frappe.get_doc("Report", "Doctor Statement").roles}
		self.assertEqual(roles, {"System Manager", "Accounts Manager"})

	# ---------- The end of a term, carry forward and curriculum changes (owner, 21 Oct 2026) ----------
	#
	# The doctor bears nothing for copies left unsold. Curriculum unchanged: they stay in the store, are carried
	# forward and sold next year, earning the doctor his amount as they sell. Curriculum changed: the edition is
	# obsolete and its copies left are disposed of as scrap, a loss on the library, and sold by weight.

	def close(self, period):
		doc = frappe.get_doc("Academic Period", period)
		doc.is_closed = 1
		doc.save()

	def charges(self, edition):
		"""Entries on the doctor's account for the edition that no sale made: there must be none."""
		return frappe.get_all(LEDGER, filters={"edition": edition.name, "sales_invoice": ("is", "not set")}, pluck="name")

	def accrued(self, edition):
		return frappe.get_all(
			LEDGER, filters={"edition": edition.name, "docstatus": 1}, fields=["period", "qty", "amount"], order_by="creation"
		)

	def test_closing_a_term_charges_the_doctor_nothing(self):
		edition = self.edition()
		self.sell(self.items[0], 30)
		balance = self.statement()[1][-1]["balance"]
		self.close(self.term2)
		self.assertEqual(self.charges(edition), [])
		self.assertEqual(self.statement()[1][-1]["balance"], balance)
		self.assertFalse(
			frappe.db.exists("Notification Log", {"document_type": LEDGER, "subject": ("like", "%unsold copies%"), "creation": (">=", today())})
		)

	def test_qa03_unsold_copies_are_carried_forward_and_sold_next_year(self):
		# 50 for the doctor; 30 sell in the first term, which closes. The 20 left stay in the store, are carried
		# forward and 5 sell in the second term: the doctor earns his 80 on 35 copies and is charged nothing.
		edition = self.edition(period=self.term1)
		self.sell(self.items[0], 30)
		self.close(self.term1)
		carry_forward(edition.name, self.term2)
		self.sell(self.items[0], 5)
		self.close(self.term2)
		self.assertEqual(self.charges(edition), [])
		self.assertEqual(
			[(e.period, e.qty, e.amount) for e in self.accrued(edition)], [(self.term1, 30, 2400), (self.term2, 5, 400)]
		)
		edition.reload()
		self.assertEqual((edition.sold_qty, edition.disposed_qty, edition.remaining_qty, edition.status), (35, 0, 15, "Carried Forward"))

	def test_closing_a_term_is_the_accounts_job(self):
		# A branch manager neither closes the term nor approves a deduction from a doctor.
		self.edition()
		frappe.set_user(RAGHAD)
		self.assertRaises(frappe.PermissionError, self.close, self.term2)
		self.assertFalse(frappe.has_permission(LEDGER, "submit"))

	def test_settling_a_closed_term(self):
		# The doctor is paid after the term is closed; nothing else goes into it.
		self.edition()
		self.sell(self.items[0], 45)
		self.close(self.term2)
		self.entry("Payout", 100, period=self.term2)
		self.assertRaisesRegex(frappe.ValidationError, "is closed", self.entry, "Adjustment", 10, period=self.term2)

	# ---------- Checked against the requirements (v1.2) ----------

	def make_module(self, name="_Test Statement Module"):
		round_ = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": f"{name} Round", "period_type": "Round",
				"parent_period": self.term2, "start_date": "2026-10-01", "end_date": "2026-12-31"}
		).insert().name
		return frappe.get_doc(
			{"doctype": "Academic Period", "period_name": name, "period_type": "Module",
				"parent_period": round_, "start_date": "2026-10-01", "end_date": "2026-12-31"}
		).insert().name

	def test_qa03_a_curriculum_change_is_the_library_s_loss_and_sold_as_scrap(self):
		# 40 for the doctor and 15 for the library; 25 sell. The curriculum changes: Raghad records it and disposes of
		# the 30 left as scrap, which a buyer takes by weight. The doctor keeps what he earned on the 25 sold; the
		# copies' cost is the library's loss, the scrap money its revenue.
		from imed_erp.imederp.damaged_stock import SCRAP_BUYER
		from imed_erp.imederp.doctype.book_edition.book_edition import cancel_for_curriculum_change, dispose_as_scrap

		edition = self.edition(doctor_qty=40, extra_qty=15)
		self.sell(self.items[0], 25)
		balance = self.statement()[1][-1]["balance"]
		frappe.set_user(RAGHAD)
		self.assertRaisesRegex(frappe.ValidationError, "curriculum changed", dispose_as_scrap, edition.name)
		cancel_for_curriculum_change(edition.name, today())
		self.assertEqual(self.charges(edition), [])

		disposal = frappe.get_doc("Damaged Stock Entry", dispose_as_scrap(edition.name))
		self.assertEqual((disposal.docstatus, disposal.book_edition, disposal.items[0].qty), (0, edition.name, 30))
		disposal.submit()
		frappe.set_user("Administrator")
		disposal.reload()
		edition.reload()
		self.assertEqual((edition.sold_qty, edition.disposed_qty, edition.remaining_qty), (25, 30, 0))
		loss = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": disposal.loss_entry, "account": "الهالك والتالف - MMG", "is_cancelled": 0},
			fields=["cost_center", "debit"],
		)
		self.assertEqual([(g.cost_center, g.debit) for g in loss], [(MAWASAH, disposal.total_loss)])
		self.assertGreater(disposal.total_loss, 0)
		# The doctor's account is not touched, and the library cannot dispose of more than it has left.
		self.assertEqual(self.charges(edition), [])
		self.assertEqual(self.statement()[1][-1]["balance"], balance)
		self.assertRaisesRegex(frappe.ValidationError, "copies left", dispose_as_scrap, edition.name, 1)

		# Sold by weight: 12.5 kg at 3.40, the library's revenue.
		sale = frappe.get_doc(
			{
				"doctype": "Damaged Stock Sale",
				"posting_date": today(),
				"damaged_store": disposal.damaged_store,
				"customer": SCRAP_BUYER,
				"weight": 12.5,
				"rate": 3.4,
				"paid_in_cash": 1,
				"items": [{"item_code": self.items[0], "qty": 30, "damage_entry": disposal.name}],
			}
		).insert()
		sale.submit()
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", sale.sales_invoice, "grand_total")), 42.5)
		self.assertEqual(self.statement()[1][-1]["balance"], balance)

		# Cancelling the disposal puts the copies back on the edition (once its sale is cancelled).
		self.assertRaisesRegex(frappe.ValidationError, "Cancel the sale first", frappe.get_doc("Damaged Stock Entry", disposal.name).cancel)
		frappe.get_doc("Damaged Stock Sale", sale.name).cancel()
		frappe.get_doc("Damaged Stock Entry", disposal.name).cancel()
		edition.reload()
		self.assertEqual((edition.disposed_qty, edition.remaining_qty), (0, 30))

	def test_qa03_only_the_edition_s_own_copies_from_its_library_are_disposed(self):
		from imed_erp.imederp.doctype.book_edition.book_edition import cancel_for_curriculum_change, dispose_as_scrap

		edition = self.edition(doctor_qty=10)
		cancel_for_curriculum_change(edition.name, today())
		disposal = frappe.get_doc("Damaged Stock Entry", dispose_as_scrap(edition.name))
		disposal.items[0].qty = 11
		self.assertRaisesRegex(frappe.ValidationError, "copies left", disposal.save)
		disposal.reload()
		disposal.items[0].item_code = self.items[1]
		self.assertRaisesRegex(frappe.ValidationError, "lists its item", disposal.save)

	def test_a_term_s_statement_takes_in_its_modules(self):
		# Books settle by module (DOC-05): an edition of a module sells under the module, and shows on both its
		# module's statement and its term's.
		module = self.make_module()
		edition = self.edition(period=module)
		self.sell(self.items[0], 2)
		for period in (module, self.term2):
			with self.subTest(period):
				rows = [row for row in self.statement(period)[1] if row.get("edition") == edition.name]
				self.assertEqual([(row["sold_qty"], row["owed"]) for row in rows], [(2, 160)])

	def test_a_whole_term(self):
		"""One doctor's term from start to end, as the accountant would check it by hand (DOC-07..09, 13, 20):
		50 copies for the doctor and 10 for the library at 80 each; 30 sold, 2 returned, 300 paid out; the term
		closes and the copies left stay in the store, charged to nobody (owner, 21 Oct 2026)."""
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		before = self.statement()[1][-1]["balance"]
		edition = self.edition(doctor_qty=50, extra_qty=10)
		cost = get_copy_cost(edition)
		self.sell(self.items[0], 20)
		sale = self.sell(self.items[0], 10)
		credit = make_sales_return(sale.name)
		credit.return_reason = "_Test returned by the accountant"
		credit.items[0].qty = -2
		credit.insert()
		credit.submit()
		self.entry("Payout", 300, period=self.term2)
		self.close(self.term2)
		self.assertEqual(self.charges(edition), [])

		_columns, data, summary = self.statement()
		[sold] = [row for row in data if row.get("edition") == edition.name and row.get("selling_price")]
		self.assertEqual(
			(sold["sold_qty"], sold["copy_cost"], sold["doctor_share"], sold["owed"]),
			(28, cost, 80, 28 * 80),
		)
		expected = before + 28 * 80 - 300
		self.assertAlmostEqual(data[-1]["balance"], expected, places=2)
		self.assertAlmostEqual(flt(frappe.db.get_value("Doctor Agreement", self.agreement, "balance")), expected, places=2)
		# Below zero, it is a debt on the Doctor Debts report; above, nothing is listed there.
		from imed_erp.imederp.report.doctor_debts.doctor_debts import execute as debts

		listed = {row["agreement"]: row["debt"] for row in debts({"as_of": today()})[1]}
		if expected < 0:
			self.assertAlmostEqual(listed[self.agreement], -expected, places=2)
		else:
			self.assertNotIn(self.agreement, listed)

