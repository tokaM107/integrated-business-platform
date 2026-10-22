# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The Owner Dashboard's yesterday (5.1, owner_yesterday.py) and the reports RPT-01 (Revenue by Period), RPT-02 (Profit
# Before and After Shared Costs) and RPT-05 (Outstanding Receivables), against documents made here and worked out by
# hand. Uses the real company, cost centers, items, treasury and expense categories (setup_core.py, setup_coa.py,
# setup_expenses.py); everything made here is rolled back after each test.
#
# Whatever else the site holds on the same days is kept out by measuring each figure before and after the documents
# are made (delta), or by a customer of the test's own.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_owner_reports

from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, getdate, today

from imed_erp.imederp import owner_yesterday
from imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading import get_machines
from imed_erp.imederp.report.outstanding_receivables import outstanding_receivables as rpt05
from imed_erp.imederp.report.profit_before_and_after_shared_costs import (
	profit_before_and_after_shared_costs as rpt02,
)
from imed_erp.imederp.report.revenue_by_period import revenue_by_period as rpt01
from imed_erp.imederp.sales_cancellation import REASON_FIELD

COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
ROOT = f"{COMPANY} - {ABBR}"
CENTER = f"سنتر Imed - {ABBR}"
HALLS = f"قاعات Imed - {ABBR}"
STUDIO = f"استوديو X - {ABBR}"
SHARED = f"مصروفات المقر المشتركة - {ABBR}"
AZARITA = f"مكتبة الأزاريطة - {ABBR}"
MAWASAH = f"مكتبة المواساة - {ABBR}"
TREASURY = f"الخزينة الرئيسية - {ABBR}"
RECEIPT = "/files/_test_owner_reports_receipt.png"
OWNER, ACCOUNTANT, RAGHAD = "owner@imed.local", "accountant@imed.local", "raghad@imed.local"
PAPER = "imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading.get_paper_cost"

# Days of the 2027-2028 fiscal year (Sep-Aug), far from the site's own documents. 5 Feb 2028 is a Saturday, the first
# day of the week in System Settings.
JAN_31, FEB_01, FEB_07 = "2028-01-31", "2028-02-01", "2028-02-07"


class OwnerReportsTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		# Only the File record is needed: an expense checks that its receipt was uploaded, not its content.
		if not frappe.db.exists("File", {"file_url": RECEIPT}):
			frappe.get_doc({"doctype": "File", "file_name": "receipt.png", "file_url": RECEIPT}).db_insert()
		cls.customer = cls.make_customer("Test Owner Reports Customer")

	@staticmethod
	def make_customer(name):
		if frappe.db.exists("Customer", name):
			return name
		return (
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_group": frappe.get_all(
						"Customer Group", filters={"is_group": 0, "name": ["!=", "طبيب"]}, pluck="name"
					)[0],
					"territory": frappe.get_all("Territory", filters={"is_group": 0}, pluck="name")[0],
				}
			)
			.insert()
			.name
		)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("owner_reports")
		# The site's expense numbering may be behind the expenses already there (its counter row missing): start this
		# test's numbers after them. Rolled back with the rest.
		prefix = f"EXP-{getdate(today()).year}-"
		last = frappe.db.sql("select max(name) from tabExpense where name like %s", prefix + "%")[0][0]
		if last:
			frappe.db.sql(
				"""insert into tabSeries (name, current) values (%(prefix)s, %(last)s)
				on duplicate key update current = greatest(current, %(last)s)""",
				{"prefix": prefix, "last": int(last.rsplit("-", 1)[1])},
			)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="owner_reports")

	# ---------------- documents ----------------
	def invoice(
		self, cost_center, amount, date, submit=True, customer=None, item_code="HALL-HOUR", booking=None
	):
		doc = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": customer or self.customer,
				"cost_center": cost_center,
				"set_posting_time": 1,
				"posting_date": date,
				"due_date": date,
				"disable_rounded_total": 1,
				"items": [{"item_code": item_code, "qty": 1, "rate": amount, "cost_center": cost_center}],
			}
		)
		if booking:
			doc.custom_booking = booking
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def cancel(self, doc):
		"""A sale is cancelled only with its reason (sales_cancellation.py)."""
		doc.set(REASON_FIELD, "Test")
		doc.cancel()
		return doc

	def pay(self, invoice, amount, date=None):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		entry = get_payment_entry("Sales Invoice", invoice.name, party_amount=amount)
		entry.update(
			{
				"posting_date": date or invoice.posting_date,
				"paid_to": TREASURY,
				"paid_amount": amount,
				"received_amount": amount,
			}
		)
		entry.references[0].allocated_amount = amount
		entry.insert()
		entry.submit()
		return entry

	def advance(self, amount, date, customer=None):
		"""Money received from a customer, set against no invoice."""
		entry = frappe.new_doc("Payment Entry")
		entry.update(
			{
				"payment_type": "Receive",
				"company": COMPANY,
				"posting_date": date,
				"party_type": "Customer",
				"party": customer or self.customer,
				"paid_to": TREASURY,
				"paid_amount": amount,
				"received_amount": amount,
				"cost_center": HALLS,
			}
		)
		entry.setup_party_account_field()
		entry.set_missing_values()
		entry.insert()
		entry.submit()
		return entry

	def expense(self, cost_center, amount, date, submit=True):
		# ERPNext caches the cost center allocation per request; each expense here stands for a request of its own.
		getattr(frappe.local, "request_cache", {}).clear()
		doc = frappe.get_doc(
			{
				"doctype": "Expense",
				"posting_date": date,
				"activity": cost_center,
				"expense_category": "الكهرباء",
				"amount": amount,
				"treasury": TREASURY,
				"receipt": RECEIPT,
			}
		).insert()
		if submit:
			doc.submit()
		return doc

	def rule(self, shares):
		"""An Allocation Rule from the first day it is accepted on (after every shared expense and rule)."""
		last_expense = frappe.db.get_value(
			"Expense", {"activity": SHARED, "docstatus": 1}, "posting_date", order_by="posting_date desc"
		)
		last_rule = frappe.db.get_value(
			"Allocation Rule",
			{"main_cost_center": SHARED, "docstatus": 1},
			"valid_from",
			order_by="valid_from desc",
		)
		valid_from = max(
			[getdate(today())] + [getdate(add_days(d, 1)) for d in (last_expense, last_rule) if d]
		)
		doc = frappe.get_doc(
			{
				"doctype": "Allocation Rule",
				"main_cost_center": SHARED,
				"valid_from": valid_from,
				"businesses": [{"cost_center": c, "percentage": p} for c, p in shares],
			}
		).insert()
		doc.submit()
		return doc

	def booking(self, name, **values):
		"""A booking row as the booking screen leaves it, without its pricing (the dashboard and RPT-05 only read it)."""
		doc = frappe.get_doc(
			{
				"doctype": "Booking",
				"name": name,
				"customer": self.customer,
				"source": "Manual",
				"status": "Tentative",
				"hours": 0,
				"total_amount": 0,
				"paid_amount": 0,
				"outstanding_amount": 0,
				**values,
			}
		)
		doc.db_insert()
		return doc

	def gl_income(self, from_date, to_date, cost_centers=None):
		"""Revenue straight from the ledger, read on its own, to reconcile against."""
		condition = " and gl.cost_center in %(ccs)s" if cost_centers else ""
		return flt(
			frappe.db.sql(
				f"""select coalesce(sum(gl.credit - gl.debit), 0) from `tabGL Entry` gl
				join `tabAccount` acc on acc.name = gl.account
				where gl.company = %(company)s and gl.is_cancelled = 0 and acc.root_type = 'Income'
					and gl.posting_date between %(from)s and %(to)s{condition}""",
				{"company": COMPANY, "from": from_date, "to": to_date, "ccs": tuple(cost_centers or [])},
			)[0][0],
			2,
		)


