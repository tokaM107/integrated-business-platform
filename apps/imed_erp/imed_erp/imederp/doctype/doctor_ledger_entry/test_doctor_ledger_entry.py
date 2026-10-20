# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A doctor's ledger has no company or cost center, so the month lock (CORE-09) uses the default company:
# no entry is saved or cancelled in a closed month. An accrual names the invoice line it comes from, and a line
# is counted once (DOC-07). A payout comes out of a treasury, in part and as often as needed, with its journal
# entry (DOC-09, ACC-11). A deduction from the doctor is applied only once the owner or the accountant approves it
# (DOC-22). Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Doctor Ledger Entry"

import frappe
from unittest.mock import patch

from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement, make_doctor
from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import get_balance

# Linked records already exist on the site or are made by the tests; without this list Frappe builds
# ERPNext's "_Test ..." records and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Academic Period",
	"Account",
	"App Course",
	"Book Edition",
	"Customer",
	"Doctor Agreement",
	"Doctor Ledger Entry",
	"Journal Entry",
	"Sales Invoice",
	"User",
]

COMPANY = "Mohamed Mamdouh group"
MAWASAH = "مكتبة المواساة - MMG"
CASH_BOX = "خزينة مكتبة المواساة - MMG"
WALLET = "محفظة InstaPay - MMG"
PAYABLE = "مستحقات للأطباء — الكتب - MMG"
LEDGER = "Doctor Ledger Entry"
ACCOUNTANT = "accountant@imed.local"
HR = "hr@imed.local"


