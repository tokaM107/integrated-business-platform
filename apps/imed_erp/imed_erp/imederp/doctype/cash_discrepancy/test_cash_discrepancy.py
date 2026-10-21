# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A shortage or surplus at a daily close (owner, 21 Oct 2026): investigated by the accountant; nobody is charged until
# found responsible; a recovery needs the employee told, the contract and the law checked and each amount typed;
# nothing is split or deducted by itself; a surplus is never revenue; the books are adjusted only after the review,
# once. A branch manager reads her own branch's and decides nothing. Rolled back.
#
# Run:
#   bench --site frontend run-tests --doctype "Cash Discrepancy"

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp.doctype.cash_discrepancy import cash_discrepancy as cd
from imed_erp.imederp.doctype.treasury_close.test_treasury_close import (
	ACCOUNTANT, AZARITA_BOX, DAY1, MAWASAH, MAWASAH_BOX, SARA, close,
)
from imed_erp.imederp.doctype.weekly_cash_reconciliation.test_weekly_cash_reconciliation import closed
from imed_erp.imederp.report.cash_discrepancies.cash_discrepancies import execute as report
from imed_erp.imederp.testing import fund_cash_boxes

IGNORE_TEST_RECORD_DEPENDENCIES = ["Account", "Cost Center", "Journal Entry", "User", "Treasury Close", "Cash Discrepancy", "Weekly Cash Reconciliation"]

RAGHAD = "raghad@imed.local"
DIFFERENCES = "فروقات الخزينة - MMG"