# ======================================================================================================================
class IntegrationTestOwnerYesterday(OwnerReportsTestCase):
	def test_yesterday_is_the_calendar_day_before(self):
		for today_, yesterday in (
			("2026-10-22", "2026-10-21"),
			("2026-11-01", "2026-10-31"),  # a month boundary
			("2027-01-01", "2026-12-31"),  # a year boundary
			("2028-03-01", "2028-02-29"),  # a leap day
		):
			with self.subTest(today=today_):
				period = owner_yesterday.report_day(today_)
				self.assertEqual(period.day, getdate(yesterday))
				self.assertEqual(period.start, datetime.combine(getdate(yesterday), datetime.min.time()))
				self.assertEqual(period.end, datetime.combine(getdate(today_), datetime.min.time()))
		# Without a date, the site's today (System Settings time zone).
		self.assertEqual(owner_yesterday.report_day().day, getdate(add_days(today(), -1)))

	def money_of(self, day):
		return {row["cost_center"]: row for row in owner_yesterday.money(day)["rows"]}

	def test_each_business_with_approved_documents_only(self):
		day = JAN_31
		before = self.money_of(day)

		self.invoice(HALLS, 1000, day)  # counted
		self.invoice(HALLS, 700, day, submit=False)  # a draft: not counted
		self.cancel(self.invoice(STUDIO, 300, day))  # cancelled, with its reversal: not counted
		studio = self.invoice(STUDIO, 400, day)  # counted once, though it is also paid
		self.pay(studio, 400)
		self.invoice(AZARITA, 50, day)
		self.expense(AZARITA, 120, day)  # counted
		self.expense(MAWASAH, 90, day, submit=False)  # not approved: not counted

		after = self.money_of(day)
		delta = {
			cc: {key: flt(after[cc][key] - before[cc][key], 2) for key in ("revenue", "expenses", "net")}
			for cc in after
		}
		self.assertEqual(delta[HALLS], {"revenue": 1000, "expenses": 0, "net": 1000})
		self.assertEqual(delta[STUDIO], {"revenue": 400, "expenses": 0, "net": 400})
		self.assertEqual(delta[AZARITA], {"revenue": 50, "expenses": 120, "net": -70})
		self.assertEqual(delta[MAWASAH], {"revenue": 0, "expenses": 0, "net": 0})
		# Every activity has its row, also one with nothing that day.
		self.assertTrue({HALLS, STUDIO, AZARITA, MAWASAH, SHARED} <= set(after))

	def test_bookings_by_their_day_not_the_day_they_were_made(self):
		day = getdate("2028-01-20")
		period = owner_yesterday.report_day(add_days(day, 1))
		before = owner_yesterday.bookings(period)
		made = datetime(2028, 1, 20, 10, 0)
		older = datetime(2028, 1, 2, 10, 0)
		self.booking(
			"_TBK-1",
			resource_type="Hall",
			status="Completed",
			booking_date=day,
			cost_center=HALLS,
			creation=older,
		)
		self.booking(
			"_TBK-2",
			resource_type="Hall",
			status="Cancelled",
			booking_date=day,
			cost_center=HALLS,
			creation=older,
		)
		self.booking(
			"_TBK-3",
			resource_type="Studio Service",
			status="Completed",
			hours=3,
			booking_date=day,
			cost_center=STUDIO,
			creation=older,
		)
		self.booking(
			"_TBK-4",
			resource_type="Studio Service",
			status="Confirmed with Deposit",
			hours=2,
			booking_date=day,
			cost_center=STUDIO,
			creation=older,
		)
		self.booking(
			"_TBK-5",
			resource_type="Studio Service",
			status="No Show",
			hours=4,
			booking_date=day,
			cost_center=STUDIO,
			creation=older,
		)
		# Made yesterday for a later day: counted as made, not as held.
		self.booking(
			"_TBK-6",
			resource_type="Hall",
			status="Tentative",
			booking_date=add_days(day, 10),
			cost_center=HALLS,
			creation=made,
		)
		after = owner_yesterday.bookings(period)

		def grew(key, sub=None):
			return (after[key][sub] - before[key][sub]) if sub else flt(after[key] - before[key], 2)

		self.assertEqual(
			(grew("halls", "held"), grew("halls", "completed"), grew("halls", "cancelled")), (1, 1, 1)
		)
		self.assertEqual(
			(grew("studio", "held"), grew("studio", "completed"), grew("studio", "no_show")), (2, 1, 1)
		)
		# Booked: not cancelled, not a no-show (3 + 2); delivered: completed (3).
		self.assertEqual(grew("studio_hours_booked"), 5)
		self.assertEqual(grew("studio_hours_delivered"), 3)
		self.assertEqual(grew("still_open"), 1)
		self.assertEqual(grew("made_yesterday"), 1)

	@patch(PAPER, return_value=0.30)
	def test_printing_warns_instead_of_showing_zero(self, _paper):
		day = "2028-01-21"
		frappe.db.delete("Daily Counter Reading", {"reading_date": day})
		if not get_machines(AZARITA):
			frappe.get_doc(
				{
					"doctype": "Printing Machine",
					"machine_name": "_Test Yesterday Epson",
					"machine_type": "Epson",
					"cost_center": AZARITA,
					"warehouse": f"مخزن الأزاريطة - {ABBR}",
				}
			).insert()
		label = frappe.db.get_value("Cost Center", AZARITA, "cost_center_name")

		printing = owner_yesterday.printing(day)
		self.assertEqual(printing["state"], "ok")
		azarita = next(lib for lib in printing["libraries"] if lib["library"] == label)
		self.assertIsNone(azarita["reading"])
		self.assertIn(frappe._("{0}: no counter reading for the day.").format(label), printing["warnings"])

		# The day's counters: up by 40, nothing sold, so a difference of 40 and a warning.
		doc = frappe.new_doc("Daily Counter Reading")
		doc.update({"branch": AZARITA, "reading_date": day})
		for row in get_machines(AZARITA):
			opening = row["opening_reading"] if row["opening_reading"] is not None else 1000
			row.update({"opening_reading": opening, "closing_reading": opening})
			doc.append("machines", row)
		doc.machines[0].closing_reading = doc.machines[0].opening_reading + 40
		doc.insert()
		doc.submit()

		printing = owner_yesterday.printing(day)
		azarita = next(lib for lib in printing["libraries"] if lib["library"] == label)
		self.assertEqual(azarita["reading"], doc.name)
		self.assertEqual((azarita["consumed"], azarita["sold"], azarita["variance"]), (40, 0, 40))
		first = azarita["machines"][0]
		self.assertEqual(first["closing"] - first["opening"], first["consumed"])
		self.assertTrue(any(label in w and "40" in w for w in printing["warnings"]))

	def test_no_machine_is_not_configured(self):
		frappe.db.set_value("Printing Machine", {"disabled": 0}, "disabled", 1)
		self.assertEqual(owner_yesterday.printing("2028-01-21")["state"], "not_configured")

	def test_app_fees_without_agreements_are_not_configured(self):
		frappe.db.delete("Doctor Agreement", {"agreement_type": "App"})
		self.assertEqual(owner_yesterday.app_fees("2028-01-21"), {"state": "not_configured"})

	def test_a_system_without_records_is_never_ok(self):
		systems = {s["name"]: s for s in owner_yesterday.systems()}
		self.assertEqual(systems[frappe._("Booking system import")]["state"], "not_configured")
		if not frappe.db.count("Data Import"):
			self.assertEqual(systems[frappe._("File imports")]["state"], "unknown")
		from imed_erp.assistant.providers import get_provider

		if not get_provider().connected:
			self.assertEqual(systems[frappe._("AI assistant")]["state"], "not_configured")
		# A failed file import is reported, with its kind and status; nothing of the file itself.
		frappe.get_doc(
			{
				"doctype": "Data Import",
				"name": "_Test Failed Import",
				"reference_doctype": "Customer",
				"import_type": "Insert New Records",
				"status": "Error",
			}
		).db_insert()
		imports = owner_yesterday.file_imports()
		self.assertEqual(imports["state"], "error")
		self.assertEqual(imports["last_status"], "Error")

	def test_only_the_owner_sees_yesterday(self):
		for user in (ACCOUNTANT, RAGHAD):
			with self.subTest(user=user):
				frappe.set_user(user)
				self.assertRaises(frappe.PermissionError, owner_yesterday.get_yesterday)
		frappe.set_user(OWNER)
		self.assertIn("money", owner_yesterday.get_yesterday())

	def test_the_money_endpoints_refuse_a_branch_manager(self):
		# The workspace's roles hide it; each figure is also refused by its own endpoint (a direct call or URL).
		from imed_erp.imederp import owner_figures

		frappe.set_user(RAGHAD)
		for method in (
			"cash_in_boxes",
			"revenue_this_month",
			"expenses_this_month",
			"net_this_month",
			"owed_to_us",
			"we_owe",
		):
			with self.subTest(method=method):
				self.assertRaises(frappe.PermissionError, getattr(owner_figures, method))
		self.assertRaises(frappe.PermissionError, owner_yesterday.get_yesterday)
		self.assertFalse(frappe.get_doc("Report", "Cash Box Balances").is_permitted())
		for report in (
			"Revenue by Period",
			"Profit Before and After Shared Costs",
			"Outstanding Receivables",
		):
			with self.subTest(report=report):
				self.assertFalse(frappe.get_doc("Report", report).is_permitted())

	def test_the_dashboard_is_the_owner_s_workspace(self):
		roles = frappe.get_all(
			"Has Role", filters={"parenttype": "Workspace", "parent": "Owner Dashboard"}, pluck="role"
		)
		self.assertEqual(roles, ["Super Admin"])
		from frappe.desk.desktop import Workspace

		page = {"name": "Owner Dashboard", "title": "Owner Dashboard", "public": 1}
		for user, allowed in ((RAGHAD, False), (ACCOUNTANT, False), (OWNER, True)):
			with self.subTest(user=user):
				frappe.set_user(user)
				self.assertEqual(bool(Workspace(page, minimal=True).is_permitted()), allowed)


