# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The doctor's amount on every copy sold goes to his ledger (DOC-07, LIB-05; imederp/doctor_accrual.py): one entry
# per invoice line, never twice, cancelled with the sale and taken back by a credit note; in the accounts, Dr
# حصة الأطباء / Cr مستحقات للأطباء — الكتب on the library's cost center. The edition's Sold Qty follows the same
# sales (imederp/edition_sales.py), at the desk and at the point of sale. The daily job catches what the hooks
# missed (imported sales). Real stores and accounts; rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_doctor_accrual

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate, now_datetime, nowdate

from imed_erp.imederp import doctor_accrual
from imed_erp.imederp.doctor_accrual import accrue, missed_sales, run_daily
from imed_erp.imederp.doctype.book_edition.test_book_edition import PAPER_COST, make_agreement
from imed_erp.imederp.sales_cancellation import cancel_with_reason
from imed_erp.imederp import test_edition_sales
from imed_erp.imederp.test_edition_sales import COMPANY, EDITIONS, MAWASAH, RAGHAD

LEDGER = "Doctor Ledger Entry"
POS_PROFILE = "نقطة بيع مكتبة المواساة"
EXPENSE = "حصة الأطباء - MMG"
PAYABLE = "مستحقات للأطباء — الكتب - MMG"


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
			fields=["name", "journal_entry", "agreement", "period", "entry_type", "edition", "qty", "amount", "invoice_item", "entry_date"],
			order_by="creation",
		)

	def gl(self, journal_entry):
		"""(account, cost center, party, debit, credit) of the journal entry's ledger lines, if submitted."""
		return sorted(
			(g.account, g.cost_center, g.party, g.debit, g.credit)
			for g in frappe.get_all(
				"GL Entry",
				filters={"voucher_type": "Journal Entry", "voucher_no": journal_entry, "is_cancelled": 0},
				fields=["account", "cost_center", "party", "debit", "credit"],
			)
		)

	def net(self, journal_entry):
		"""Debit minus credit per account over all the journal entry's GL lines, the reversing ones too."""
		net = {}
		for g in frappe.get_all("GL Entry", filters={"voucher_no": journal_entry}, fields=["account", "debit", "credit"]):
			net[g.account] = net.get(g.account, 0) + flt(g.debit) - flt(g.credit)
		return net

	def sold(self, edition):
		return frappe.db.get_value("Book Edition", edition.name, ["sold_qty", "remaining_qty"])

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
		# In the accounts: the doctors' share is a cost of the library that sold, owed to this doctor.
		self.assertEqual(
			self.gl(entry.journal_entry),
			[(EXPENSE, MAWASAH, None, 240, 0), (PAYABLE, MAWASAH, None, 0, 240)],
		)

	def test_counting_an_invoice_again_adds_nothing(self):
		edition = self.edition()
		before = self.balance(edition.agreement)
		sale = self.sell([(self.items[0], 3)])
		accrue(frappe.get_doc("Sales Invoice", sale.name))
		accrue(frappe.get_doc("Sales Invoice", sale.name))
		self.assertEqual([e.amount for e in self.entries(sale.name)], [240])
		self.assertEqual(self.balance(edition.agreement) - before, 240)
		self.assertEqual(frappe.db.count("Journal Entry", {"user_remark": ["like", f"%{sale.name}%"], "docstatus": 1}), 1)

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
		# One journal entry for the sale, with a debit and a credit for each line.
		[journal_entry] = {e.journal_entry for e in self.entries(sale.name)}
		self.assertEqual(
			[(g[0], g[3], g[4]) for g in self.gl(journal_entry)],
			[(EXPENSE, 80, 0), (EXPENSE, 160, 0), (EXPENSE, 280, 0), (PAYABLE, 0, 80), (PAYABLE, 0, 160), (PAYABLE, 0, 280)],
		)

	def test_a_cancelled_sale_takes_its_amount_back(self):
		edition = self.edition()
		before = self.balance(edition.agreement)
		sale = self.sell([(self.items[0], 3)])
		[entry] = self.entries(sale.name)
		self.assertEqual(self.sold(edition), (3, 47))
		cancel_with_reason("Sales Invoice", sale.name, "Test: wrong copies")
		self.assertEqual(self.sold(edition), (0, 50))
		self.assertEqual(frappe.db.get_value(LEDGER, entry.name, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Journal Entry", entry.journal_entry, "docstatus"), 2)
		self.assertEqual(self.gl(entry.journal_entry), [])
		# ERPNext reverses the journal entry: each line is matched by one the other way round.
		self.assertEqual(self.net(entry.journal_entry), {EXPENSE: 0, PAYABLE: 0})
		self.assertEqual(frappe.db.count("GL Entry", {"voucher_no": entry.journal_entry}), 4)
		self.assertEqual(self.balance(edition.agreement), before)

	def test_what_a_sale_posted_goes_only_with_the_sale(self):
		edition = self.edition()
		sale = self.sell([(self.items[0], 3)])
		[entry] = self.entries(sale.name)
		for doctype, name in ((LEDGER, entry.name), ("Journal Entry", entry.journal_entry)):
			with self.subTest(doctype):
				self.assertRaisesRegex(frappe.ValidationError, "Cancel the invoice instead", frappe.get_doc(doctype, name).cancel)
				self.assertEqual(frappe.db.get_value(doctype, name, "docstatus"), 1)

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
		self.assertEqual(
			self.gl(entry.journal_entry),
			[(EXPENSE, MAWASAH, None, 0, 80), (PAYABLE, MAWASAH, None, 80, 0)],
		)
		self.assertEqual(self.balance(edition.agreement) - before, 160)
		self.assertEqual(self.sold(edition), (2, 48))

		# Cancelling the credit note gives the copies back to the sale: 240 owed again.
		cancel_with_reason("Sales Invoice", credit.name, "Test: return made by mistake")
		self.assertEqual(frappe.db.get_value("Journal Entry", entry.journal_entry, "docstatus"), 2)
		self.assertEqual(self.net(entry.journal_entry), {EXPENSE: 0, PAYABLE: 0})
		self.assertEqual(self.balance(edition.agreement) - before, 240)
		self.assertEqual(self.sold(edition), (3, 47))

	def test_a_branch_manager_s_sale_posts_to_the_ledger_she_cannot_read(self):
		edition = self.edition()
		frappe.set_user(RAGHAD)
		self.assertFalse(frappe.has_permission(LEDGER, "read"))
		sale = self.sell([(self.items[0], 2)])
		frappe.set_user("Administrator")
		[entry] = self.entries(sale.name)
		self.assertEqual((entry.amount, frappe.db.get_value("Journal Entry", entry.journal_entry, "docstatus")), (160, 1))

	def test_a_point_of_sale_sale_counts_too(self):
		# The till makes a Sales Invoice (POS Settings); the row takes the edition by itself, since the point of
		# sale cannot show the field.
		edition = self.edition()
		before = self.balance(edition.agreement)
		cashier = frappe.db.get_value("POS Profile User", {"parent": POS_PROFILE, "default": 1}, "user")
		frappe.get_doc(
			{
				"doctype": "POS Opening Entry",
				"company": COMPANY,
				"pos_profile": POS_PROFILE,
				"user": cashier,
				"period_start_date": now_datetime(),
				"posting_date": nowdate(),
				"balance_details": [{"mode_of_payment": "Cash", "opening_amount": 0}],
			}
		).insert().submit()
		sale = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": self.customer,
				"is_pos": 1,
				"pos_profile": POS_PROFILE,
				"items": [{"item_code": self.items[0], "qty": 2, "rate": 150}],
			}
		)
		sale.set_missing_values()
		sale.insert()
		sale.payments[0].amount = sale.grand_total
		sale.save()
		sale.submit()
		self.assertEqual(sale.items[0].book_edition, edition.name)
		self.assertEqual(self.sold(edition), (2, 48))
		[entry] = self.entries(sale.name)
		self.assertEqual(entry.amount, 160)
		self.assertEqual(self.balance(edition.agreement) - before, 160)
		self.assertEqual(self.gl(entry.journal_entry), [(EXPENSE, MAWASAH, None, 160, 0), (PAYABLE, MAWASAH, None, 0, 160)])

	# ---------- The daily safety net (run_daily) ----------

	def test_the_daily_job_counts_a_sale_the_hooks_missed(self):
		# An imported sale reaches the books without the submit hook.
		edition = self.edition()
		before = self.balance(edition.agreement)
		with patch.object(doctor_accrual, "accrue"):
			sale = self.sell([(self.items[0], 3)])
		self.assertEqual(self.entries(sale.name), [])
		self.assertIn(sale.name, missed_sales())

		run_daily()
		[entry] = self.entries(sale.name)
		self.assertEqual((entry.amount, entry.invoice_item), (240, sale.items[0].name))
		self.assertEqual(self.gl(entry.journal_entry), [(EXPENSE, MAWASAH, None, 240, 0), (PAYABLE, MAWASAH, None, 0, 240)])
		# Again, as often as it runs: the same key, nothing added.
		run_daily()
		self.assertEqual([e.name for e in self.entries(sale.name)], [entry.name])
		self.assertEqual(self.balance(edition.agreement) - before, 240)
		self.assertNotIn(sale.name, missed_sales())

	def test_the_daily_job_cancels_what_a_cancelled_sale_left(self):
		edition = self.edition()
		before = self.balance(edition.agreement)
		sale = self.sell([(self.items[0], 3)])
		[entry] = self.entries(sale.name)
		# ERPNext refuses to cancel a sale its entry still links to, so only an import that writes the invoice's
		# state straight to the database leaves one behind.
		frappe.db.set_value("Sales Invoice", sale.name, "docstatus", 2)
		self.assertEqual(frappe.db.get_value(LEDGER, entry.name, "docstatus"), 1)

		self.assertEqual(run_daily()[1], 1)
		self.assertEqual(frappe.db.get_value(LEDGER, entry.name, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Journal Entry", entry.journal_entry, "docstatus"), 2)
		self.assertEqual(self.balance(edition.agreement), before)
		self.assertEqual(run_daily()[1], 0)

	def test_one_bad_sale_does_not_stop_the_others(self):
		self.edition()
		with patch.object(doctor_accrual, "accrue"):
			bad, good = self.sell([(self.items[0], 1)]), self.sell([(self.items[0], 2)])
		post = doctor_accrual.post

		def fail_on_bad(doc, accruals):
			if doc.name == bad.name:
				raise frappe.ValidationError("_Test failure")
			return post(doc, accruals)

		with patch.object(doctor_accrual, "post", side_effect=fail_on_bad), patch.object(frappe, "log_error") as log:
			run_daily()
		self.assertEqual(self.entries(bad.name), [])
		self.assertEqual([e.amount for e in self.entries(good.name)], [160])
		self.assertIn(bad.name, log.call_args.kwargs["title"])
		# Nothing of the failed one is left half done; the next run counts it.
		self.assertFalse(frappe.db.exists("Journal Entry", {"user_remark": ["like", f"%{bad.name}%"]}))
		run_daily()
		self.assertEqual([e.amount for e in self.entries(bad.name)], [80])

	def test_an_edition_with_no_amount_is_not_looked_at_every_day(self):
		self.edition(amount_per_copy=0)
		sale = self.sell([(self.items[0], 1)])
		self.assertEqual(self.entries(sale.name), [])
		self.assertNotIn(sale.name, missed_sales())

