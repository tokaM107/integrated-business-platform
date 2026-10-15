# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Doctor Receivables (RPT-08) and Doctor Debts (RPT-10): figures read from the doctor's ledger and, for platform
# fees, from the app subscriptions, worked out by hand below. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_doctor_reports

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctor_balances import age_debt, ageing_buckets
from imed_erp.imederp.doctype.book_edition.test_book_edition import PAPER_COST, make_agreement, make_doctor
from imed_erp.imederp.report.doctor_debts import doctor_debts
from imed_erp.imederp.report.doctor_receivables import doctor_receivables

# A test module outside a doctype folder builds no "_Test ..." records; keep it here, not under a doctype.
MAWASAH = "مكتبة المواساة - MMG"
APP = "تطبيق BA Plus - MMG"
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
		cls.entry(cls.owed, "2026-10-01", "Payout", 600)
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
				"agreement": agreement,
				"course": "_Test Course",
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

	def debts(self, **filters):
		return {row["agreement"]: row for row in doctor_debts.execute(frappe._dict({"to_date": AS_ON, **filters}))[1]}

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
		# The edition's accrual is Mawasah's; the rest (an accrual and a payout with no sale or edition) is not.
		self.assertEqual(by_branch, {MAWASAH: 1000, None: -150})
		self.assertEqual(sum(by_branch.values()), 850)
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

	# ---------- RPT-10 ----------

	def test_a_negative_books_balance_is_a_debt_aged_from_the_charge(self):
		row = self.debts()[self.negative]
		self.assertEqual((row["raised"], row["paid"], row["outstanding"]), (300, 100, 200))
		self.assertEqual(str(row["oldest"]), "2026-09-01")
		# 44 days on 15 Oct: in 31-60.
		self.assertEqual([row[f"range{i}"] for i in range(1, 5)], [0, 200, 0, 0])
		self.assertEqual(frappe.db.get_value("Doctor Agreement", self.negative, "balance"), -200)

	def test_uncollected_platform_fees_oldest_paid_first(self):
		row = self.debts()[self.app]
		self.assertEqual((row["raised"], row["paid"], row["outstanding"]), (450, 300, 150))
		self.assertEqual(str(row["oldest"]), "2026-09-20")
		self.assertEqual([row[f"range{i}"] for i in range(1, 5)], [150, 0, 0, 0])

	def test_a_fee_in_the_ledger_is_not_counted_twice(self):
		self.assertEqual(self.debts()[self.app_in_ledger]["outstanding"], 170)

	def test_debts_leave_out_what_is_owed_to_the_doctor(self):
		self.assertNotIn(self.owed, self.debts())

	def test_debts_on_an_earlier_date_and_by_type(self):
		# On 15 Sep, the 20 Sep fee was not due yet, and the 1 Jul one was not collected.
		self.assertEqual(self.debts(to_date="2026-09-15")[self.app]["outstanding"], 250)
		self.assertEqual(set(self.debts(agreement_type="App")) & {self.negative, self.owed}, set())

	def test_custom_ageing_ranges(self):
		row = doctor_debts.execute(frappe._dict({"to_date": AS_ON, "agreement": self.negative, "range": "15, 45"}))
		columns = [c["label"] for c in row[0] if c["fieldname"].startswith("range")]
		self.assertEqual(columns, ["0-15", "16-45", "46+"])
		self.assertEqual([row[1][0][f"range{i}"] for i in range(1, 4)], [0, 200, 0])

	# ---------- Who ----------

	def test_only_those_who_may_read_the_doctors_accounts(self):
		for user in ("raghad@imed.local", "sara@imed.local", "hr@imed.local"):
			frappe.set_user(user)
			self.assertRaises(frappe.PermissionError, doctor_receivables.execute, {})
			self.assertRaises(frappe.PermissionError, doctor_debts.execute, {})
		frappe.set_user("accountant@imed.local")
		self.assertTrue(doctor_receivables.execute({"agreement": self.owed})[1])


class TestAgeDebt(IntegrationTestCase):
	def test_payments_settle_the_oldest_part_and_overpayment_waits_for_the_next_debt(self):
		self.assertEqual(age_debt([("2026-01-01", 100), ("2026-02-01", 50), ("2026-03-01", -120)]), [(frappe.utils.getdate("2026-02-01"), 30)])
		# Paid 80 before anything was owed: set against the next debt.
		self.assertEqual(age_debt([("2026-01-01", -80), ("2026-02-01", 100)]), [(frappe.utils.getdate("2026-02-01"), 20)])
		self.assertEqual(age_debt([("2026-01-01", 100), ("2026-01-02", -100)]), [])

	def test_buckets(self):
		debts = [(frappe.utils.getdate("2026-10-14"), 10), (frappe.utils.getdate("2026-08-01"), 20), (frappe.utils.getdate("2026-01-01"), 30)]
		self.assertEqual(ageing_buckets(debts, "2026-10-15", [30, 60, 90]), [10, 0, 20, 30])