# ======================================================================================================================
class IntegrationTestRevenueByPeriod(OwnerReportsTestCase):
	FROM, TO = "2028-01-01", "2028-02-29"

	def run_report(self, periodicity, **filters):
		columns, data, *_rest = rpt01.execute(
			{"from_date": self.FROM, "to_date": self.TO, "periodicity": periodicity, **filters}
		)
		return columns, {row["cost_center"]: row for row in data}

	def deltas(self, periodicity, make, **filters):
		_columns, before = self.run_report(periodicity, **filters)
		make()
		columns, after = self.run_report(periodicity, **filters)
		keys = [c["fieldname"] for c in columns if c["fieldname"].startswith("p_")] + ["total"]
		return {
			cc: {
				k: flt(after[cc][k] - before[cc][k], 2) for k in keys if flt(after[cc][k] - before[cc][k], 2)
			}
			for cc in after
		}

	def make_sales(self):
		self.invoice(HALLS, 100, JAN_31)
		self.invoice(HALLS, 200, FEB_01)
		self.invoice(STUDIO, 50, FEB_07)
		self.invoice(AZARITA, 30, FEB_07)

	def test_daily_weekly_monthly(self):
		monthly = self.deltas("Monthly", self.make_sales)
		self.assertEqual(monthly[HALLS], {"p_20280101": 100, "p_20280201": 200, "total": 300})
		self.assertEqual(monthly[STUDIO], {"p_20280201": 50, "total": 50})
		# The group adds up its branches; the top row everything.
		self.assertEqual(monthly[CENTER], {"p_20280101": 100, "p_20280201": 250, "total": 350})
		self.assertEqual(monthly[ROOT], {"p_20280101": 100, "p_20280201": 280, "total": 380})

	def test_weeks_start_on_the_system_s_first_day(self):
		frappe.db.set_single_value("System Settings", "first_day_of_the_week", "Saturday")
		weekly = self.deltas("Weekly", self.make_sales)
		# 31 Jan (Mon) and 1 Feb (Tue) are in the week of Sat 29 Jan; 7 Feb (Mon) in the week of Sat 5 Feb.
		self.assertEqual(weekly[HALLS], {"p_20280129": 300, "total": 300})
		self.assertEqual(weekly[ROOT], {"p_20280129": 300, "p_20280205": 80, "total": 380})
		# The first week is cut to the dates chosen: it starts on 1 Jan.
		columns, _data = self.run_report("Weekly")
		self.assertEqual(columns[2]["fieldname"], "p_20280101")

	def test_daily(self):
		daily = self.deltas("Daily", self.make_sales)
		self.assertEqual(daily[HALLS], {"p_20280131": 100, "p_20280201": 200, "total": 300})
		columns, _data = self.run_report("Daily")
		self.assertEqual(len([c for c in columns if c["fieldname"].startswith("p_")]), 60)

	def test_business_and_branch_filters(self):
		_columns, data = self.run_report("Monthly", cost_center=HALLS)
		self.assertEqual(set(data), {HALLS})
		_columns, data = self.run_report("Monthly", cost_center=CENTER)
		self.assertEqual(set(data), {CENTER, HALLS, STUDIO, SHARED})
		delta = self.deltas("Monthly", self.make_sales, cost_center=f"مكتبات 2Be Doctor - {ABBR}")
		self.assertEqual(delta[AZARITA], {"p_20280201": 30, "total": 30})
		self.assertNotIn(HALLS, delta)

	def test_status_returns_and_no_double_counting(self):
		def make():
			paid = self.invoice(HALLS, 500, FEB_01)
			self.pay(paid, 500)  # the payment is not revenue again
			self.invoice(HALLS, 70, FEB_01, submit=False)  # draft
			self.cancel(self.invoice(HALLS, 90, FEB_01))  # cancelled
			from erpnext.controllers.sales_and_purchase_return import make_return_doc

			credit = make_return_doc("Sales Invoice", paid.name)
			credit.posting_date = FEB_07
			credit.set_posting_time = 1
			credit.items[0].qty = -1
			credit.items[0].rate = 120
			credit.insert()
			credit.submit()

		delta = self.deltas("Monthly", make)
		self.assertEqual(delta[HALLS], {"p_20280201": 380, "total": 380})

	def test_totals_reconcile_with_the_ledger(self):
		self.make_sales()
		_columns, data = self.run_report("Monthly")
		self.assertEqual(data[ROOT]["total"], self.gl_income(self.FROM, self.TO))
		self.assertEqual(data[CENTER]["total"], self.gl_income(self.FROM, self.TO, [HALLS, STUDIO, SHARED]))
		periods = [k for k in data[ROOT] if k.startswith("p_")]
		self.assertEqual(flt(sum(data[ROOT][k] for k in periods), 2), data[ROOT]["total"])

	def test_wrong_filters_are_refused(self):
		for filters in (
			{"from_date": "2028-02-01", "to_date": "2028-01-01", "periodicity": "Monthly"},
			{"from_date": "2028-01-01", "to_date": "2028-02-01", "periodicity": "Hourly"},
			{"from_date": "2020-01-01", "to_date": "2028-02-01", "periodicity": "Daily"},
			{
				"from_date": "2028-01-01",
				"to_date": "2028-02-01",
				"periodicity": "Daily",
				"cost_center": "No Such - XX",
			},
		):
			with self.subTest(filters=filters):
				self.assertRaises(frappe.ValidationError, rpt01.execute, filters)

	def test_owner_and_accountant_only(self):
		frappe.set_user(RAGHAD)
		self.assertRaises(frappe.PermissionError, self.run_report, "Monthly")
		frappe.set_user(ACCOUNTANT)
		self.run_report("Monthly")


