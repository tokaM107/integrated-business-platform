# The owner's figures (requirements 5.1, RPT-01; QA-06, QA-18): Number Cards of type Custom call these methods
# (setup/setup_dashboard.py). Each figure is worked out on the server, for a stated stretch of time, so a card never
# adds up all time or counts what has not happened yet.
#
#   revenue and expenses   from the general ledger: every income or expense account, so the platform fees and the
#                          halls' revenue share (posted by journal entry) are in, not only sales invoices
#   bookings and hours     confirmed or completed bookings dated from the start of the month to today; a tentative
#                          booking or one still to come is not business done
#   unpaid on bookings     what is still owed on bookings up to today: a completed booking's invoice outstanding
#                          (it is paid on the invoice), else the booking's own Remaining
#   paper                  sheets the printing machines counted yesterday (Printer Reading)
#   app fees               the platform fees posted this month, and what was collected from the doctors

import frappe
from frappe.utils import add_days, flt, get_first_day, today

STUDIO = "استوديو X"
HALLS = "قاعات Imed"
BUSINESS_DONE = ("Confirmed with Deposit", "Completed")
FEE_ACCOUNT = "إيراد رسوم المنصة"


def company():
	return frappe.defaults.get_global_default("company")


def cost_center(name):
	return f"{name} - {frappe.get_cached_value('Company', company(), 'abbr')}"


def card(value, fieldtype="Currency"):
	return {"value": flt(value, 2), "fieldtype": fieldtype}


def check_access():
	# The figures are the group's whole books, every branch together: the owner's and the accountant's only. A
	# branch manager may read the ledger, but only her branch's (User Permissions), which a total here ignores.
	frappe.only_for(("Super Admin", "System Manager", "Accounts Manager"))


def gl_total(root_type, from_date, to_date, account=None, by_cost_center=False):
	"""Income (credit - debit) or expense (debit - credit) posted between two dates, cancelled entries left out."""
	amount = "gl.credit - gl.debit" if root_type == "Income" else "gl.debit - gl.credit"
	conditions, values = ["gl.is_cancelled = 0", "gl.company = %(company)s", "gl.posting_date between %(from)s and %(to)s"], {
		"company": company(),
		"from": from_date,
		"to": to_date,
	}
	if account:
		conditions.append("acc.account_name = %(account)s")
		values["account"] = account
	else:
		conditions.append("acc.root_type = %(root_type)s")
		values["root_type"] = root_type
	group = ", gl.cost_center" if by_cost_center else ""
	rows = frappe.db.sql(
		f"""select sum({amount}) as total{group}
		from `tabGL Entry` gl join `tabAccount` acc on acc.name = gl.account
		where {' and '.join(conditions)}
		{'group by gl.cost_center' if by_cost_center else ''}""",
		values,
		as_dict=True,
	)
	if by_cost_center:
		return {row.cost_center: flt(row.total, 2) for row in rows if flt(row.total, 2)}
	return flt(rows[0].total, 2) if rows else 0


def yesterday():
	return add_days(today(), -1)


def month_to_date():
	return get_first_day(today()), today()


@frappe.whitelist()
def revenue_yesterday(filters=None):
	check_access()
	return card(gl_total("Income", yesterday(), yesterday()))


@frappe.whitelist()
def expenses_yesterday(filters=None):
	check_access()
	return card(gl_total("Expense", yesterday(), yesterday()))


@frappe.whitelist()
def revenue_this_month(filters=None):
	check_access()
	return card(gl_total("Income", *month_to_date()))


@frappe.whitelist()
def platform_fees_this_month(filters=None):
	check_access()
	return card(gl_total("Income", *month_to_date(), account=FEE_ACCOUNT))


@frappe.whitelist()
def app_collections_this_month(filters=None):
	check_access()
	start, end = month_to_date()
	value = frappe.db.sql(
		"""select sum(amount) from `tabDoctor Ledger Entry`
		where entry_type = 'Collection' and docstatus = 1 and entry_date between %s and %s""",
		(start, end),
	)[0][0]
	return card(value)


def bookings(business, field=None):
	start, end = month_to_date()
	filters = {
		"cost_center": cost_center(business),
		"status": ("in", BUSINESS_DONE),
		"booking_date": ("between", (start, end)),
	}
	if field:
		return flt(sum(flt(v) for v in frappe.get_all("Booking", filters=filters, pluck=field)), 2)
	return frappe.db.count("Booking", filters)


@frappe.whitelist()
def studio_bookings_this_month(filters=None):
	check_access()
	return card(bookings(STUDIO), "Int")


@frappe.whitelist()
def studio_hours_this_month(filters=None):
	check_access()
	return card(bookings(STUDIO, "hours"), "Float")


@frappe.whitelist()
def hall_bookings_this_month(filters=None):
	check_access()
	return card(bookings(HALLS), "Int")


def unpaid_on_bookings():
	"""QA-18: owed on bookings dated up to today. A completed booking is paid on its invoice, whose outstanding is
	what is left (a payment made on the invoice itself is counted there); one confirmed with a deposit owes its
	Remaining. A tentative booking owes nothing yet; a cancelled one or a no-show keeps its deposit and owes nothing."""
	total = 0
	for booking in frappe.get_all(
		"Booking",
		filters={"status": ("in", BUSINESS_DONE), "booking_date": ("<=", today())},
		fields=["status", "sales_invoice", "outstanding_amount"],
	):
		if booking.status == "Completed" and booking.sales_invoice:
			invoice = frappe.db.get_value("Sales Invoice", booking.sales_invoice, ["docstatus", "outstanding_amount"], as_dict=True)
			total += flt(invoice.outstanding_amount) if invoice and invoice.docstatus == 1 else flt(booking.outstanding_amount)
		else:
			total += flt(booking.outstanding_amount)
	return flt(total, 2)


@frappe.whitelist()
def unpaid_on_bookings_card(filters=None):
	check_access()
	return card(unpaid_on_bookings())


@frappe.whitelist()
def sheets_printed_yesterday(filters=None):
	check_access()
	value = frappe.db.sql(
		"select sum(consumed) from `tabPrinter Reading` where docstatus = 1 and reading_date = %s", yesterday()
	)[0][0]
	return card(value, "Int")


@frappe.whitelist()
def cash_discrepancies_open(filters=None):
	"""Shortages and surpluses from the daily closes still waiting for the accountant."""
	check_access()
	from imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy import OPEN

	return card(frappe.db.count("Cash Discrepancy", {"status": ("in", OPEN)}), "Int")


@frappe.whitelist()
def cash_shortages_this_month(filters=None):
	"""What the daily closes found short this month, whatever was decided on it since (withdrawn ones aside)."""
	check_access()
	start, end = month_to_date()
	value = frappe.db.sql(
		"""select sum(amount) from `tabCash Discrepancy`
		where kind = 'Shortage' and status != 'Withdrawn' and close_date between %s and %s""",
		(start, end),
	)[0][0]
	return card(value)


def revenue_by_business(from_date, to_date):
	"""{business: revenue} from the ledger, every income account, between two dates (QA-06)."""
	return gl_total("Income", from_date, to_date, by_cost_center=True)
