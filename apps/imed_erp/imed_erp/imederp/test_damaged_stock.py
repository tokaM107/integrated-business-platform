# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Damaged stock and its sale by weight (LIB-09, PRN-07, DOC-19; imederp/damaged_stock.py).
# Uses the real stores, accounts, users and A4 paper made by the setup scripts; every test is rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_damaged_stock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate

from imed_erp.imederp.damaged_stock import SCRAP_BUYER

COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
MAWASAH_STORE = f"خامات المواساة - {ABBR}"
MAWASAH_EDITIONS = f"إصدارات الأطباء — المواساة - {ABBR}"
AZARITA_EDITIONS = f"إصدارات الأطباء — الأزاريطة - {ABBR}"
DAMAGED = f"التالف — المواساة - {ABBR}"
MAWASAH_LIBRARY = f"مكتبة المواساة - {ABBR}"
AZARITA_LIBRARY = f"مكتبة الأزاريطة - {ABBR}"
LOSS = f"الهالك والتالف - {ABBR}"
SCRAP_REVENUE = f"إيراد بيع التالف بالوزن - {ABBR}"
MAWASAH_CASH = f"خزينة مكتبة المواساة - {ABBR}"

PAPER = "A4-PAPER"
RAGHAD = "raghad@imed.local"
SARA = "sara@imed.local"
NOUR = "nour@imed.local"


def as_user(user, fn, *args, **kwargs):
	frappe.set_user(user)
	try:
		return fn(*args, **kwargs)
	finally:
		frappe.set_user("Administrator")


def qty(item, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty"))


def stock_value(item, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "stock_value"))


def gl(voucher_no):
	"""(account, cost center) -> debit - credit, for the voucher's live entries."""
	rows = frappe.get_all(
		"GL Entry",
		filters={"voucher_no": voucher_no, "is_cancelled": 0},
		fields=["account", "cost_center", "debit", "credit"],
	)
	out = {}
	for r in rows:
		key = (r.account, r.cost_center)
		out[key] = flt(out.get(key, 0) + flt(r.debit) - flt(r.credit), 2)
	return out


def receive(item, quantity, warehouse, rate):
	uom = frappe.db.get_value("Item", item, "stock_uom")
	doc = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"company": COMPANY,
			"stock_entry_type": "Material Receipt",
			"purpose": "Material Receipt",
			"items": [{"item_code": item, "qty": quantity, "uom": uom, "conversion_factor": 1, "t_warehouse": warehouse, "basic_rate": rate}],
		}
	).insert()
	doc.submit()