class IntegrationTestDoctorLedgerEntry(IntegrationTestCase):
	def new_entry(self, entry_date, **values):
		return frappe.get_doc(
			{
				"doctype": "Doctor Ledger Entry",
				"agreement": make_agreement("Books"),
				"entry_date": entry_date,
				"entry_type": "Accrual",
				"amount": 100,
				**values,
			}
		)

	def draft_sale(self, lines=1):
		"""A draft sale with `lines` rows: the ledger only needs its invoice and line names."""
		item = frappe.get_all("Item", filters={"is_sales_item": 1, "disabled": 0, "has_variants": 0}, pluck="name", limit=1)[0]
		return frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": make_doctor(),
				"cost_center": MAWASAH,
				"items": [{"item_code": item, "qty": 1, "rate": 100, "cost_center": MAWASAH} for _ in range(lines)],
			}
		).insert()

	def test_an_invoice_line_is_counted_once(self):
		sale = self.draft_sale()
		line = {"sales_invoice": sale.name, "invoice_item": sale.items[0].name}
		first = self.new_entry(today(), **line).insert()
		self.assertRaisesRegex(frappe.ValidationError, "already in the doctor's ledger", self.new_entry(today(), **line).insert)

		# Once the first is cancelled (its sale was cancelled), the line may be counted again.
		first.submit()
		first.cancel()
		self.new_entry(today(), **line).insert()

	def test_an_invoice_line_is_on_its_invoice(self):
		one, other = self.draft_sale(), self.draft_sale()
		entry = self.new_entry(today(), sales_invoice=other.name, invoice_item=one.items[0].name)
		self.assertRaisesRegex(frappe.ValidationError, "is not on invoice", entry.insert)

	def test_the_source_is_filled_by_the_system(self):
		meta = frappe.get_meta("Doctor Ledger Entry")
		for field in ("sales_invoice", "invoice_item", "journal_entry"):
			with self.subTest(field):
				self.assertTrue(meta.get_field(field).read_only)
				self.assertTrue(meta.get_field(field).no_copy)

	def close_month(self):
		return frappe.get_doc(
			{
				"doctype": "Accounting Period",
				"period_name": "_Test Closed Month",
				"start_date": "2026-08-01",
				"end_date": "2026-08-31",
				"company": frappe.defaults.get_global_default("company"),
				"closed_documents": [{"document_type": "Doctor Ledger Entry", "closed": 1}],
			}
		).insert()

	def test_no_entry_saved_in_a_closed_month(self):
		period = self.close_month()
		try:
			self.assertRaises(frappe.ValidationError, self.new_entry("2026-08-15").insert)
			self.new_entry("2026-09-15").insert()
		finally:
			frappe.delete_doc("Accounting Period", period.name)

	def test_no_entry_cancelled_in_a_closed_month(self):
		entry = self.new_entry("2026-08-15").insert()
		entry.submit()
		period = self.close_month()
		try:
			self.assertRaises(frappe.ValidationError, entry.cancel)
			self.assertEqual(frappe.db.get_value("Doctor Ledger Entry", entry.name, "docstatus"), 1)
		finally:
			frappe.delete_doc("Accounting Period", period.name)
		# Once the month is open again, the entry is cancelled as usual.
		entry.reload()
		entry.cancel()

	# ---------- Payouts (DOC-09, ACC-11) ----------

	def payout(self, amount, treasury=CASH_BOX, submit=True):
		entry = self.new_entry(today(), entry_type="Payout", amount=amount, treasury=treasury).insert()
		if submit:
			entry.submit()
		return entry

	def gl(self, journal_entry):
		return sorted(
			(g.account, g.debit, g.credit)
			for g in frappe.get_all(
				"GL Entry",
				filters={"voucher_type": "Journal Entry", "voucher_no": journal_entry, "is_cancelled": 0},
				fields=["account", "debit", "credit"],
			)
		)

	def test_a_payout_in_parts_from_any_treasury(self):
		agreement = make_agreement("Books")
		self.new_entry(today(), amount=500).insert().submit()
		owed = get_balance(agreement)

		first = self.payout(200)
		second = self.payout(owed - 200, WALLET)
		self.assertEqual(self.gl(first.journal_entry), sorted([(PAYABLE, 200, 0), (CASH_BOX, 0, 200)]))
		self.assertEqual(self.gl(second.journal_entry), sorted([(PAYABLE, owed - 200, 0), (WALLET, 0, owed - 200)]))
		self.assertEqual(flt(frappe.db.get_value("Doctor Agreement", agreement, "balance")), 0)
		self.assertEqual(frappe.db.get_value("Doctor Agreement", agreement, "last_settlement_amount"), owed - 200)

	def test_no_payout_beyond_what_is_owed(self):
		agreement = make_agreement("Books")
		self.new_entry(today(), amount=100).insert().submit()
		owed = get_balance(agreement)
		self.assertRaisesRegex(frappe.ValidationError, "more than that", self.payout, owed + 1)
		self.payout(owed)
		self.assertRaisesRegex(frappe.ValidationError, "more than that", self.payout, 1)

	def test_a_payout_needs_a_treasury(self):
		self.new_entry(today(), amount=100).insert().submit()
		self.assertRaisesRegex(frappe.ValidationError, "Choose the treasury", self.payout, 10, None)
		self.assertRaisesRegex(frappe.ValidationError, "is not a treasury", self.payout, 10, PAYABLE)
		# Other kinds of entry keep no treasury.
		accrual = self.new_entry(today(), treasury=CASH_BOX).insert()
		self.assertIsNone(accrual.treasury)

	def test_a_cancelled_payout_takes_its_journal_entry_with_it(self):
		agreement = make_agreement("Books")
		self.new_entry(today(), amount=300).insert().submit()
		before = get_balance(agreement)
		payout = self.payout(100)
		# The journal entry alone is not cancelled: the ledger would still show the money paid.
		self.assertRaisesRegex(
			frappe.ValidationError, "Cancel that entry instead", frappe.get_doc("Journal Entry", payout.journal_entry).cancel
		)
		payout.reload()
		payout.cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", payout.journal_entry, "docstatus"), 2)
		self.assertEqual(self.gl(payout.journal_entry), [])
		self.assertEqual(get_balance(agreement), before)

	def test_the_payout_receipt(self):
		# A simple receipt until the final design (week C): who was paid, from which treasury, how much in figures
		# and in words, and room for both signatures. The ledger prints with it by default.
		self.assertEqual(frappe.get_meta("Doctor Ledger Entry").default_print_format, "MMG Doctor Payout")
		self.new_entry(today(), amount=500).insert().submit()
		payout = self.payout(150)
		doctor = frappe.db.get_value("Doctor Agreement", payout.agreement, "doctor")
		lang = frappe.local.lang
		try:
			frappe.local.lang = "ar"
			html = frappe.get_print("Doctor Ledger Entry", payout.name, print_format="MMG Doctor Payout")
		finally:
			frappe.local.lang = lang
		for text in ("إيصال صرف للطبيب", doctor, "خزينة مكتبة المواساة", "فقط", "جنيه مصري", "توقيع المستلم (الطبيب)", payout.name):
			with self.subTest(text):
				self.assertIn(text, html)
		self.assertIn("Doctor Payout Receipt", frappe.get_print("Doctor Ledger Entry", payout.name, print_format="MMG Doctor Payout"))

	# ---------- Approving a deduction (DOC-22) ----------

	def pending_charge(self, amount=50):
		# As closing a term raises it (charge_unsold_copies).
		entry = self.new_entry(today(), entry_type="Unsold Copies Charge", amount=amount)
		entry.approval_status = "Pending Approval"
		entry.flags.approval_action = True
		return entry.insert()

	def test_the_accountant_approves_a_charge(self):
		charge = self.pending_charge()
		frappe.set_user(ACCOUNTANT)
		try:
			frappe.get_doc(LEDGER, charge.name).approve()
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value(LEDGER, charge.name, ["docstatus", "approval_status", "approved_by"]), (1, "Approved", ACCOUNTANT)
		)

	def test_a_rejected_charge_is_closed(self):
		charge = self.pending_charge()
		frappe.set_user(ACCOUNTANT)
		try:
			frappe.get_doc(LEDGER, charge.name).reject("_Test the doctor took the copies")
		finally:
			frappe.set_user("Administrator")
		rejected = frappe.get_doc(LEDGER, charge.name)
		self.assertEqual((rejected.docstatus, rejected.approval_status, rejected.approved_by), (0, "Rejected", ACCOUNTANT))
		rejected.amount = 10
		self.assertRaisesRegex(frappe.ValidationError, "rejected and is closed", rejected.save)
		self.assertRaisesRegex(frappe.ValidationError, "rejected and is closed", frappe.get_doc(LEDGER, charge.name).submit)
		self.assertRaisesRegex(frappe.ValidationError, "not a deduction waiting", frappe.get_doc(LEDGER, charge.name).approve)

	def test_only_an_approver_applies_a_deduction(self):
		charge = self.pending_charge()
		frappe.set_user(HR)
		try:
			self.assertRaises(frappe.PermissionError, frappe.get_doc(LEDGER, charge.name).approve)
		finally:
			frappe.set_user("Administrator")
		# Someone with the right to submit but not to approve: refused, for a charge and a deduction by hand.
		module = "imed_erp.imederp.doctype.doctor_ledger_entry.doctor_ledger_entry.is_approver"
		by_hand = self.new_entry(today(), entry_type="Adjustment", amount=-30).insert()
		with patch(module, return_value=False):
			for entry in (frappe.get_doc(LEDGER, charge.name), by_hand):
				with self.subTest(entry.entry_type):
					self.assertRaisesRegex(frappe.ValidationError, "approves it", entry.submit)

	def test_an_approver_s_own_deduction_is_approved_as_he_submits_it(self):
		entry = self.new_entry(today(), entry_type="Adjustment", amount=-30).insert()
		entry.submit()
		self.assertEqual((entry.approval_status, entry.approved_by), ("Approved", "Administrator"))
		# Money owed to the doctor or paid to him is not a deduction.
		for entry_type, amount in (("Adjustment", 30), ("Accrual", 30)):
			with self.subTest(entry_type):
				other = self.new_entry(today(), entry_type=entry_type, amount=amount).insert()
				other.submit()
				self.assertIsNone(other.approval_status)

	def test_the_approval_is_not_set_through_the_api(self):
		entry = self.new_entry(today(), entry_type="Unsold Copies Charge", amount=50)
		entry.approval_status, entry.approved_by = "Approved", HR
		entry.insert()
		self.assertEqual((entry.approval_status, entry.approved_by), (None, None))
		entry.approval_status = "Approved"
		self.assertRaisesRegex(frappe.ValidationError, "only with Approve or Reject", entry.save)


	# ---------- The ledger and the accounts agree (QA-02) ----------

	def gl_rows(self, journal_entry):
		return sorted(
			(g.account, g.party or None, g.debit, g.credit)
			for g in frappe.get_all(
				"GL Entry",
				filters={"voucher_type": "Journal Entry", "voucher_no": journal_entry, "is_cancelled": 0},
				fields=["account", "party", "debit", "credit"],
			)
		)

	def test_qa02_entries_by_hand_post_to_the_accounts(self):
		expense = "حصة الأطباء - MMG"
		accrual = self.new_entry(today(), amount=1000).insert()
		accrual.submit()
		self.assertEqual(self.gl_rows(accrual.journal_entry), sorted([(expense, None, 1000, 0), (PAYABLE, None, 0, 1000)]))

		charge = self.pending_charge(300)
		frappe.get_doc(LEDGER, charge.name).approve()
		charge.reload()
		self.assertEqual(self.gl_rows(charge.journal_entry), sorted([(PAYABLE, None, 300, 0), (expense, None, 0, 300)]))

		minus = self.new_entry(today(), entry_type="Adjustment", amount=-50).insert()
		minus.submit()
		self.assertEqual(self.gl_rows(minus.journal_entry), sorted([(PAYABLE, None, 50, 0), (expense, None, 0, 50)]))

		# Cancelling the entry takes its journal entry with it; the journal entry alone is not cancelled.
		self.assertRaisesRegex(
			frappe.ValidationError, "Cancel that entry instead", frappe.get_doc("Journal Entry", charge.journal_entry).cancel
		)
		charge.cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", charge.journal_entry, "docstatus"), 2)
		self.assertEqual(self.gl_rows(charge.journal_entry), [])

	def test_qa02_an_app_adjustment_is_owed_by_the_doctor_in_the_accounts(self):
		agreement = make_agreement("App")
		doctor = frappe.db.get_value("Doctor Agreement", agreement, "doctor")
		receivable, revenue = "مستحقات على الأطباء — رسوم المنصة - MMG", "إيراد رسوم المنصة - MMG"
		entry = self.new_entry(today(), agreement=agreement, entry_type="Adjustment", amount=1000).insert()
		entry.submit()
		self.assertEqual(self.gl_rows(entry.journal_entry), sorted([(receivable, doctor, 1000, 0), (revenue, None, 0, 1000)]))
		self.assertEqual(
			set(frappe.get_all("GL Entry", filters={"voucher_no": entry.journal_entry}, pluck="cost_center")),
			{"تطبيق BA Plus - MMG"},
		)

	def test_qa11_the_agreement_is_locked_before_its_balance_is_read(self):
		# Two sessions cannot run in one test; what keeps them apart is the lock taken before the balance is read.
		self.new_entry(today(), amount=500).insert().submit()
		module = "imed_erp.imederp.doctype.doctor_ledger_entry.doctor_ledger_entry"
		calls = []
		with patch(f"{module}.lock_agreement", side_effect=calls.append), patch(
			f"{module}.get_balance", side_effect=lambda agreement: calls.append("balance") or 500
		):
			self.payout(100, submit=False)
		self.assertEqual(calls[:2], [make_agreement("Books"), "balance"])

	def test_qa24_no_payout_dated_ahead(self):
		from frappe.utils import add_days

		self.new_entry(today(), amount=500).insert().submit()
		entry = self.new_entry(add_days(today(), 1), entry_type="Payout", amount=10, treasury=CASH_BOX)
		self.assertRaisesRegex(frappe.ValidationError, "after today", entry.insert)