# ======================================================================================================================
class IntegrationTestProfitBeforeAfterSharedCosts(OwnerReportsTestCase):
	def run_report(self, from_date, to_date, **filters):
		_columns, data, message, _chart, summary = rpt02.execute(
			{"from_date": from_date, "to_date": to_date, **filters}
		)
		return {row["cost_center"]: row for row in data}, message, summary

	def result(self, from_date, to_date, cost_center=None):
		return rpt02.get_result(
			rpt02.subtree(cost_center), getdate(from_date), getdate(to_date), not cost_center
		)

	FIELDS = (
		"revenue",
		"direct_expenses",
		"shared_before",
		"profit_before",
		"shared_allocated",
		"shared_unallocated",
		"profit_after",
	)

	def deltas(self, from_date, to_date, make, **filters):
		before, *_ = self.run_report(from_date, to_date, **filters)
		make()
		after, message, summary = self.run_report(from_date, to_date, **filters)
		delta = {cc: {f: flt(after[cc][f] - before[cc][f], 2) for f in self.FIELDS} for cc in after}
		return delta, message, summary

	def test_without_shared_costs(self):
		day = JAN_31

		def make():
			self.invoice(HALLS, 800, day)
			self.expense(HALLS, 300, day)

		delta, _message, _summary = self.deltas(day, day, make)
		self.assertEqual(
			delta[HALLS],
			{
				"revenue": 800,
				"direct_expenses": 300,
				"shared_before": 0,
				"profit_before": 500,
				"shared_allocated": 0,
				"shared_unallocated": 0,
				"profit_after": 500,
			},
		)

	def test_shared_costs_split_across_businesses(self):
		rule = self.rule([(HALLS, 70), (STUDIO, 30)])
		day = rule.valid_from

		def make():
			self.invoice(HALLS, 500, day)
			self.invoice(STUDIO, 300, day)
			self.expense(HALLS, 200, day)  # the halls' own
			self.expense(SHARED, 1000, day)  # split 700 / 300 by the rule

		delta, _message, _summary = self.deltas(day, day, make)
		self.assertEqual(
			delta[HALLS],
			{
				"revenue": 500,
				"direct_expenses": 200,
				"shared_before": 0,
				"profit_before": 300,
				"shared_allocated": 700,
				"shared_unallocated": 0,
				"profit_after": -400,
			},
		)
		self.assertEqual(
			delta[STUDIO],
			{
				"revenue": 300,
				"direct_expenses": 0,
				"shared_before": 0,
				"profit_before": 300,
				"shared_allocated": 300,
				"shared_unallocated": 0,
				"profit_after": 0,
			},
		)
		# Before allocation the 1,000 is the shared premises' own; after, it is on the businesses, not there again.
		self.assertEqual(
			delta[SHARED],
			{
				"revenue": 0,
				"direct_expenses": 0,
				"shared_before": 1000,
				"profit_before": -1000,
				"shared_allocated": 0,
				"shared_unallocated": 0,
				"profit_after": 0,
			},
		)
		self.assertEqual(delta[CENTER]["profit_before"], delta[CENTER]["profit_after"])
		self.assertEqual(delta[CENTER]["profit_after"], -400)

	def test_totals_reconcile_with_the_ledger(self):
		rule = self.rule([(HALLS, 60), (STUDIO, 40)])
		day = rule.valid_from
		self.invoice(HALLS, 900, day)
		self.expense(SHARED, 500, day)
		result = self.result(day, day)
		self.assertTrue(result.reconciles)
		top = result.totals
		self.assertEqual(top["profit_before"], top["profit_after"])
		ledger_profit = flt(
			frappe.db.sql(
				"""select coalesce(sum(gl.credit - gl.debit), 0) from `tabGL Entry` gl
				join `tabAccount` acc on acc.name = gl.account
				where gl.company = %s and gl.is_cancelled = 0 and acc.root_type in ('Income', 'Expense')
					and gl.posting_date = %s and gl.voucher_type != 'Period Closing Voucher'""",
				(COMPANY, day),
			)[0][0],
			2,
		)
		self.assertEqual(top["profit_after"], ledger_profit)
		# One branch shown: the two profits differ by exactly the shared costs split onto it.
		halls = self.result(day, day, HALLS)
		self.assertTrue(halls.reconciles)
		self.assertEqual(
			flt(halls.totals["profit_before"] - halls.totals["profit_after"], 2),
			halls.totals["shared_allocated"],
		)

	def test_a_period_no_rule_covered_is_incomplete(self):
		# Before the first rule (the site's starts on 1 Nov 2026), a shared expense stays on the shared cost center.
		first_rule = frappe.db.get_value(
			"Cost Center Allocation",
			{"main_cost_center": SHARED, "docstatus": 1},
			"valid_from",
			order_by="valid_from asc",
		)
		day = add_days(first_rule, -3) if first_rule else JAN_31
		delta, message, summary = self.deltas(day, day, lambda: self.expense(SHARED, 400, day))
		self.assertEqual(delta[SHARED]["shared_before"], 400)
		self.assertEqual(delta[SHARED]["shared_unallocated"], 400)
		self.assertEqual(delta[SHARED]["profit_after"], -400)
		self.assertEqual(delta[HALLS]["shared_allocated"], 0)
		self.assertGreaterEqual(self.result(day, day).unallocated, 400)
		self.assertIn(frappe._("Shared Costs Not Allocated"), [s["label"] for s in summary])
		self.assertTrue(message)
		self.assertTrue(self.result(day, day).reconciles)

	def test_a_cancelled_shared_expense_is_gone_from_both(self):
		rule = self.rule([(HALLS, 50), (STUDIO, 50)])
		day = rule.valid_from
		delta, *_ = self.deltas(day, day, lambda: self.expense(SHARED, 600, day).cancel())
		self.assertEqual(
			{f: delta[SHARED][f] for f in ("shared_before", "shared_unallocated")},
			{"shared_before": 0, "shared_unallocated": 0},
		)
		self.assertEqual(delta[HALLS]["shared_allocated"], 0)

	def test_owner_and_accountant_only(self):
		frappe.set_user(RAGHAD)
		self.assertRaises(frappe.PermissionError, self.run_report, JAN_31, JAN_31)


