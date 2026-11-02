# The Owner Dashboard's overview, drawn on top of it by public/js/imed_owner_dashboard.js (the owner's picture of
# 2 Nov 2026: four figures with how they moved since last month, the bookings' path, what is coming, the
# bookings' money and the reports). One call (get_overview); read only.
#
# Nothing is worked out in a new way: the money is owner_figures.balance over the same accounts as the dashboard's
# cards (an opening entry and a Period Closing Voucher left out), the rest is the bookings as they are.
#
#   kpis        this month to today: net, revenue, expenses; and the cash in the boxes now. Each compared with
#               last month over the same days (the 1st to the same day; when last month is shorter, both stop at
#               its last day, so the two periods have the same length); the cash with its balance at the end of
#               that same day last month. The dates compared are sent with the figures.
#   pipeline    this month's bookings, the halls and the studio apart, each tentative or completed; cancelled and
#               no-shows apart.
#   upcoming    the next bookings from today, a week ahead, not cancelled.
#   collection  this month's bookings (not cancelled, not a no-show): their total, what was paid and what is still
#               owed, and of that what is owed on bookings whose day has passed.
#
# The owner's alone, as the day's figures (owner_yesterday.check_owner).

import frappe
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate, nowdate

from imed_erp.imederp.owner_figures import balance, company, leaf_accounts
from imed_erp.imederp.owner_yesterday import check_owner

NOT_HELD = ("Cancelled", "No Show")
# A booking's resource type (Booking.resource_type, as owner_yesterday reads it) and how the page names it.
KINDS = {"Hall": "halls", "Studio Service": "studio"}
UPCOMING_DAYS = 7
UPCOMING_LIMIT = 5


@frappe.whitelist()
def get_overview():
	check_owner()
	return overview()


def overview(today=None):
	period = periods(today)
	return {
		"today": period.today,
		"currency": frappe.get_cached_value("Company", company(), "default_currency"),
		"kpis": kpis(period),
		"pipeline": pipeline(period),
		"upcoming": upcoming(period),
		"collection": collection(period),
	}


def periods(today=None):
	"""This month to `today`, and the two periods of the same length compared: from the 1st of this month and of the
	one before, to the same day (or both to the last day of the shorter month)."""
	today = getdate(today or nowdate())
	month_start = getdate(get_first_day(today))
	previous_start = getdate(add_months(month_start, -1))
	days = min((today - month_start).days + 1, (month_start - previous_start).days)
	return frappe._dict(
		today=today,
		month_start=month_start,
		month_end=getdate(get_last_day(today)),
		current=(month_start, getdate(add_days(month_start, days - 1))),
		previous=(previous_start, getdate(add_days(previous_start, days - 1))),
	)


def profit_and_loss(from_date, to_date):
	revenue = balance(leaf_accounts(root_type="Income"), -1, from_date, to_date, profit_and_loss=True)
	expenses = balance(leaf_accounts(root_type="Expense"), 1, from_date, to_date, profit_and_loss=True)
	return {"revenue": revenue, "expenses": expenses, "net": flt(revenue - expenses, 2)}


def kpis(period):
	month = profit_and_loss(period.month_start, period.today)
	current = month if period.current[1] == period.today else profit_and_loss(*period.current)
	previous = profit_and_loss(*period.previous)
	boxes = leaf_accounts(account_type=["in", ["Cash", "Bank"]])
	return {
		"month": month,
		"compare": {
			"current": {"from": period.current[0], "to": period.current[1], **current},
			"previous": {"from": period.previous[0], "to": period.previous[1], **previous},
		},
		"cash": {
			"now": balance(boxes),
			# The boxes at the end of the same day last month.
			"previous": balance(boxes, to_date=period.previous[1]),
			"previous_on": period.previous[1],
		},
	}


def pipeline(period):
	"""This month's bookings, the halls apart from the studio, each as tentative or completed (the owner, 2 Nov 2026:
	a booking is tentative or completed). A booking in another state that still holds its time (confirmed, with a
	deposit) is counted as tentative, not completed yet, so none is left out; cancelled and no-shows apart."""
	rows = frappe.get_all(
		"Booking",
		filters={"booking_date": ["between", [period.month_start, period.month_end]]},
		fields=["resource_type", "status", {"COUNT": "*", "as": "count"}],
		group_by="resource_type, status",
	)
	kinds = {kind: {"tentative": 0, "completed": 0, "cancelled": 0, "no_show": 0} for kind in KINDS}
	for row in rows:
		kind = kinds.get(row.resource_type)
		if kind is None:
			continue
		if row.status == "Completed":
			kind["completed"] += row.count
		elif row.status == "Cancelled":
			kind["cancelled"] += row.count
		elif row.status == "No Show":
			kind["no_show"] += row.count
		else:
			kind["tentative"] += row.count
	return {
		"from": period.month_start,
		"to": period.month_end,
		"kinds": [{"kind": KINDS[kind], **counts} for kind, counts in kinds.items()],
	}


def upcoming(period):
	rows = frappe.get_all(
		"Booking",
		filters={
			"booking_date": ["between", [period.today, add_days(period.today, UPCOMING_DAYS)]],
			"status": ["not in", NOT_HELD],
		},
		fields=["name", "booking_date", "from_time", "to_time", "resource", "customer", "status"],
		order_by="booking_date asc, from_time asc",
		limit=UPCOMING_LIMIT,
	)
	for row in rows:
		row.customer_name = (
			frappe.get_cached_value("Customer", row.customer, "customer_name") if row.customer else None
		)
		row.from_time = str(row.from_time) if row.from_time else None
		row.to_time = str(row.to_time) if row.to_time else None
	return {"days": UPCOMING_DAYS, "rows": rows}


def collection(period):
	held = {
		"booking_date": ["between", [period.month_start, period.month_end]],
		"status": ["not in", NOT_HELD],
	}
	sums = frappe.get_all(
		"Booking",
		filters=held,
		fields=[
			{"COUNT": "*", "as": "count"},
			{"SUM": "total_amount", "as": "total"},
			{"SUM": "paid_amount", "as": "paid"},
			{"SUM": "outstanding_amount", "as": "outstanding"},
		],
	)[0]
	overdue = frappe.get_all(
		"Booking",
		filters={**held, "booking_date": ["between", [period.month_start, add_days(period.today, -1)]]},
		fields=[{"SUM": "outstanding_amount", "as": "amount"}],
	)[0]
	return {
		"from": period.month_start,
		"to": period.month_end,
		"count": sums.count or 0,
		"total": flt(sums.total, 2),
		"paid": flt(sums.paid, 2),
		"outstanding": flt(sums.outstanding, 2),
		# Still owed on bookings whose day has passed: part of the outstanding.
		"overdue": flt(overdue.amount, 2),
	}