class IntegrationTestDamagedStock(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("damaged_stock_test")
		receive(PAPER, 5000, MAWASAH_STORE, 0.26)
		receive("BOOK", 10, AZARITA_EDITIONS, 50)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="damaged_stock_test")

	# ---------- helpers ----------
	def damage(self, rows=None, store=MAWASAH_STORE, user=RAGHAD, reason="مياه على الكراتين", submit=True):
		doc = frappe.get_doc(
			{
				"doctype": "Damaged Stock Entry",
				"posting_date": nowdate(),
				"source_store": store,
				"damaged_store": DAMAGED,
				"reason": reason,
				"items": rows or [{"item_code": PAPER, "qty": 1000}],
			}
		)
		as_user(user, doc.insert)
		if submit:
			as_user(user, doc.submit)
		return doc

	def sale(self, rows=None, weight=12.5, rate=3.4, user=RAGHAD, paid=1, submit=True):
		doc = frappe.get_doc(
			{
				"doctype": "Damaged Stock Sale",
				"posting_date": nowdate(),
				"damaged_store": DAMAGED,
				"customer": SCRAP_BUYER,
				"weight": weight,
				"rate": rate,
				"paid_in_cash": paid,
				"items": rows or [{"item_code": PAPER, "qty": 1000}],
			}
		)
		as_user(user, doc.insert)
		if submit:
			as_user(user, doc.submit)
		return doc

	def assert_refused(self, exc, fn, *args, **kwargs):
		"""The call fails and what it wrote is undone, as a failed request would be."""
		frappe.db.savepoint("refused")
		with self.assertRaises(exc):
			fn(*args, **kwargs)
		frappe.db.rollback(save_point="refused")
		frappe.set_user("Administrator")

	# ---------- 1, 3, 12: damage recorded, moved, loss on the library ----------
	def test_damage_is_a_loss_and_waits_in_the_damaged_store(self):
		rate_before = flt(frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": MAWASAH_STORE}, "valuation_rate"))
		doc = self.damage()
		doc.reload()
		self.assertEqual((doc.responsible, doc.owner, doc.branch), (RAGHAD, RAGHAD, MAWASAH_LIBRARY))
		self.assertEqual(qty(PAPER, MAWASAH_STORE), 4000)
		self.assertEqual(qty(PAPER, DAMAGED), 1000)
		# Kept in the damaged store at no value; the store it came from keeps its cost per sheet.
		self.assertEqual(stock_value(PAPER, DAMAGED), 0)
		self.assertEqual(flt(frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": MAWASAH_STORE}, "valuation_rate")), rate_before)
		# 1,000 sheets at 0.26: a loss of 260 on Mawasah's library.
		self.assertEqual(flt(doc.total_loss), 260)
		self.assertEqual(gl(doc.loss_entry).get((LOSS, MAWASAH_LIBRARY)), 260)
		self.assertEqual(sum(gl(doc.damaged_store_entry).values()), 0)
		# DOC-19: never charged to a doctor.
		self.assertFalse(frappe.db.exists("Doctor Ledger Entry", {"remarks": ["like", f"%{doc.name}%"]}))

	def test_azarita_damage_goes_to_the_damaged_store_as_azarita_loss(self):
		doc = self.damage([{"item_code": "BOOK", "qty": 2}], store=AZARITA_EDITIONS, user=SARA, reason="نسخ مبلولة في التخزين")
		self.assertEqual(qty("BOOK", AZARITA_EDITIONS), 8)
		self.assertEqual(qty("BOOK", DAMAGED), 2)
		self.assertEqual(gl(doc.loss_entry).get((LOSS, AZARITA_LIBRARY)), 100)

	# ---------- 2: missing or wrong data ----------
	def test_missing_or_wrong_data_is_refused(self):
		self.assert_refused(frappe.ValidationError, self.damage, reason="  ")
		self.assert_refused(frappe.ValidationError, self.damage, [{"item_code": PAPER, "qty": 0}])
		self.assert_refused(frappe.ValidationError, self.damage, [{"item_code": PAPER, "qty": 6000}])
		self.assert_refused(frappe.ValidationError, self.damage, [{"item_code": PAPER, "qty": 1}, {"item_code": PAPER, "qty": 2}])
		self.assert_refused(frappe.ValidationError, self.damage, store=DAMAGED, user="Administrator")
		self.assertEqual((qty(PAPER, MAWASAH_STORE), qty(PAPER, DAMAGED)), (5000, 0))

	# ---------- 4: never taken off twice ----------
	def test_damage_is_taken_off_once(self):
		doc = self.damage()
		frappe.db.savepoint("again")
		try:
			as_user(RAGHAD, frappe.get_doc("Damaged Stock Entry", doc.name).submit)
		except Exception:
			frappe.db.rollback(save_point="again")
		frappe.set_user("Administrator")
		self.assertEqual((qty(PAPER, MAWASAH_STORE), qty(PAPER, DAMAGED)), (4000, 1000))
		self.assertEqual(frappe.db.count("Stock Entry", {"remarks": ["like", f"%{doc.name}%"], "docstatus": 1}), 2)
		# Its stock entries are reversed only through the damage record.
		self.assert_refused(frappe.ValidationError, frappe.get_doc("Stock Entry", doc.loss_entry).cancel)

	def test_cancelling_the_damage_puts_everything_back(self):
		doc = self.damage()
		frappe.get_doc("Damaged Stock Entry", doc.name).cancel()
		self.assertEqual((qty(PAPER, MAWASAH_STORE), qty(PAPER, DAMAGED)), (5000, 0))
		self.assertEqual(gl(doc.loss_entry), {})

	# ---------- 5, 6, 7, 8: sale by weight ----------
	def test_sale_by_weight_posts_revenue_once(self):
		self.damage()
		sale = self.sale(weight=12.5, rate=3.4)
		sale.reload()
		self.assertEqual(flt(sale.amount), 42.5)
		self.assertEqual(qty(PAPER, DAMAGED), 0)
		self.assertEqual(qty(PAPER, MAWASAH_STORE), 4000)
		# Revenue through ERPNext's Sales Invoice, on Mawasah's library; the cash in its cash box.
		invoice = frappe.get_doc("Sales Invoice", sale.sales_invoice)
		self.assertEqual((invoice.docstatus, flt(invoice.grand_total), invoice.items[0].qty, invoice.items[0].uom), (1, 42.5, 12.5, "Kg"))
		self.assertEqual(gl(sale.sales_invoice).get((SCRAP_REVENUE, MAWASAH_LIBRARY)), -42.5)
		self.assertEqual(gl(sale.payment_entry).get((MAWASAH_CASH, MAWASAH_LIBRARY)), 42.5)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", sale.sales_invoice, "outstanding_amount")), 0)
		# The damaged items carried no cost, so taking them out posts none.
		self.assertFalse(any(gl(sale.stock_entry).values()))

		# Submitted again (a second click): no second invoice, no second revenue.
		frappe.db.savepoint("again")
		try:
			as_user(RAGHAD, frappe.get_doc("Damaged Stock Sale", sale.name).submit)
		except Exception:
			frappe.db.rollback(save_point="again")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Sales Invoice", {"remarks": ["like", f"%{sale.name}%"], "docstatus": 1}), 1)
		self.assertEqual(
			frappe.db.count("GL Entry", {"account": SCRAP_REVENUE, "is_cancelled": 0, "voucher_no": sale.sales_invoice}), 1
		)
		self.assert_refused(frappe.ValidationError, frappe.get_doc("Sales Invoice", sale.sales_invoice).cancel)

	def test_amount_is_weight_times_price_to_the_piastre(self):
		self.damage()
		# A price is kept in piastres, as the invoice keeps it: 3.333 is 3.33, and 2.345 Kg x 3.33 = 7.80885 -> 7.81.
		sale = self.sale(weight=2.345, rate=3.333)
		self.assertEqual((flt(sale.rate), flt(sale.amount)), (3.33, 7.81))
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", sale.sales_invoice, "grand_total")), 7.81)

	def test_sale_on_credit_leaves_the_invoice_to_pay(self):
		self.damage()
		sale = self.sale(paid=0)
		self.assertFalse(sale.payment_entry)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", sale.sales_invoice, "outstanding_amount")), 42.5)

	def test_selling_more_than_the_damaged_store_holds_is_refused(self):
		self.damage()
		self.assert_refused(frappe.ValidationError, self.sale, [{"item_code": PAPER, "qty": 1001}])
		self.assert_refused(frappe.ValidationError, self.sale, weight=0)
		self.assert_refused(frappe.ValidationError, self.sale, rate=0)
		self.assertEqual(qty(PAPER, DAMAGED), 1000)
		self.assertFalse(frappe.db.exists("Sales Invoice", {"customer": SCRAP_BUYER, "docstatus": 1}))

	# ---------- 10, 12: traced from the damage to the sale ----------
	def test_sale_traced_to_the_damage_record(self):
		damage = self.damage()
		sale = self.sale([{"item_code": PAPER, "qty": 600, "damage_entry": damage.name}])
		self.assertEqual(flt(frappe.db.get_value("Damaged Stock Item", {"parent": damage.name}, "sold_qty")), 600)
		# Only 400 left of that record.
		self.assert_refused(frappe.ValidationError, self.sale, [{"item_code": PAPER, "qty": 500, "damage_entry": damage.name}])
		# A damage record partly sold cannot be cancelled before its sale.
		self.assert_refused(frappe.ValidationError, frappe.get_doc("Damaged Stock Entry", damage.name).cancel)
		frappe.get_doc("Damaged Stock Sale", sale.name).cancel()
		self.assertEqual(flt(frappe.db.get_value("Damaged Stock Item", {"parent": damage.name}, "sold_qty")), 0)
		self.assertEqual(qty(PAPER, DAMAGED), 1000)
		self.assertEqual(gl(sale.sales_invoice), {})

	# ---------- No way round the damage record and the sale by weight ----------
	def test_the_damaged_store_moves_only_through_damage_and_sale(self):
		def plain_entry(purpose, row):
			doc = frappe.get_doc(
				{"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": purpose, "purpose": purpose,
				 "items": [{"item_code": PAPER, "qty": 100, "uom": frappe.db.get_value("Item", PAPER, "stock_uom"), "conversion_factor": 1, **row}]}
			)
			doc.insert()
			doc.submit()

		# In by a plain transfer: no reason, no loss, the cost kept.
		self.assert_refused(frappe.ValidationError, as_user, RAGHAD, plain_entry, "Material Transfer", {"s_warehouse": MAWASAH_STORE, "t_warehouse": DAMAGED})
		# Out by a plain issue: not a sale by weight.
		self.damage()
		self.assert_refused(frappe.ValidationError, as_user, RAGHAD, plain_entry, "Material Issue", {"s_warehouse": DAMAGED})
		self.assertEqual(qty(PAPER, DAMAGED), 1000)
		# The owner and the accountant may, to correct a mistake.
		plain_entry("Material Issue", {"s_warehouse": DAMAGED})
		self.assertEqual(qty(PAPER, DAMAGED), 900)

	# ---------- 11: who may do what ----------
	def test_permissions(self):
		# Sara records damage for Azarita only.
		self.assert_refused((frappe.PermissionError, frappe.ValidationError), self.damage, user=SARA)
		# Nour (the halls) is no library's manager.
		self.assert_refused((frappe.PermissionError, frappe.ValidationError), self.damage, [{"item_code": "BOOK", "qty": 1}], store=AZARITA_EDITIONS, user=NOUR)
		# The damaged store is Mawasah's: Sara cannot sell from it.
		self.damage()
		self.assert_refused((frappe.PermissionError, frappe.ValidationError), self.sale, user=SARA)
		# Branch managers record and submit; only the owner and the accountant cancel.
		sale = self.sale()
		self.assert_refused(frappe.PermissionError, as_user, RAGHAD, frappe.get_doc("Damaged Stock Sale", sale.name).cancel)