# ======================================================================================================================
class IntegrationTestOutstandingReceivables(OwnerReportsTestCase):
	def rows(self, **filters):
		_columns, data, *_rest = rpt05.execute({"customer": self.customer, **filters})
		return [row for row in data if not row.get("is_subtotal")], [
			row for row in data if row.get("is_subtotal")
		]

	def by_reference(self, **filters):
		return {row["voucher_no"]: row for row in self.rows(**filters)[0]}

	def test_unpaid_partly_paid_and_paid(self):
		unpaid = self.invoice(HALLS, 1000, JAN_31)
		partly = self.invoice(HALLS, 1000, JAN_31)
		self.pay(partly, 400)
		paid = self.invoice(STUDIO, 300, JAN_31)
		self.pay(paid, 300)
		rows = self.by_reference()
		self.assertEqual(
			(rows[unpaid.name]["paid"], rows[unpaid.name]["outstanding"], rows[unpaid.name]["status_key"]),
			(0, 1000, "Unpaid"),
		)
		self.assertEqual(
			(rows[partly.name]["paid"], rows[partly.name]["outstanding"], rows[partly.name]["status_key"]),
			(400, 600, "Partly Paid"),
		)
		self.assertNotIn(paid.name, rows)
		self.assertEqual(set(self.by_reference(payment_status="Partly Paid")), {partly.name})
		# Due on 31 Jan 2028: not overdue yet.
		self.assertEqual(self.by_reference(payment_status="Overdue"), {})

	def test_cancelled_and_returned(self):
		cancelled = self.invoice(HALLS, 500, JAN_31)
		self.cancel(cancelled)
		returned = self.invoice(HALLS, 1000, JAN_31)
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		credit = make_return_doc("Sales Invoice", returned.name)
		credit.update({"set_posting_time": 1, "posting_date": FEB_01})  # a return comes after its sale
		credit.items[0].qty = -1
		credit.items[0].rate = 200
		if credit.meta.has_field("update_outstanding_for_self"):
			credit.update_outstanding_for_self = 0  # set against the invoice, as a return of part of it
		credit.insert()
		credit.submit()
		rows = self.by_reference()
		self.assertNotIn(cancelled.name, rows)
		self.assertEqual(rows[returned.name]["outstanding"], 800)
		self.assertNotIn(credit.name, rows)

	def test_an_advance_is_a_credit_not_owed(self):
		self.invoice(HALLS, 1000, JAN_31)
		entry = self.advance(300, JAN_31)
		rows, subtotals = self.rows()
		credit = next(row for row in rows if row["voucher_no"] == entry.name)
		self.assertEqual((credit["kind_key"], credit["outstanding"]), ("Credit", -300))
		totals = {row["kind"]: row["outstanding"] for row in subtotals}
		self.assertEqual(totals[frappe._("Total: {0}").format(rpt05.kind_label("Invoiced"))], 1000)
		self.assertEqual(totals[frappe._("Total: {0}").format(rpt05.kind_label("Credit"))], -300)

	def test_a_status_filter_leaves_credits_out(self):
		invoice = self.invoice(HALLS, 1000, JAN_31)
		entry = self.advance(300, JAN_31)
		shown = set(self.by_reference(payment_status="Unpaid"))
		self.assertIn(invoice.name, shown)
		self.assertNotIn(entry.name, shown)

	def test_a_wrong_date_is_refused(self):
		self.assertRaises(frappe.ValidationError, rpt05.execute, {"from_date": "not a date"})

	def test_a_booking_and_its_invoice_are_one_debt(self):
		# Not invoiced yet: listed apart, with its deposit, and not as a receivable.
		self.booking(
			"_TBK-OPEN",
			resource_type="Hall",
			status="Confirmed with Deposit",
			booking_date=JAN_31,
			cost_center=HALLS,
			total_amount=500,
			paid_amount=200,
			outstanding_amount=300,
		)
		# Invoiced: only its invoice, which names it.
		invoice = self.invoice(HALLS, 700, JAN_31)
		self.booking(
			"_TBK-DONE",
			resource_type="Hall",
			status="Completed",
			booking_date=JAN_31,
			cost_center=HALLS,
			total_amount=700,
			paid_amount=0,
			outstanding_amount=700,
			sales_invoice=invoice.name,
		)
		frappe.db.set_value("Sales Invoice", invoice.name, "custom_booking", "_TBK-DONE")
		# Cancelled: owes nothing.
		self.booking(
			"_TBK-GONE",
			resource_type="Hall",
			status="Cancelled",
			booking_date=JAN_31,
			cost_center=HALLS,
			total_amount=400,
			outstanding_amount=400,
		)

		rows, subtotals = self.rows()
		by_ref = {row["voucher_no"]: row for row in rows}
		self.assertEqual(
			(
				by_ref["_TBK-OPEN"]["kind_key"],
				by_ref["_TBK-OPEN"]["paid"],
				by_ref["_TBK-OPEN"]["outstanding"],
			),
			("Not Invoiced", 200, 300),
		)
		self.assertNotIn("_TBK-DONE", by_ref)
		self.assertNotIn("_TBK-GONE", by_ref)
		self.assertEqual(by_ref[invoice.name]["booking"], "_TBK-DONE")
		self.assertEqual(sum(1 for row in rows if row.get("booking") == "_TBK-DONE"), 1)
		totals = {row["kind"]: row["outstanding"] for row in subtotals}
		self.assertEqual(totals[frappe._("Total: {0}").format(rpt05.kind_label("Invoiced"))], 700)
		self.assertEqual(totals[frappe._("Total: {0}").format(rpt05.kind_label("Not Invoiced"))], 300)
		self.assertEqual(set(r["voucher_no"] for r in self.rows(kind="Invoiced")[0]), {invoice.name})

	def test_a_deposit_on_an_open_booking_is_not_counted_twice(self):
		self.booking(
			"_TBK-DEP",
			resource_type="Studio Service",
			status="Confirmed with Deposit",
			booking_date=JAN_31,
			cost_center=STUDIO,
			total_amount=600,
			paid_amount=250,
			outstanding_amount=350,
		)
		entry = self.advance(250, JAN_31)
		frappe.db.set_value("Payment Entry", entry.name, "custom_booking", "_TBK-DEP")
		by_ref = self.by_reference()
		self.assertNotIn(entry.name, by_ref)
		self.assertEqual(by_ref["_TBK-DEP"]["outstanding"], 350)

	def test_reconciles_with_the_payment_ledger(self):
		one = self.invoice(HALLS, 1000, JAN_31)
		two = self.invoice(STUDIO, 450, FEB_01)
		self.pay(two, 150)
		_rows, subtotals = self.rows(kind="Invoiced")
		ledger = flt(
			frappe.db.sql(
				"""select coalesce(sum(amount), 0) from `tabPayment Ledger Entry`
				where delinked = 0 and party_type = 'Customer' and party = %s and against_voucher_no in %s""",
				(self.customer, (one.name, two.name)),
			)[0][0],
			2,
		)
		self.assertEqual(subtotals[0]["outstanding"], ledger)
		self.assertEqual(ledger, 1300)

	def test_filters(self):
		self.invoice(HALLS, 100, JAN_31)
		self.invoice(STUDIO, 200, FEB_07)
		self.assertEqual({r["cost_center"] for r in self.rows(cost_center=STUDIO)[0]}, {STUDIO})
		self.assertEqual({r["cost_center"] for r in self.rows(cost_center=CENTER)[0]}, {HALLS, STUDIO})
		self.assertEqual(len(self.rows(from_date=FEB_01, to_date=FEB_07)[0]), 1)
		self.assertRaises(frappe.ValidationError, rpt05.execute, {"payment_status": "Whatever"})
		frappe.set_user(RAGHAD)
		self.assertRaises(frappe.PermissionError, rpt05.execute, {})


# ======================================================================================================================
class IntegrationTestReportsOpen(OwnerReportsTestCase):
	def test_each_report_runs_as_the_desk_runs_it(self):
		# By the report's name, as the page calls it: catches a report whose folder does not match its name.
		from frappe.desk.query_report import run

		for name, filters in (
			("Revenue by Period", {"from_date": JAN_31, "to_date": FEB_07, "periodicity": "Weekly"}),
			("Profit Before and After Shared Costs", {"from_date": JAN_31, "to_date": FEB_07}),
			("Outstanding Receivables", {}),
		):
			with self.subTest(report=name):
				frappe.set_user(OWNER)
				self.assertIn("result", run(name, filters=filters))
