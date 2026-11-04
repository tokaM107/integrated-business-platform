# The Owner Dashboard's overview, drawn on top of it by public/js/imed_owner_dashboard.js (the owner's picture of
# 2 Nov 2026: four figures, the bookings, what is coming, the bookings' money and the reports). One call
# (get_overview); read only.
#
# Nothing is worked out in a new way: the money is owner_figures.balance over the same accounts as the dashboard's
# cards (an opening entry and a Period Closing Voucher left out), the rest is the bookings as they are.
#
#   kpis        this month to today: net, revenue, expenses; and the cash in the boxes now (no comparison with
#               last month: the owner, 2 Nov 2026).
#   pipeline    this month's bookings, the halls and the studio apart, each tentative or completed; cancelled and
#               no-shows apart.
#   upcoming    the next bookings from today, a week ahead, not cancelled.
#   collection  this month's bookings (not cancelled, not a no-show): their total, what was paid and what is still
#               owed, and of that what is owed on bookings whose day has passed.
#   libraries   today's sales of each library (Azarita, Mawasah) as its own system sent them (Library Sales
#               Document, issued and not cancelled), its returns, and when its connector last delivered; a library
#               whose system is not linked yet says so (the owner, 4 Nov 2026: the first thing on the page).
#
# The owner's alone, as the day's figures (owner_yesterday.check_owner).

import frappe
from frappe.utils import add_days, flt, get_first_day, get_last_day, getdate, nowdate

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
		"libraries": libraries(period),
	}


def periods(today=None):
	"""Today and its month."""
	today = getdate(today or nowdate())
	return frappe._dict(
		today=today,
		month_start=getdate(get_first_day(today)),
		month_end=getdate(get_last_day(today)),
	)


def profit_and_loss(from_date, to_date):
	revenue = balance(leaf_accounts(root_type="Income"), -1, from_date, to_date, profit_and_loss=True)
	expenses = balance(leaf_accounts(root_type="Expense"), 1, from_date, to_date, profit_and_loss=True)
	return {"revenue": revenue, "expenses": expenses, "net": flt(revenue - expenses, 2)}


def kpis(period):
	return {
		"month": profit_and_loss(period.month_start, period.today),
		"cash": balance(leaf_accounts(account_type=["in", ["Cash", "Bank"]])),
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


# The libraries, by their cost center's name (as library_revenue.py and treasuries.py name them), Azarita first.
LIBRARIES = ("مكتبة الأزاريطة", "مكتبة المواساة")


def libraries(period):
	from imed_erp.imederp.library_sync.contract import RETURN_KINDS, SALES_KINDS

	centers = {
		r.cost_center_name: r.name
		for r in frappe.get_all("Cost Center", filters={"company": company(), "cost_center_name": ["in", LIBRARIES]}, fields=["name", "cost_center_name"])
	}
	day = {
		"reg_date": ["between", [f"{period.today} 00:00:00", f"{period.today} 23:59:59"]],
		"is_final": 1,
		"is_cancelled": 0,
		"document_kind": ["in", SALES_KINDS + RETURN_KINDS],
	}
	sums = frappe.get_all(
		"Library Sales Document",
		filters={**day, "cost_center": ["in", list(centers.values()) or [""]]},
		fields=["cost_center", "document_kind", {"COUNT": "*", "as": "n"}, {"SUM": "total", "as": "value"}],
		group_by="cost_center, document_kind",
	)
	heard = {
		r.cost_center: r.at
		for r in frappe.get_all(
			"Library Sales Document",
			filters={"cost_center": ["in", list(centers.values()) or [""]]},
			fields=["cost_center", {"MAX": "last_synced_at", "as": "at"}],
			group_by="cost_center",
		)
	}
	rows = []
	for name in LIBRARIES:
		center = centers.get(name)
		row = {"name": name, "cost_center": center, "linked": bool(center and heard.get(center)), "last_synced_at": heard.get(center), "sales_count": 0, "sales_value": 0.0, "returns_count": 0, "returns_value": 0.0}
		for s in sums:
			if s.cost_center == center:
				side = "sales" if s.document_kind in SALES_KINDS else "returns"
				row[f"{side}_count"] += s.n
				row[f"{side}_value"] = flt(row[f"{side}_value"] + flt(s.value), 2)
		row["net"] = flt(row["sales_value"] - row["returns_value"], 2)
		rows.append(row)
	return {"rows": rows, "total": flt(sum(r["net"] for r in rows), 2)}
