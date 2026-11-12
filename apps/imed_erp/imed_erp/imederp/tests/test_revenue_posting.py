# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The studio's payments and the libraries' sales written to the ledger by themselves (imederp/revenue_posting.py):
# posted once, corrected by the difference, a studio amount lowered later left for the accountant.
#
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_revenue_posting

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp import revenue_posting as posting

# A test module outside a doctype folder builds no "_Test ..." records; keep it here, not under a doctype.
MAWASAH = "مكتبة المواساة - MMG"
MAWASAH_BOX, MAWASAH_INCOME = "خزينة مكتبة المواساة - MMG", "إيراد مكتبة المواساة - MMG"
STUDIO, STUDIO_BOX, STUDIO_INCOME = "استوديو X - MMG", "خزينة X Studio - MMG", "إيراد X Studio - MMG"


class IntegrationTestRevenuePosting(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("revenue_posting")
		posting.make_custom_fields()
		self.n = 0

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="revenue_posting")

	def balance(self, account):
		return flt(frappe.db.sql("select coalesce(sum(debit - credit), 0) from `tabGL Entry` where account = %s and is_cancelled = 0", account)[0][0], 2)

	def document(self, kind, total, **values):
		self.n += 1
		doc = frappe.get_doc(
			{
				"doctype": "Library Sales Document",
				"document_kind": kind,
				"number": f"T{self.n}",
				"reg_date": f"{today()} 10:00:00",
				"is_final": 1,
				"cost_center": MAWASAH,
				"total": total,
				"source_system": "tanmya",
				"library": "test",
				"family": "stock",
				"external_id": f"test-{self.n}",
				"import_key": f"tanmya:test:stock:rp-{self.n}",
				**values,
			}
		)
		frappe.flags.library_sync = True  # only the sync writes a mirrored document
		try:
			doc.insert(ignore_permissions=True, ignore_mandatory=True)
		finally:
			frappe.flags.library_sync = False
		return doc

	def settle_all(self, targets):
		return [posting.settle(t) for t in targets]

	def mine(self):
		return [t for t in posting.library_targets(today()) if t["cost_center"] == MAWASAH and str(t["date"]) == today()]

	def test_a_library_s_day_is_posted_once_then_corrected_by_the_difference(self):
		box, income = self.balance(MAWASAH_BOX), self.balance(MAWASAH_INCOME)
		already = posting.posted(f"library:{MAWASAH}:{today()}", MAWASAH_INCOME)
		sale = self.document("Retail Sale", 500)
		self.document("Retail Return", 100)
		self.document("Purchase", 9000)  # not a sale: never revenue
		self.document("Retail Sale", 70, is_final=0)  # not final yet
		before = self.mine()[0]["amount"]
		self.settle_all(self.mine())
		self.assertEqual(posting.posted(f"library:{MAWASAH}:{today()}", MAWASAH_INCOME), before)
		self.assertEqual(self.balance(MAWASAH_BOX) - box, before - already)
		self.assertEqual(income - self.balance(MAWASAH_INCOME), before - already)
		# Again: nothing new.
		self.assertEqual(self.settle_all(self.mine()), [(None, None, 0)])
		# One more sale: the difference only.
		extra = self.document("Wholesale Sale", 50)
		self.assertEqual(self.settle_all(self.mine())[0][2], 50)
		# The library cancels a sale: the day follows it down.
		frappe.db.set_value("Library Sales Document", extra.name, "is_cancelled", 1)
		self.assertEqual(self.settle_all(self.mine())[0][2], -50)
		self.assertEqual(self.balance(MAWASAH_BOX) - box, before - already)
		# A fall the cash box cannot cover is refused by the box's own rule (never below zero), not forced.
		frappe.db.set_value("Library Sales Document", sale.name, "total", -100000)
		self.assertRaises(frappe.ValidationError, self.settle_all, self.mine())

	def test_a_studio_payment_is_posted_and_one_lowered_later_waits_for_the_accountant(self):
		target = {"key": "xstudio:booking:TEST-RP", "amount": 300, "date": today(), "cash": STUDIO_BOX, "income": STUDIO_INCOME, "cost_center": STUDIO, "remark": "test"}
		box = self.balance(STUDIO_BOX)
		what, entry, amount = posting.settle(target)
		self.assertEqual((what, amount), ("posted", 300))
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, [posting.KEY, "docstatus"]), ("xstudio:booking:TEST-RP", 1))
		self.assertEqual(self.balance(STUDIO_BOX) - box, 300)
		# Paid more: the difference.
		self.assertEqual(posting.settle({**target, "amount": 450})[2], 150)
		# Lowered in XStudio: nothing is reversed here.
		self.assertEqual(posting.settle({**target, "amount": 200}), ("review", None, -250))
		self.assertEqual(self.balance(STUDIO_BOX) - box, 450)

	def test_nothing_runs_until_it_is_switched_on(self):
		frappe.db.set_single_value(posting.SETTINGS, {"post_studio": 0, "post_libraries": 0})
		self.assertIsNone(posting.run())
