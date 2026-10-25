# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The owner's figures (QA-06, QA-18; imederp/owner_dashboard.py): for a stated stretch of time, from the ledger, and
# never counting a booking that has not happened. Every check is a difference before and after, so it holds on any
# site. Rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_owner_dashboard

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_last_day, add_days, today

from imed_erp.imederp import owner_dashboard as dashboard

COMPANY = "Mohamed Mamdouh group"
APP = "تطبيق BA Plus - MMG"
STUDIO = "استوديو X - MMG"
FEES = "إيراد رسوم المنصة - MMG"
TREASURY = "خزينة تطبيق BA Plus - MMG"
RAGHAD = "raghad@imed.local"


class IntegrationTestOwnerDashboard(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("owner_dashboard")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="owner_dashboard")

	def journal_entry(self, amount, posting_date):
		"""Fee revenue posted by journal entry, as the platform fees and the halls' revenue share are."""
		doc = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": COMPANY,
				"posting_date": posting_date,
				"accounts": [
					{"account": TREASURY, "debit_in_account_currency": amount, "cost_center": APP},
					{"account": FEES, "credit_in_account_currency": amount, "cost_center": APP},
				],
			}
		).insert()
		doc.submit()

	def test_revenue_posted_by_journal_entry_is_in_the_owner_s_figures(self):
		yesterday = add_days(today(), -1)
		before = (
			dashboard.revenue_yesterday()["value"],
			dashboard.revenue_by_business(yesterday, yesterday).get(APP, 0),
		)
		self.journal_entry(700, yesterday)
		# Today's posting is not yesterday's.
		self.journal_entry(50, today())
		self.assertEqual(dashboard.revenue_yesterday()["value"], before[0] + 700)
		self.assertEqual(dashboard.revenue_by_business(yesterday, yesterday).get(APP, 0), before[1] + 700)

	def booking(self, status, booking_date, hours=2, outstanding=0, sales_invoice=None):
		doc = frappe.get_doc(
			{
				"doctype": "Booking",
				"name": f"_Test Dashboard Booking {frappe.generate_hash(length=8)}",
				"cost_center": STUDIO,
				"booking_date": booking_date,
				"hours": hours,
				"status": status,
				"outstanding_amount": outstanding,
				"sales_invoice": sales_invoice,
			}
		)
		# Only what the figures read; the booking's own checks are tested in test_booking.py.
		doc.db_insert()
		return doc

	def test_the_held_bookings_of_this_month_count_the_tentative_ones_included(self):
		"""The studio's bookings come from XStudio, where one stays pending until its day (owner, 25 Oct 2026)."""
		before = dashboard.studio_bookings_this_month()["value"], dashboard.studio_hours_this_month()["value"]
		self.booking("Completed", today(), hours=3)
		self.booking("Confirmed with Deposit", today(), hours=1)
		self.booking("Tentative", get_last_day(today()), hours=2)  # still to come, this month
		# Not counted: cancelled, a no-show, another month.
		self.booking("Cancelled", today())
		self.booking("No Show", today())
		self.booking("Confirmed with Deposit", add_days(get_last_day(today()), 1))
		self.booking("Completed", add_days(today(), -400))
		self.assertEqual(
			(dashboard.studio_bookings_this_month()["value"], dashboard.studio_hours_this_month()["value"]),
			(before[0] + 3, before[1] + 6),
		)

	def test_qa18_unpaid_on_bookings_leaves_out_what_is_not_owed(self):
		before = dashboard.unpaid_on_bookings()
		self.booking("Confirmed with Deposit", today(), outstanding=300)
		# Still to come, tentative, or a no-show keeping its deposit: nothing owed yet.
		self.booking("Confirmed with Deposit", add_days(today(), 10), outstanding=1000)
		self.booking("Tentative", today(), outstanding=1000)
		self.booking("No Show", today(), outstanding=1000)
		self.assertEqual(dashboard.unpaid_on_bookings(), before + 300)

		# A completed booking is paid on its invoice: what the invoice still owes, not the booking's Remaining.
		invoice = frappe.get_all("Sales Invoice", filters={"docstatus": 1, "outstanding_amount": 0}, pluck="name", limit=1)
		if invoice:
			self.booking("Completed", today(), outstanding=500, sales_invoice=invoice[0])
			self.assertEqual(dashboard.unpaid_on_bookings(), before + 300)

	def test_only_the_accounts_read_the_figures(self):
		frappe.set_user(RAGHAD)
		self.assertRaises(frappe.PermissionError, dashboard.revenue_this_month)
