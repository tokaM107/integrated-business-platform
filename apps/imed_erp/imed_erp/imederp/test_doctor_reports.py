# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Doctor Receivables (RPT-08): figures read from the doctor's ledger, worked out by hand below. Doctor Debts
# (RPT-10) has its own tests (test_doctor_debts.py). Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_doctor_reports

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.app_course.test_app_course import make_course
from imed_erp.imederp.doctype.book_edition.test_book_edition import PAPER_COST, make_agreement, make_doctor
from imed_erp.imederp.report.doctor_receivables import doctor_receivables

# A test module outside a doctype folder builds no "_Test ..." records; keep it here, not under a doctype.
MAWASAH = "مكتبة المواساة - MMG"
APP = "تطبيق BA Plus - MMG"
CASH_BOX = "خزينة مكتبة المواساة - MMG"
AS_ON = "2026-10-15"


class IntegrationTestDoctorReports(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Books, owed to the doctor: 1,000 (Mawasah's edition) + 500 accrued, 600 paid out, -50 adjusted = 850.
		cls.owed = make_agreement("Books", 81)
		cls.edition = cls.make_edition(cls.owed)
		cls.entry(cls.owed, "2026-09-10", "Accrual", 1000, edition=cls.edition)
		cls.entry(cls.owed, "2026-09-20", "Accrual", 500)
		# A payout comes out of a treasury and posts its journal entry (doctor_ledger_entry.post_payout).
		cls.entry(cls.owed, "2026-10-01", "Payout", 600, treasury=CASH_BOX)
		cls.entry(cls.owed, "2026-10-05", "Adjustment", -50)
		# Books, below zero (DOC-20): 100 accrued on 1 Aug, 300 charged for unsold copies on 1 Sep. The 100 owed to
		# him is set against the charge, so 200 of it is still owed, since 1 Sep.
		cls.negative = make_agreement("Books", 82)
		cls.entry(cls.negative, "2026-08-01", "Accrual", 100)
		cls.entry(cls.negative, "2026-09-01", "Unsold Copies Charge", 300)
		# App: fees 250 (1 Jul) and 200 (20 Sep), 300 collected on 1 Oct. The oldest fee is paid first, so 150 of
		# the 20 Sep fee is still owed.
		cls.app = make_agreement("App", 83)
		cls.subscription(cls.app, "2026-07-01", 250)
		cls.subscription(cls.app, "2026-09-20", 200)
		cls.entry(cls.app, "2026-10-01", "Collection", 300)
		# App whose fee is also posted to the ledger as an Accrual: counted once, from the ledger.
		cls.app_in_ledger = make_agreement("App", 84)
		cls.subscription(cls.app_in_ledger, "2026-10-01", 170)
		cls.entry(cls.app_in_ledger, "2026-10-01", "Accrual", 170)

	@classmethod
	@patch(PAPER_COST, return_value=0.30)
	def make_edition(cls, agreement, _):
		return (
			frappe.get_doc(
				{
					"doctype": "Book Edition",
					"edition_name": f"_Test Report Edition {frappe.generate_hash(length=6)}",
					"agreement": agreement,
					"cost_center": MAWASAH,
					"pages": 10,
					"doctor_qty": 10,
				}
			)
			.insert()
			.name
		)

	@staticmethod
	def entry(agreement, date, entry_type, amount, **values):
		doc = frappe.get_doc(
			{"doctype": "Doctor Ledger Entry", "agreement": agreement, "entry_date": date, "entry_type": entry_type, "amount": amount, **values}
		).insert()
		doc.submit()

	@staticmethod
	def subscription(agreement, date, fee):
		doc = frappe.get_doc(
			{
				"doctype": "App Subscription",
				"student": make_doctor("_Test Report Student"),
				"course": make_course(agreement=agreement),
				"subscription_date": date,
				"platform_fee": fee,
				"cost_center": APP,
			}
		).insert()
		doc.submit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def receivables(self, **filters):
		return doctor_receivables.execute(frappe._dict({"to_date": AS_ON, **filters}))[1]

	# ---------- RPT-08 ----------

	def test_receivables_follow_the_ledger_and_the_agreement_balance(self):
		rows = self.receivables(from_date="2026-10-01", agreement=self.owed)
		[total] = [row for row in rows if row["indent"] == 0]
		self.assertEqual(
			[total[f] for f in ("opening", "accrued", "adjustments", "charges", "paid", "outstanding", "entries")],
			[1500, 0, -50, 0, 600, 850, 2],
		)
		# The same figure as the agreement's own balance (the ledger), and the doctor of the agreement.
		self.assertEqual(frappe.db.get_value("Doctor Agreement", self.owed, "balance"), 850)
		self.assertEqual(total["doctor"], frappe.db.get_value("Doctor Agreement", self.owed, "doctor"))

	def test_receivables_by_branch_add_up_to_the_agreement(self):
		rows = [row for row in self.receivables(agreement=self.owed) if row["indent"] == 1]
		by_branch = {row["branch"]: row["outstanding"] for row in rows}
		# The edition's accrual is Mawasah's; the rest (an accrual and a payout with no sale or edition) is not. The
		# payout's journal entry has a cost center (the company's default) but it is not a library, so it is not read.
		self.assertEqual(by_branch, {MAWASAH: 1000, None: -150})
		self.assertEqual(sum(by_branch.values()), 850)
		payout = frappe.db.get_value("Doctor Ledger Entry", {"agreement": self.owed, "entry_type": "Payout"}, "journal_entry")
		self.assertTrue(payout)
		only_mawasah = self.receivables(agreement=self.owed, branch=MAWASAH)
		self.assertEqual([row["outstanding"] for row in only_mawasah], [1000])

	def test_an_earlier_to_date_gives_the_balance_on_that_day(self):
		[total] = [row for row in self.receivables(to_date="2026-09-30", agreement=self.owed) if row["indent"] == 0]
		self.assertEqual(total["outstanding"], 1500)

	def test_receivables_leave_out_debts_and_app_agreements(self):
		agreements = {row["agreement"] for row in self.receivables()}
		self.assertIn(self.owed, agreements)
		self.assertNotIn(self.negative, agreements)  # owes the group: in Doctor Debts
		self.assertNotIn(self.app, agreements)
		self.assertIn(self.negative, {row["agreement"] for row in self.receivables(show_settled=1)})

	def test_receivables_stay_on_books_agreements_whatever_the_filters_say(self):
		"""An app balance runs the other way: shown here it would read as money owed to the doctor."""
		agreements = {row["agreement"] for row in self.receivables(agreement_type="App", show_settled=1)}
		self.assertNotIn(self.app, agreements)
		self.assertIn(self.owed, agreements)

	def test_a_new_kind_of_entry_does_not_break_the_report(self):
		from imed_erp.imederp import doctor_balances

		real = doctor_balances.get_entries

		def with_a_new_kind(agreements, to_date=None):
			entries = real(agreements, to_date)
			entries.append(frappe._dict(agreement=self.owed, entry_date="2026-10-10", entry_type="Something New", signed=-25, branch=None))
			return entries

		with patch.object(doctor_receivables, "get_entries", with_a_new_kind):
			[total] = [row for row in self.receivables(agreement=self.owed) if row["indent"] == 0]
		self.assertEqual((total["adjustments"], total["outstanding"]), (-75, 825))

	# ---------- Who ----------

	def test_only_those_who_may_read_the_doctors_accounts(self):
		for user in ("raghad@imed.local", "sara@imed.local", "hr@imed.local"):
			frappe.set_user(user)
			self.assertRaises(frappe.PermissionError, doctor_receivables.execute, {})
		frappe.set_user("accountant@imed.local")
		self.assertTrue(doctor_receivables.execute({"agreement": self.owed})[1])

