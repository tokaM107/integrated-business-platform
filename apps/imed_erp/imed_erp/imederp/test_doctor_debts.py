# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A doctor's negative balance stays a debt on him (DOC-20): it shows on the Doctor Debts report with its age, with
# the app's platform fees not collected yet, and the next amount he earns pays it off before anything is paid to
# him. From the doctor's ledger only; rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_doctor_debts

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.book_edition.test_book_edition import make_doctor
from imed_erp.imederp.report.doctor_debts.doctor_debts import execute

LEDGER = "Doctor Ledger Entry"
AS_OF = "2026-10-15"
TREASURY = "الخزينة الرئيسية - MMG"
# Platform fees collected from a doctor go into the app's treasury (APP-06).
APP_TREASURY = "خزينة تطبيق BA Plus - MMG"


class IntegrationTestDoctorDebts(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("debts_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="debts_test")

	def agreement(self, agreement_type, doctor="_Test Debt Doctor"):
		return (
			frappe.get_doc(
				{
					"doctype": "Doctor Agreement",
					"agreement_name": f"_Test Debts {agreement_type} {frappe.generate_hash(length=6)}",
					"doctor": make_doctor(doctor),
					"agreement_type": agreement_type,
					"start_date": "2026-01-01",
					"settlement_cycle": "Term",
					"terms": [{"valid_from": "2026-01-01", "amount_per_copy": 80}],
				}
			)
			.insert()
			.submit()
			.name
		)

	def entry(self, agreement, entry_type, amount, entry_date, **values):
		doc = frappe.get_doc(
			{"doctype": LEDGER, "agreement": agreement, "entry_type": entry_type, "amount": amount, "entry_date": entry_date, **values}
		).insert()
		doc.submit()
		return doc

	def debts(self, as_of=AS_OF, **filters):
		return {row["agreement"]: row for row in execute({"as_of": as_of, **filters})[1]}

	def test_a_negative_balance_is_a_debt_with_its_age(self):
		books = self.agreement("Books")
		self.entry(books, "Accrual", 200, "2026-09-05")
		self.entry(books, "Unsold Copies Charge", 500, "2026-09-10")
		row = self.debts()[books]
		self.assertEqual(
			(row["debt"], str(row["since"]), row["age"], row["age_31-60"], row.get("age_0-30")),
			(300, "2026-09-10", 35, 300, None),
		)
		self.assertEqual(frappe.db.get_value("Doctor Agreement", books, "balance"), -300)

	def test_what_the_doctor_earns_next_pays_off_the_debt_first(self):
		books = self.agreement("Books")
		self.entry(books, "Accrual", 200, "2026-09-05")
		self.entry(books, "Unsold Copies Charge", 500, "2026-09-10")
		# 240 earned on copies sold: 60 of the debt is left, still owed since 10 September.
		self.entry(books, "Accrual", 240, "2026-10-01")
		row = self.debts()[books]
		self.assertEqual((row["debt"], str(row["since"])), (60, "2026-09-10"))
		# Nothing is paid to him while he owes.
		self.assertRaisesRegex(frappe.ValidationError, "more than that", self.entry, books, "Payout", 10, AS_OF, treasury=TREASURY)

		# 100 more: the debt is paid off and 40 is his, which is all he can be paid.
		self.entry(books, "Accrual", 100, "2026-10-05")
		self.assertNotIn(books, self.debts())
		self.assertRaisesRegex(frappe.ValidationError, "more than that", self.entry, books, "Payout", 41, AS_OF, treasury=TREASURY)
		self.entry(books, "Payout", 40, AS_OF, treasury=TREASURY)

	def test_platform_fees_not_collected_yet(self):
		# An app agreement's balance is what the doctor owes; a collection pays off the oldest fees first.
		app = self.agreement("App")
		self.entry(app, "Accrual", 150, "2026-09-05")
		self.entry(app, "Accrual", 100, "2026-10-10")
		self.entry(app, "Collection", 120, "2026-10-12", treasury=APP_TREASURY)
		row = self.debts()[app]
		self.assertEqual(
			(row["debt"], str(row["since"]), row["age_31-60"], row["age_0-30"]),
			(130, "2026-09-05", 30, 100),
		)

	def test_as_of_a_date_and_for_one_doctor(self):
		books = self.agreement("Books")
		self.entry(books, "Unsold Copies Charge", 70, "2026-09-10")
		self.entry(books, "Accrual", 70, "2026-10-01")
		self.assertEqual(self.debts(as_of="2026-09-30")[books]["debt"], 70)
		self.assertNotIn(books, self.debts())

		other = self.agreement("Books", doctor="_Test Other Debt Doctor")
		self.entry(other, "Unsold Copies Charge", 20, "2026-09-10")
		self.assertEqual(list(self.debts(doctor="_Test Other Debt Doctor")), [other])

	def test_a_doctor_who_is_owed_is_not_listed(self):
		books = self.agreement("Books")
		self.entry(books, "Accrual", 50, "2026-09-05")
		self.assertNotIn(books, self.debts())

	def test_only_the_accounts_read_it(self):
		roles = {r.role for r in frappe.get_doc("Report", "Doctor Debts").roles}
		self.assertEqual(roles, {"System Manager", "Accounts Manager"})
