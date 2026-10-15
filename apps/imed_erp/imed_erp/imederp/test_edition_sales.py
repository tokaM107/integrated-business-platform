# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Edition quantities, the sales of each edition, carrying it forward and cancelling it when the curriculum
# changes (DOC-14..17; book_edition.py, imederp/edition_sales.py). Real stores and accounts; rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_edition_sales

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from imed_erp.imederp.doctype.book_edition.book_edition import (
	carry_forward,
	cancel_for_curriculum_change,
	update_sold_qty,
)
from imed_erp.imederp.doctype.book_edition.test_book_edition import PAPER_COST, make_agreement
from imed_erp.imederp.sales_cancellation import cancel_with_reason

# A test module outside a doctype folder builds no "_Test ..." records; keep it here, not under a doctype.
COMPANY = "Mohamed Mamdouh group"
MAWASAH = "مكتبة المواساة - MMG"
EDITIONS = "إصدارات الأطباء — المواساة - MMG"
RAGHAD = "raghad@imed.local"
SARA = "sara@imed.local"
HR = "hr@imed.local"
PRICING = ("paper_cost", "ink_cost", "overhead_cost", "owner_share", "binding_cost", "doctor_share", "selling_price")


class IntegrationTestEditionSales(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.items = [cls.make_item(f"_Test Edition Book {n}") for n in (1, 2)]
		receipt = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": COMPANY,
				"items": [{"item_code": item, "qty": 300, "basic_rate": 60, "t_warehouse": EDITIONS} for item in cls.items],
			}
		).insert()
		receipt.submit()
		cls.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test Edition Buyer",
				"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0],
			}
		).insert().name
		cls.term1 = cls.make_period("_Test Term 1", "2026-09-01", "2026-12-31")
		cls.term2 = cls.make_period("_Test Term 2", "2027-01-01", "2027-04-30")

	@staticmethod
	def make_item(code):
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{"doctype": "Item", "item_code": code, "item_name": code, "item_group": "كتب", "stock_uom": "Nos", "is_stock_item": 1}
			).insert()
		return code

	@staticmethod
	def make_period(name, start, end):
		return frappe.get_doc(
			{"doctype": "Academic Period", "period_name": name, "period_type": "Term", "start_date": start, "end_date": end}
		).insert().name

	def setUp(self):
		# Each test starts from the class's items and stock only: editions of the same item would otherwise pile up.
		frappe.db.savepoint("edition_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="edition_test")

	@patch(PAPER_COST, return_value=0.30)
	def edition(self, _, item=None, doctor_qty=100, extra_qty=20, submit=True, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Book Edition",
				"edition_name": f"_Test Edition {frappe.generate_hash(length=6)}",
				"agreement": make_agreement("Books", 80),
				"item_code": item or self.items[0],
				"cost_center": MAWASAH,
				"edition_date": "2026-09-15",
				"period": self.term1,
				"pages": 100,
				"doctor_qty": doctor_qty,
				"extra_qty": extra_qty,
				**values,
			}
		).insert()
		if submit:
			doc.submit()
		return doc

	def sell(self, rows, rate=150):
		"""A submitted sale of (item, qty[, edition]) rows at Mawasah, stock out of its editions store."""
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": self.customer,
				"cost_center": MAWASAH,
				"update_stock": 1,
				"set_warehouse": EDITIONS,
				"items": [
					{
						"item_code": row[0],
						"qty": row[1],
						"rate": rate,
						"warehouse": EDITIONS,
						"cost_center": MAWASAH,
						"book_edition": row[2] if len(row) > 2 else None,
					}
					for row in rows
				],
			}
		).insert()
		invoice.submit()
		return invoice

	def qty(self, edition):
		return frappe.db.get_value("Book Edition", edition.name, ["total_qty", "sold_qty", "remaining_qty"])

	# ---------- DOC-14: the doctor's and the library's copies ----------

	def test_a_new_edition_keeps_both_quantities_and_their_total(self):
		edition = self.edition(doctor_qty=100, extra_qty=20)
		reopened = frappe.get_doc("Book Edition", edition.name)
		self.assertEqual(
			(reopened.doctor_qty, reopened.extra_qty, reopened.total_qty, reopened.sold_qty, reopened.remaining_qty),
			(100, 20, 120, 0, 120),
		)
		self.assertEqual((reopened.status, reopened.docstatus, reopened.item_code), ("Active", 1, self.items[0]))

	def test_invalid_quantities_are_refused(self):
		self.assertRaisesRegex(frappe.ValidationError, "negative", self.edition, doctor_qty=-1, submit=False)
		self.assertRaisesRegex(frappe.ValidationError, "negative", self.edition, extra_qty=-5, submit=False)
		self.assertRaisesRegex(frappe.ValidationError, "copies to print", self.edition, doctor_qty=0, extra_qty=0)
		# Only the library's extra copies, or only the doctor's, is a valid edition.
		self.assertEqual(self.edition(doctor_qty=0, extra_qty=30).total_qty, 30)

	def test_quantities_and_status_cannot_be_changed_after_approval(self):
		edition = self.edition()
		edition.reload()
		edition.doctor_qty = 500
		self.assertRaises(frappe.ValidationError, edition.save)
		for field, value in (("status", "Cancelled"), ("carried_to_period", self.term2), ("notice_received_by", HR)):
			edition.reload()
			edition.set(field, value)
			self.assertRaisesRegex(frappe.ValidationError, "only through", edition.save)
		# Sold Qty is the sales' count: a value sent with a save is ignored, and a copy opened before a sale saves.
		edition.reload()
		self.sell([(self.items[0], 4)])
		edition.sold_qty = 99
		edition.save()
		self.assertEqual(self.qty(edition), (120, 4, 116))

	# ---------- The sales of an edition ----------

	def test_sales_name_their_edition_and_are_counted_once(self):
		edition = self.edition()
		first = self.sell([(self.items[0], 30)])
		self.assertEqual(first.items[0].book_edition, edition.name)
		self.sell([(self.items[0], 15), (self.items[0], 5)])
		self.assertEqual(self.qty(edition), (120, 50, 70))
		# Working it out again, as often as it happens, changes nothing.
		update_sold_qty(edition.name)
		update_sold_qty(edition.name)
		self.assertEqual(self.qty(edition), (120, 50, 70))
		# A cancelled sale stops counting; the invoice stays, with its edition.
		cancel_with_reason("Sales Invoice", first.name, "Test: wrong book")
		self.assertEqual(self.qty(edition), (120, 20, 100))
		self.assertEqual(frappe.db.get_value("Sales Invoice Item", {"parent": first.name}, "book_edition"), edition.name)

	def test_a_sale_never_goes_to_another_items_edition(self):
		edition = self.edition(item=self.items[0])
		other = self.edition(item=self.items[1])
		self.assertRaisesRegex(frappe.ValidationError, "is sold as", self.sell, [(self.items[1], 1, edition.name)])
		self.sell([(self.items[1], 4)])
		self.assertEqual(self.qty(other), (120, 4, 116))
		self.assertEqual(self.qty(edition), (120, 0, 120))

	def test_with_two_editions_on_sale_the_seller_chooses(self):
		old = self.edition()
		new = self.edition(edition_date="2026-10-01")
		self.assertRaisesRegex(frappe.ValidationError, "more than one edition", self.sell, [(self.items[0], 1)])
		self.sell([(self.items[0], 7, new.name)])
		self.assertEqual((self.qty(old)[1], self.qty(new)[1]), (0, 7))

	def test_an_edition_does_not_sell_more_than_it_has(self):
		edition = self.edition(doctor_qty=10, extra_qty=2)
		self.sell([(self.items[0], 10)])
		self.assertRaisesRegex(frappe.ValidationError, "2 copies left", self.sell, [(self.items[0], 3)])
		self.sell([(self.items[0], 2)])
		self.assertEqual(self.qty(edition), (12, 12, 0))

	def test_a_cancelled_editions_item_is_not_sold_without_an_edition(self):
		edition = self.edition()
		cancel_for_curriculum_change(edition.name, today())
		self.assertRaisesRegex(frappe.ValidationError, "no edition on sale", self.sell, [(self.items[0], 1)])

	def test_a_sale_saved_at_the_same_moment_asks_to_submit_again(self):
		"""MariaDB refuses the locking read when another sale changed the rows meanwhile; the seller is told to
		submit again rather than shown a database error, and nothing is sold."""
		edition = self.edition()
		with patch(
			"imed_erp.imederp.edition_sales.get_sold_qty", side_effect=frappe.QueryDeadlockError("1020")
		):
			self.assertRaisesRegex(frappe.ValidationError, "Submit this invoice again", self.sell, [(self.items[0], 1)])
		self.assertEqual(self.qty(edition), (120, 0, 120))

	def test_an_item_without_editions_sells_as_before(self):
		invoice = self.sell([(self.items[1], 1)])
		self.assertIsNone(invoice.items[0].book_edition)

	def test_an_edition_with_sales_is_not_cancelled_by_frappes_cancel(self):
		"""Cancelling the approval would leave its sales pointing at a cancelled edition; ERPNext's link check
		refuses it while a submitted invoice names it."""
		edition = self.edition()
		self.sell([(self.items[0], 1)])
		self.assertRaises(frappe.LinkExistsError, frappe.get_doc("Book Edition", edition.name).cancel)

	# ---------- The original cost (DOC-15, DOC-16) ----------

	def test_carrying_forward_keeps_the_approved_costs_and_sells_at_todays_price(self):
		edition = self.edition()
		approved = frappe.db.get_value("Book Edition", edition.name, PRICING)
		self.sell([(self.items[0], 20)], rate=150)
		frappe.set_user(RAGHAD)
		carry_forward(edition.name, self.term2)
		frappe.set_user("Administrator")

		carried = frappe.get_doc("Book Edition", edition.name)
		self.assertEqual(
			(carried.status, carried.carried_to_period, carried.carried_forward_by, carried.period),
			("Carried Forward", self.term2, RAGHAD, self.term1),
		)
		self.assertTrue(carried.carried_forward_on)
		self.assertEqual(frappe.db.get_value("Book Edition", edition.name, PRICING), approved)
		# Still on sale, at the price of the day of the sale (DOC-16), not the edition's.
		later = self.sell([(self.items[0], 5)], rate=175)
		self.assertEqual((later.items[0].book_edition, later.items[0].rate), (edition.name, 175))
		self.assertEqual(self.qty(edition), (120, 25, 95))
		# Carrying forward posts nothing to the doctor's account; only the sales do (imederp/doctor_accrual.py).
		self.assertFalse(frappe.db.exists("Doctor Ledger Entry", {"edition": edition.name, "sales_invoice": ["is", "not set"]}))

	def test_carry_forward_only_to_a_later_open_period(self):
		edition = self.edition()
		earlier = self.make_period("_Test Term 0", "2026-01-01", "2026-06-30")
		self.assertRaisesRegex(frappe.ValidationError, "later period", carry_forward, edition.name, earlier)
		self.assertRaisesRegex(frappe.ValidationError, "already in", carry_forward, edition.name, self.term1)
		frappe.db.set_value("Academic Period", self.term2, "is_closed", 1)
		self.assertRaisesRegex(frappe.ValidationError, "closed", carry_forward, edition.name, self.term2)
		frappe.db.set_value("Academic Period", self.term2, "is_closed", 0)
		sold_out = self.edition(item=self.items[1], doctor_qty=3, extra_qty=0)
		self.sell([(self.items[1], 3)])
		self.assertRaisesRegex(frappe.ValidationError, "nothing to carry", carry_forward, sold_out.name, self.term2)

	# ---------- DOC-17: cancelled because the curriculum changed ----------

	def test_cancel_for_a_curriculum_change_records_the_notice(self):
		edition = self.edition()
		sale = self.sell([(self.items[0], 30)])
		stock_entries = frappe.db.count("Stock Ledger Entry", {"voucher_no": sale.name})
		gl_entries = frappe.db.count("GL Entry", {"voucher_no": sale.name})

		frappe.set_user(RAGHAD)
		notice = add_days(today(), -2)
		with patch.object(frappe, "in_test", False):  # Frappe keeps no history while testing; keep it here.
			cancel_for_curriculum_change(edition.name, notice)
		frappe.set_user("Administrator")

		cancelled = frappe.get_doc("Book Edition", edition.name)
		self.assertEqual(
			(cancelled.status, cancelled.docstatus, getdate(cancelled.notice_date), cancelled.notice_received_by),
			("Cancelled", 1, getdate(notice), RAGHAD),
		)
		self.assertTrue(cancelled.cancellation_recorded_on)
		self.assertGreaterEqual(getdate(cancelled.cancellation_recorded_on), getdate(notice))
		# Its history stays: the sale, its stock and ledger entries, the copies sold; nothing is reversed or added.
		self.assertEqual(frappe.db.get_value("Sales Invoice", sale.name, "docstatus"), 1)
		self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": sale.name}), stock_entries)
		self.assertEqual(frappe.db.count("GL Entry", {"voucher_no": sale.name}), gl_entries)
		self.assertEqual(self.qty(edition), (120, 30, 90))
		# DOC-18/22: the doctor's 70 unsold copies (of his 100) are charged to him, as a draft waiting for approval;
		# the library's 20 extra are not.
		self.assertEqual(
			frappe.get_all(
				"Doctor Ledger Entry",
				filters={"edition": edition.name, "sales_invoice": ["is", "not set"]},
				fields=["entry_type", "qty", "docstatus", "approval_status"],
			),
			[{"entry_type": "Unsold Copies Charge", "qty": 70, "docstatus": 0, "approval_status": "Pending Approval"}],
		)
		version = frappe.get_all("Version", filters={"ref_doctype": "Book Edition", "docname": edition.name}, fields=["owner", "data"])
		self.assertTrue(any(v.owner == RAGHAD and "Cancelled" in v.data for v in version), version)
		# No more copies are sold, and it is not cancelled or carried forward twice.
		self.assertRaisesRegex(frappe.ValidationError, "no longer sold", self.sell, [(self.items[0], 1, edition.name)])
		self.assertRaisesRegex(frappe.ValidationError, "already cancelled", cancel_for_curriculum_change, edition.name, notice)
		self.assertRaisesRegex(frappe.ValidationError, "cancelled", carry_forward, edition.name, self.term2)

	def test_the_notice_date_is_required_and_real(self):
		edition = self.edition()
		self.assertRaisesRegex(frappe.ValidationError, "notice", cancel_for_curriculum_change, edition.name, None)
		self.assertRaisesRegex(frappe.ValidationError, "future", cancel_for_curriculum_change, edition.name, add_days(today(), 1))
		self.assertRaisesRegex(frappe.ValidationError, "before the edition date", cancel_for_curriculum_change, edition.name, "2026-09-01")
		self.assertEqual(frappe.db.get_value("Book Edition", edition.name, "status"), "Active")

	def test_a_draft_edition_has_no_actions(self):
		draft = self.edition(submit=False)
		self.assertRaisesRegex(frappe.ValidationError, "not approved", carry_forward, draft.name, self.term2)
		self.assertRaisesRegex(frappe.ValidationError, "not approved", cancel_for_curriculum_change, draft.name, today())
		self.assertRaisesRegex(frappe.ValidationError, "not approved", self.sell, [(self.items[0], 1, draft.name)])

	# ---------- Who ----------

	def test_only_the_editions_library_or_the_accounts_act_on_it(self):
		edition = self.edition()
		for user in (SARA, HR):
			frappe.set_user(user)
			self.assertRaises(frappe.PermissionError, carry_forward, edition.name, self.term2)
			self.assertRaises(frappe.PermissionError, cancel_for_curriculum_change, edition.name, today())
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Book Edition", edition.name, "status"), "Active")