class IntegrationTestCashDiscrepancy(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fund_cash_boxes()

	def setUp(self):
		frappe.db.savepoint("discrepancy")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="discrepancy")

	def as_user(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def refused(self, error, pattern, user, fn, *args, **kwargs):
		frappe.db.savepoint("refused")
		try:
			with self.assertRaisesRegex(error, pattern):
				self.as_user(user, fn, *args, **kwargs)
		finally:
			frappe.db.rollback(save_point="refused")

	def shortage(self, amount=100):
		return frappe.get_doc("Cash Discrepancy", closed(DAY1, -amount).cash_discrepancy)

	def investigate(self, doc, *rows):
		"""rows: (user, responsible, notified_on, recovery_amount)"""
		doc.investigation_notes = "Counted the drawer and the receipts with the branch."
		doc.employees = []
		for user, responsible, notified_on, amount in rows:
			doc.append("employees", {"user": user, "responsible": responsible, "notified_on": notified_on, "recovery_amount": amount})
		self.as_user(ACCOUNTANT, doc.save)
		return doc

	# 13. Investigation, then approval, each with its conditions.
	def test_a_recovery_needs_an_investigation_the_employee_told_and_the_law_checked(self):
		doc = self.shortage(100)
		self.refused(frappe.ValidationError, "Write what the investigation found", ACCOUNTANT, cd.determine_responsibility, doc.name)
		self.investigate(doc, (SARA, 0, None, 0), (RAGHAD, 0, None, 0))
		self.refused(frappe.ValidationError, "Mark who is responsible", ACCOUNTANT, cd.determine_responsibility, doc.name)
		# Not found responsible: nothing to recover from them.
		doc.employees[1].recovery_amount = 10
		self.refused(frappe.ValidationError, "not found responsible", ACCOUNTANT, doc.save)
		doc.reload()

		self.investigate(doc, (SARA, 1, None, 60), (RAGHAD, 0, None, 0))
		self.assertEqual(self.as_user(ACCOUNTANT, cd.determine_responsibility, doc.name), "Responsibility Determined")
		self.refused(frappe.ValidationError, "has not been told", ACCOUNTANT, cd.approve_recovery, doc.name)
		doc.reload()
		doc.employees[0].notified_on = today()
		doc.employees[0].employee_response = "Agrees"
		self.as_user(ACCOUNTANT, doc.save)
		self.refused(frappe.ValidationError, "contract and the labour law", ACCOUNTANT, cd.approve_recovery, doc.name)
		doc.reload()
		doc.legal_check = 1
		doc.employees[0].recovery_amount = 101
		self.as_user(ACCOUNTANT, doc.save)
		self.refused(frappe.ValidationError, "more than the shortage", ACCOUNTANT, cd.approve_recovery, doc.name)
		doc.reload()
		doc.employees[0].recovery_amount = 60
		self.as_user(ACCOUNTANT, doc.save)

		before = frappe.db.count("GL Entry")
		self.assertEqual(self.as_user(ACCOUNTANT, cd.approve_recovery, doc.name), "Recovery Approved")
		doc.reload()
		self.assertEqual((doc.recovery_total, doc.payroll_status, doc.approved_by), (60, "Ready for Payroll Review", ACCOUNTANT))
		# 14. Nothing deducted, posted or split: the payroll review lists the 60 typed for Sara, nothing for Raghad.
		self.assertEqual(frappe.db.count("GL Entry"), before)
		rows = report({"view": "Payroll Review", "from_date": DAY1, "to_date": today()})[1]
		mine = [(r["user"], r["recovery_amount"]) for r in rows if r["name"] == doc.name]
		self.assertEqual(mine, [(SARA, 60)])
		# Settled: the decision is kept.
		doc.reload()
		doc.employees[0].recovery_amount = 1
		self.refused(frappe.ValidationError, "can no longer be changed", ACCOUNTANT, doc.save)

	def test_two_responsible_employees_are_not_split_by_themselves(self):
		doc = self.shortage(100)
		self.investigate(doc, (SARA, 1, today(), 0), (RAGHAD, 1, today(), 0))
		doc.legal_check = 1
		self.as_user(ACCOUNTANT, doc.save)
		self.as_user(ACCOUNTANT, cd.determine_responsibility, doc.name)
		self.refused(frappe.ValidationError, "Nothing is split by itself", ACCOUNTANT, cd.approve_recovery, doc.name)

	# 7, 13. A branch manager reads her branch's and decides nothing; another branch's is hidden.
	def test_a_branch_manager_reads_her_own_and_decides_nothing(self):
		doc = self.shortage()
		self.assertTrue(frappe.has_permission("Cash Discrepancy", "read", doc.name, user=SARA))
		self.assertFalse(frappe.has_permission("Cash Discrepancy", "write", doc.name, user=SARA))
		for action, args in [
			(cd.determine_responsibility, ()), (cd.approve_recovery, ()), (cd.write_off, ("x",)), (cd.post_adjustment, ()),
		]:
			self.refused(frappe.PermissionError, "", SARA, action, doc.name, *args)
		mawasah = frappe.get_doc("Cash Discrepancy", closed(DAY1, -5, MAWASAH_BOX, MAWASAH).cash_discrepancy)
		self.assertFalse(frappe.has_permission("Cash Discrepancy", "read", mawasah.name, user=SARA))
		names = [r["name"] for r in self.as_user(SARA, report, {"view": "Discrepancies", "from_date": DAY1, "to_date": today()})[1]]
		self.assertIn(doc.name, names)
		self.assertNotIn(mawasah.name, names)
		self.refused(frappe.PermissionError, "", SARA, report, {"view": "Payroll Review", "from_date": DAY1, "to_date": today()})

	def test_a_written_off_shortage_and_its_adjustment(self):
		doc = self.shortage(40)
		self.refused(frappe.ValidationError, "cannot be done to it now", ACCOUNTANT, cd.post_adjustment, doc.name)
		self.as_user(ACCOUNTANT, cd.write_off, doc.name, "Not found after a recount")
		entry = self.as_user(ACCOUNTANT, cd.post_adjustment, doc.name)
		lines = {r.account: (r.debit, r.credit) for r in frappe.get_all("GL Entry", filters={"voucher_no": entry}, fields=["account", "debit", "credit"])}
		self.assertEqual(lines, {AZARITA_BOX: (0, 40), DIFFERENCES: (40, 0)})
		self.refused(frappe.ValidationError, "already adjusted", ACCOUNTANT, cd.post_adjustment, doc.name)
		# The next close starts from the cash counted; the adjustment is not counted again.
		nxt = close(0, today())
		self.assertEqual((nxt.last_close, nxt.opening, nxt.other_out), (doc.treasury_close, closed_counted(doc), 0))
		self.assertEqual(nxt.book_balance, nxt.expected)

	def test_a_surplus_is_explained_then_adjusted_never_revenue_by_itself(self):
		doc = frappe.get_doc("Cash Discrepancy", closed(DAY1, 25).cash_discrepancy)
		self.refused(frappe.ValidationError, "cannot be done", ACCOUNTANT, cd.approve_recovery, doc.name)
		self.refused(frappe.ValidationError, "Reason Needed|Write where", ACCOUNTANT, cd.explain_surplus, doc.name, " ")
		self.as_user(ACCOUNTANT, cd.explain_surplus, doc.name, "A customer paid twice; to be returned")
		entry = self.as_user(ACCOUNTANT, cd.post_adjustment, doc.name)
		lines = {r.account: (r.debit, r.credit) for r in frappe.get_all("GL Entry", filters={"voucher_no": entry}, fields=["account", "debit", "credit"])}
		self.assertEqual(lines, {AZARITA_BOX: (25, 0), DIFFERENCES: (0, 25)})

	def test_kept_and_listed(self):
		doc = self.shortage(10)
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Cash Discrepancy", doc.name)
		self.assertEqual(cd.unresolved_count(), frappe.db.count("Cash Discrepancy", {"status": ("in", cd.OPEN)}))
		rows = report({"view": "Discrepancies", "from_date": DAY1, "to_date": today(), "unresolved": 1})[1]
		self.assertIn(doc.name, [r["name"] for r in rows])


def closed_counted(doc):
	return flt(frappe.db.get_value("Treasury Close", doc.treasury_close, "counted"), 2)
