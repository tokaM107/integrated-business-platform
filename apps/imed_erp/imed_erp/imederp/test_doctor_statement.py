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
from frappe.utils import today

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
		cls.term1 = helpers.make_period("_Test Statement Term 1", "2026-01-01", "2026-06-30")
		cls.term2 = helpers.make_period("_Test Statement Term 2", "2026-07-01", "2026-12-31")
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
				"edition_date": "2026-03-01",
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
		self.entry("Adjustment", 50, "2026-06-15", self.term1, "_Test from the first term")
		first, second = self.edition(), self.edition(item=self.items[1], selling_price=150)
		self.sell(self.items[0], 3)
		sale = self.sell(self.items[0], 2)
		self.sell(self.items[1], 1)
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		credit = make_sales_return(sale.name)
		credit.items[0].qty = -1
		credit.insert()
		credit.submit()
		# A payout entered with the period, and one entered without it but dated in the term.
		self.entry("Payout", 200, period=self.term2)
		self.entry("Payout", 30, "2026-09-02")

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
		# By date: the one of 2 September first.
		self.assertEqual([row.get("paid") for row in data if row.get("paid")], [30, 200])
		self.assertEqual(data[-1]["balance"], opening + 320 + 80 - 230)
		self.assertEqual(
			(summary["Balance Brought Forward"], summary["Owed"], summary["Paid / Deducted"]), (opening, 400, 230)
		)

		# The first term shows only its own entry, none of the second's.
		_columns, data, _summary = self.statement(self.term1)
		self.assertEqual([row["description"] for row in data[1:-1]], ["Adjustment — 15-06-2026 — _Test from the first term"])

	def test_the_cost_of_a_copy_leaves_out_the_library_s_side(self):
		# Paper 0.30 + ink + overheads per sheet x 100 sheets + binding; not the profit, the marketing, the doctor's
		# amount or a price set by hand.
		edition = self.edition(selling_price=999, marketing_cost=5)
		cost = (0.30 + edition.ink_cost + edition.overhead_cost) * 100 + edition.binding_cost
		self.assertAlmostEqual(get_copy_cost(edition), cost, places=2)
		self.assertTrue(edition.owner_share and edition.rounding_diff)
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
		# DOC-20: charged more than he earned, the doctor owes the group; the statement says so.
		before = self.opening()
		self.entry("Unsold Copies Charge", before + 100, period=self.term2)
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

	# ---------- The end of a term or module: unsold copies (DOC-18, DOC-22) ----------

	def close(self, period):
		doc = frappe.get_doc("Academic Period", period)
		doc.is_closed = 1
		doc.save()

	def charges(self, edition):
		return frappe.get_all(
			LEDGER,
			filters={"edition": edition.name, "entry_type": "Unsold Copies Charge", "docstatus": ["<", 2]},
			fields=["name", "docstatus", "period", "qty", "amount"],
		)

	def test_closing_the_term_charges_the_doctor_s_unsold_copies_as_a_draft(self):
		edition = self.edition()
		self.sell(self.items[0], 30)
		before = self.opening(), self.statement()[1][-1]["balance"]
		self.close(self.term2)

		[charge] = self.charges(edition)
		self.assertEqual(
			(charge.docstatus, charge.period, charge.qty, charge.amount),
			(0, self.term2, 20, round(20 * get_copy_cost(edition), 2)),
		)
		# Waiting for approval: nothing is taken from the doctor yet.
		self.assertEqual((self.opening(), self.statement()[1][-1]["balance"]), before)

		# The accountant or the owner approves it by submitting it.
		frappe.get_doc(LEDGER, charge.name).submit()
		self.assertEqual(self.statement()[1][-1]["balance"], before[1] - charge.amount)

	def test_the_library_s_extra_copies_are_not_charged(self):
		# 10 for the doctor and 20 more for the library: 5 sold leaves 5 of his; 15 sold leaves none.
		some = self.edition(doctor_qty=10, extra_qty=20)
		self.sell(self.items[0], 5)
		none = self.edition(item=self.items[1], doctor_qty=10, extra_qty=20)
		self.sell(self.items[1], 15)
		self.close(self.term2)
		self.assertEqual([c.qty for c in self.charges(some)], [5])
		self.assertEqual(self.charges(none), [])

	def test_closing_again_charges_nothing_more(self):
		edition = self.edition()
		self.close(self.term2)
		frappe.db.set_value("Academic Period", self.term2, "is_closed", 0)
		self.close(self.term2)
		self.assertEqual(len(self.charges(edition)), 1)

	def test_a_module_ends_with_its_term(self):
		round_ = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": "_Test Statement Round", "period_type": "Round",
				"parent_period": self.term2, "start_date": "2026-07-01", "end_date": "2026-12-31"}
		).insert().name
		module = frappe.get_doc(
			{"doctype": "Academic Period", "period_name": "_Test Statement Module", "period_type": "Module",
				"parent_period": round_, "start_date": "2026-07-01", "end_date": "2026-12-31"}
		).insert().name
		edition = self.edition(period=module)
		self.close(self.term2)
		self.assertEqual([c.period for c in self.charges(edition)], [module])

	def test_a_carried_forward_edition_ends_with_the_period_it_was_carried_to(self):
		edition = self.edition(period=self.term1)
		carry_forward(edition.name, self.term2)
		self.close(self.term1)
		self.assertEqual(self.charges(edition), [])
		self.close(self.term2)
		self.assertEqual([c.period for c in self.charges(edition)], [self.term2])

	def test_closing_a_term_is_the_accounts_job(self):
		# A branch manager neither closes the term nor approves a charge on a doctor.
		self.edition()
		frappe.set_user(RAGHAD)
		self.assertRaises(frappe.PermissionError, self.close, self.term2)
		self.assertFalse(frappe.has_permission(LEDGER, "submit"))

	def test_settling_a_closed_term(self):
		# The charge is approved and the doctor paid after the term is closed; nothing else goes into it.
		edition = self.edition()
		self.sell(self.items[0], 45)
		self.close(self.term2)
		[charge] = self.charges(edition)
		frappe.get_doc(LEDGER, charge.name).submit()
		self.entry("Payout", 100, period=self.term2)
		self.assertRaisesRegex(frappe.ValidationError, "is closed", self.entry, "Adjustment", 10, period=self.term2)

