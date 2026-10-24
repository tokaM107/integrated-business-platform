# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Opening cash on a new site (imederp/opening_cash.py): every treasury checked; the counted cash prepared as a draft
# opening entry only, never for a wallet, a box with entries, or below zero. Rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_opening_cash

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp import opening_cash
from imed_erp.imederp.doctype.treasury_close.test_treasury_close import AZARITA_BOX, HALLS_BOX, INSTAPAY, move

APP_TREASURY = "خزينة تطبيق BA Plus - MMG"


class IntegrationTestOpeningCash(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("opening_cash")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="opening_cash")

	def test_every_treasury_is_checked(self):
		rows = {row.treasury: row for row in opening_cash.treasuries()}
		for box in (AZARITA_BOX, HALLS_BOX):
			self.assertEqual((rows[box].type, bool(rows[box].business)), ("Cash", True))
		# The app's treasury is a bank account: the close and the cash check do not reach it.
		if rows.get(APP_TREASURY) and rows[APP_TREASURY].type == "Bank":
			self.assertTrue(rows[APP_TREASURY].problems)

	def test_a_draft_for_the_accountant_never_twice(self):
		self.assertRaisesRegex(frappe.ValidationError, "is not a cash box", opening_cash.prepare, {INSTAPAY: 10})
		self.assertRaisesRegex(frappe.ValidationError, "below zero", opening_cash.prepare, {HALLS_BOX: -1})
		move(100, box=AZARITA_BOX)
		self.assertRaisesRegex(frappe.ValidationError, "already has entries", opening_cash.prepare, {AZARITA_BOX: 50})
		empty = [
			row.treasury for row in opening_cash.treasuries() if row.type == "Cash" and not row.entries and row.business
		]
		if not empty:
			self.skipTest("every cash box has entries on this site")
		name = opening_cash.prepare({empty[0]: 1500})
		entry = frappe.get_doc("Journal Entry", name)
		self.assertEqual((entry.docstatus, entry.is_opening), (0, "Yes"))
		self.assertEqual(
			sorted((r.account, r.debit_in_account_currency, r.credit_in_account_currency) for r in entry.accounts),
			sorted([(empty[0], 1500, 0), (f"{opening_cash.OPENING_EQUITY} - MMG", 0, 1500)]),
		)
