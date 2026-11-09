# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The Owner Dashboard by period (owner, 5 Nov 2026): today first, then the week, then the month, each business on
# its own card — the studio, the halls, the libraries, the app. Each card: what the ledger holds for the business
# (revenue, expenses, net, on its cost center) and what the business did (bookings and hours, sales, students'
# fees), from the same records the rest of the dashboard reads.
#
#   today   the day so far
#   week    from Saturday (the week starts on Saturday here, as on the booking calendars) to today
#   month   from the 1st to today

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_first_day, getdate, nowdate

from imed_erp.imederp.booking_rules import NOT_HELD
from imed_erp.imederp.business_figures import company, ledger
from imed_erp.imederp.owner_yesterday import check_owner

# The businesses on the cards, by their cost centers' names (setup_core.py).
STUDIO, HALLS, APP = "استوديو X", "قاعات Imed", "تطبيق BA Plus"
LIBRARIES = ("مكتبة الأزاريطة", "مكتبة المواساة")
SATURDAY = 5  # date.weekday()


@frappe.whitelist()
def get_periods():
	check_owner()
	return periods()


def periods(today=None):
	today = getdate(today or nowdate())
	week_start = add_days(today, -((today.weekday() - SATURDAY) % 7))
	centers = {
		r.cost_center_name: r.name
		for r in frappe.get_all("Cost Center", filters={"company": company(), "is_group": 0}, fields=["name", "cost_center_name"])
	}
	week_start = getdate(week_start)
	month_start = getdate(get_first_day(today))
	week = period("week", _("This Week"), week_start, today, centers)
	# The week drawn day by day, Saturday to Friday (the days to come empty): each business's main figure.
	week["days"] = daily(week_start, add_days(week_start, 6), centers)
	month = period("month", _("This Month"), month_start, today, centers)
	# The month against the same stretch of the month before (the 1st to the same day, or its last day).
	previous_start = getdate(get_first_day(add_days(month_start, -1)))
	previous_end = min(add_days(previous_start, (today - month_start).days), add_days(month_start, -1))
	previous = period("previous", "", previous_start, getdate(previous_end), centers)
	for business, before in zip(month["businesses"], previous["businesses"]):
		business["main"], business["previous"] = main_value(business), main_value(before)
	month["previous_from"], month["previous_to"] = previous_start, getdate(previous_end)
	return {
		"today": today,
		"currency": frappe.get_cached_value("Company", company(), "default_currency"),
		"periods": [period("today", _("Today"), today, today, centers), week, month],
		"tomorrow": tomorrow(add_days(today, 1)),
	}


def hh_mm(value):
	"""A time as 09:00: the database gives 9:00:00 (a timedelta) for a time before ten."""
	if value is None:
		return None
	hours, minutes = str(value).split(":")[:2]
	return f"{cint(hours):02d}:{minutes}"


def tomorrow(day):
	"""Tomorrow's bookings that hold their time, the halls' and the studio's apart, in the order of the day (the
	owner, 9 Nov 2026: in place of the next bookings)."""
	rows = frappe.db.sql(
		"""select b.name, b.resource, b.resource_type, b.from_time, b.to_time, b.status, b.activity,
			coalesce(c.customer_name, b.xstudio_customer_name, b.responsible_name) as who
		from `tabBooking` b left join `tabCustomer` c on c.name = b.customer
		where b.booking_date = %s and b.status not in %s and b.resource_type in ('Hall', 'Studio Service')
		order by b.from_time, b.resource""",
		(day, NOT_HELD),
		as_dict=True,
	)
	for row in rows:
		row.from_time, row.to_time = hh_mm(row.from_time), hh_mm(row.to_time)
	return {
		"date": getdate(day),
		"halls": [r for r in rows if r.resource_type == "Hall"],
		"studio": [r for r in rows if r.resource_type == "Studio Service"],
	}


def main_value(business):
	"""Each business's one figure: bookings for the studio and the halls, sales for the libraries, students' fees
	for the app."""
	a = business["activity"]
	return flt({"studio": a.get("bookings"), "halls": a.get("bookings"), "libraries": a.get("net"), "app": a.get("charged")}.get(business["key"]), 2)


def daily(start, end, centers):
	"""{business: [the main figure of each day from start to end]}, one grouped query a business."""
	from imed_erp.imederp.library_sync.contract import RETURN_KINDS, SALES_KINDS

	days = [getdate(add_days(start, i)) for i in range((getdate(end) - getdate(start)).days + 1)]
	series = {key: {d: 0.0 for d in days} for key in ("studio", "halls", "libraries", "app")}
	for day, resource_type, n in frappe.db.sql(
		"""select booking_date, resource_type, count(*) from `tabBooking`
		where booking_date between %s and %s and status not in %s group by booking_date, resource_type""",
		(start, end, NOT_HELD),
	):
		key = {"Studio Service": "studio", "Hall": "halls"}.get(resource_type)
		if key and getdate(day) in series[key]:
			series[key][getdate(day)] += cint(n)
	libraries = [centers[n] for n in LIBRARIES if centers.get(n)]
	if libraries:
		for day, kind, value in frappe.db.sql(
			"""select date(reg_date), document_kind, coalesce(sum(total), 0) from `tabLibrary Sales Document`
			where cost_center in %s and is_final = 1 and is_cancelled = 0 and reg_date between %s and %s
			group by date(reg_date), document_kind""",
			(tuple(libraries), f"{start} 00:00:00", f"{end} 23:59:59"),
		):
			sign = 1 if kind in SALES_KINDS else -1 if kind in RETURN_KINDS else 0
			if getdate(day) in series["libraries"]:
				series["libraries"][getdate(day)] += sign * flt(value)
	agreements = frappe.get_all("Doctor Agreement", filters={"agreement_type": "App"}, pluck="name")
	if agreements:
		for day, value in frappe.db.sql(
			"""select entry_date, coalesce(sum(amount), 0) from `tabDoctor Ledger Entry`
			where docstatus = 1 and entry_type in ('Accrual', 'Adjustment') and agreement in %s and entry_date between %s and %s
			group by entry_date""",
			(tuple(agreements), start, end),
		):
			if getdate(day) in series["app"]:
				series["app"][getdate(day)] += flt(value)
	return {"dates": days, **{key: [flt(values[d], 2) for d in days] for key, values in series.items()}}


def period(key, label, start, end, centers):
	totals = ledger(start, end)

	def money(*names):
		cost_centers = [centers[n] for n in names if centers.get(n)]
		revenue = -sum(flt(totals.get((cc, "Income"))) for cc in cost_centers)
		expenses = sum(flt(totals.get((cc, "Expense"))) for cc in cost_centers)
		return {"revenue": flt(revenue, 2), "expenses": flt(expenses, 2), "net": flt(revenue - expenses, 2)}

	return {
		"key": key,
		"label": label,
		"from": start,
		"to": end,
		"businesses": [
			{"key": "studio", "label": _("Studio"), "icon": "clapperboard", **money(STUDIO), "activity": studio(start, end)},
			{"key": "halls", "label": _("Halls"), "icon": "presentation", **money(HALLS), "activity": halls(start, end)},
			{"key": "libraries", "label": _("Libraries"), "icon": "book-open", **money(*LIBRARIES), "activity": libraries(start, end, centers)},
			{"key": "app", "label": _("BA Plus App"), "icon": "smartphone", **money(APP), "activity": app(start, end)},
		],
	}


def held_bookings(resource_type, start, end):
	return frappe.db.sql(
		"""select count(*), coalesce(sum(hours), 0), coalesce(sum(total_amount), 0), coalesce(sum(paid_amount), 0),
			coalesce(sum(outstanding_amount), 0), coalesce(sum(xstudio_amount_paid), 0), coalesce(sum(xstudio_amount_due), 0)
		from `tabBooking` where resource_type = %s and booking_date between %s and %s and status not in %s""",
		(resource_type, start, end, NOT_HELD),
	)[0]


def cancelled(resource_type, start, end):
	return frappe.db.count("Booking", {"resource_type": resource_type, "booking_date": ["between", [start, end]], "status": ["in", NOT_HELD]})


def studio(start, end):
	"""The studio's bookings in the period that hold their time; its money as XStudio reports it (not posted)."""
	n, hours, total, paid, due, x_paid, x_due = held_bookings("Studio Service", start, end)
	return {
		"bookings": cint(n),
		"hours": flt(hours, 1),
		"paid": flt(flt(x_paid) + flt(paid), 2),
		"due": flt(flt(x_due) + flt(due), 2),
		"cancelled": cancelled("Studio Service", start, end),
	}


def halls(start, end):
	"""The halls' bookings in the period (from Sparkle and any made here) that hold their time."""
	n, hours, total, paid, due, x_paid, x_due = held_bookings("Hall", start, end)
	return {
		"bookings": cint(n),
		"hours": flt(hours, 1),
		"value": flt(total, 2),
		"paid": flt(paid, 2),
		"due": flt(due, 2),
		"cancelled": cancelled("Hall", start, end),
	}


def libraries(start, end, centers):
	"""Each library's sales less returns in the period, from the library system's invoices."""
	from imed_erp.imederp.library_sync.contract import RETURN_KINDS, SALES_KINDS

	rows = []
	for name in LIBRARIES:
		center = centers.get(name)
		sums = frappe.get_all(
			"Library Sales Document",
			filters={
				"cost_center": center or "",
				"reg_date": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]],
				"is_final": 1,
				"is_cancelled": 0,
				"document_kind": ["in", SALES_KINDS + RETURN_KINDS],
			},
			fields=["document_kind", {"COUNT": "*", "as": "n"}, {"SUM": "total", "as": "value"}],
			group_by="document_kind",
		)
		sales = sum(flt(s.value) for s in sums if s.document_kind in SALES_KINDS)
		returns = sum(flt(s.value) for s in sums if s.document_kind in RETURN_KINDS)
		rows.append({"name": name, "invoices": sum(cint(s.n) for s in sums if s.document_kind in SALES_KINDS), "net": flt(sales - returns, 2)})
	return {"rows": rows, "net": flt(sum(r["net"] for r in rows), 2), "invoices": sum(r["invoices"] for r in rows)}


def app(start, end):
	"""The doctors' platform fees for the students counted in the period, what was collected, new subscriptions."""
	agreements = frappe.get_all("Doctor Agreement", filters={"agreement_type": "App"}, pluck="name")
	if not agreements:
		return {"state": "not_configured"}
	amounts = {
		entry_type: flt(amount)
		for entry_type, amount in frappe.db.sql(
			"""select entry_type, coalesce(sum(amount), 0) from `tabDoctor Ledger Entry`
			where docstatus = 1 and entry_date between %(start)s and %(end)s and agreement in %(agreements)s group by entry_type""",
			{"start": start, "end": end, "agreements": tuple(agreements)},
		)
	}
	return {
		"state": "ok",
		"charged": flt(amounts.get("Accrual", 0) + amounts.get("Adjustment", 0), 2),
		"collected": flt(amounts.get("Collection", 0), 2),
		"subscriptions": frappe.db.count("App Subscription", {"docstatus": 1, "subscription_date": ["between", [start, end]]}),
	}


# ---------- the cash boxes and the supplies (the owner, 5 Nov 2026: "a good stock section, arrows up and down") ----


@frappe.whitelist()
def get_boxes_and_stock():
	check_owner()
	return {"currency": frappe.get_cached_value("Company", company(), "default_currency"), "boxes": boxes(), "stock": stock(), "requests": requests()}


def boxes():
	"""What each cash box and wallet holds now, largest first; its name without the company's suffix."""
	from imed_erp.imederp.owner_figures import balance, leaf_accounts

	abbr = frappe.get_cached_value("Company", company(), "abbr")
	rows = []
	for account in leaf_accounts(account_type=["in", ["Cash", "Bank"]]):
		name = frappe.get_cached_value("Account", account, "account_name") or account.replace(f" - {abbr}", "")
		rows.append({"account": account, "name": name, "balance": flt(balance([account]), 2)})
	return sorted(rows, key=lambda r: -r["balance"])


WEEK = 7
# The Epson set's four colours (setup/setup_inks.py): shown together, which finished most this month first.
EPSON_PREFIX = "INK-EPSON-"


def library_stores():
	"""The stores the libraries keep their supplies in (خامات المواساة, خامات الأزاريطة), by the stores the library
	accounts work in, else by name."""
	stores = frappe.get_all(
		"User Permission",
		filters={"allow": "Warehouse", "user": ["in", frappe.get_all("Has Role", filters={"role": "Library Staff", "parenttype": "User"}, pluck="parent") or [""]]},
		pluck="for_value",
	)
	stores += frappe.get_all("Warehouse", filters={"company": company(), "is_group": 0, "warehouse_name": ["like", "خامات%"]}, pluck="name")
	return [w for w in dict.fromkeys(stores) if not frappe.db.get_value("Warehouse", w, "is_group")]


def stock(today=None):
	"""Each library store apart (owner, 9 Nov 2026: Mawasah's stock apart from Azarita's), each supply in the unit the
	library counts it in (paper in boxes): what it holds now, against a week ago (the arrow), what the week used, how
	many days that lasts. The Epson colours together: what each holds and how many finished this month."""
	from imed_erp.imederp.library_desk import SUPPLY_GROUPS, UNIT_NAMES, screen_unit

	today = getdate(today or nowdate())
	week_ago = add_days(today, -WEEK)
	month_start = getdate(get_first_day(today))
	groups = [g for g in SUPPLY_GROUPS if frappe.db.exists("Item Group", g)]
	items = frappe.get_all(
		"Item", filters={"item_group": ["in", groups or [""]], "disabled": 0, "is_stock_item": 1}, fields=["name", "item_name", "item_group"], order_by="item_group desc, item_name"
	)
	result = []
	for store in library_stores():
		rows, colours = [], []
		for item in items:
			unit, factor = screen_unit(item.name)
			now = flt(frappe.db.get_value("Bin", {"item_code": item.name, "warehouse": store}, "actual_qty"))
			before = flt(
				frappe.db.sql(
					"""select qty_after_transaction from `tabStock Ledger Entry` where item_code = %s and warehouse = %s and is_cancelled = 0
					and posting_date <= %s order by posting_date desc, posting_time desc, creation desc limit 1""",
					(item.name, store, week_ago),
				)[0][0]
				if frappe.db.exists("Stock Ledger Entry", {"item_code": item.name, "warehouse": store, "is_cancelled": 0, "posting_date": ["<=", week_ago]})
				else 0
			)
			used = used_between(item.name, store, add_days(week_ago, 1), today)
			row = {
				"item_code": item.name,
				"name": item.item_name,
				"group": item.item_group,
				"unit": UNIT_NAMES.get(unit, unit) or "",
				"qty": flt(now / factor, 2),
				"week_ago": flt(before / factor, 2),
				"change": flt((now - before) / factor, 2),
				"used_week": flt(used / factor, 2),
				"days_left": cint(now / (used / WEEK)) if used > 0 else None,
				# Never counted nor moved in this store: not "ran out", "not counted yet".
				"counted": 1 if frappe.db.exists("Stock Ledger Entry", {"item_code": item.name, "warehouse": store, "is_cancelled": 0}) else 0,
			}
			if item.name.startswith(EPSON_PREFIX):
				row["finished_month"] = flt(used_between(item.name, store, month_start, today) / factor, 2)
				colours.append(row)
			else:
				rows.append(row)
		if colours:
			# The colour that finished most this month first.
			colours.sort(key=lambda c: (-c["finished_month"], c["qty"]))
		result.append(
			{"store": store, "name": frappe.get_cached_value("Warehouse", store, "warehouse_name") or store, "items": rows, "epson": colours}
		)
	return result


def used_between(item_code, store, start, end):
	"""What left a store as used between two days: sold, or taken off as finished (a Material Issue); a transfer moves
	it and a count corrects it, neither is use."""
	sold = -flt(
		frappe.db.sql(
			"""select coalesce(sum(actual_qty), 0) from `tabStock Ledger Entry` where item_code = %s and warehouse = %s and is_cancelled = 0
			and actual_qty < 0 and voucher_type not in ('Stock Entry', 'Stock Reconciliation') and posting_date between %s and %s""",
			(item_code, store, start, end),
		)[0][0]
	)
	issued = -flt(
		frappe.db.sql(
			"""select coalesce(sum(sle.actual_qty), 0) from `tabStock Ledger Entry` sle join `tabStock Entry` se on se.name = sle.voucher_no
			where sle.item_code = %s and sle.warehouse = %s and sle.is_cancelled = 0 and sle.actual_qty < 0 and sle.voucher_type = 'Stock Entry'
			and se.stock_entry_type = 'Material Issue' and sle.posting_date between %s and %s""",
			(item_code, store, start, end),
		)[0][0]
	)
	return sold + issued


@frappe.whitelist()
def get_requests():
	check_owner()
	return requests()


def requests(limit=15):
	"""The libraries' requests for supplies still open (owner, 9 Nov 2026: the owner sees them at once): the newest
	first, each with its library's store, what and how much, and where it stands."""
	stores = library_stores()
	rows = frappe.db.sql(
		"""select mr.name, mr.transaction_date, mr.creation, mr.status, mr.docstatus, mr.material_request_type,
			mr.set_warehouse, mr.per_ordered, mr.per_received, {approval}
		from `tabMaterial Request` mr
		where mr.company = %(company)s and mr.docstatus < 2 and mr.set_warehouse in %(stores)s
			and mr.status not in ('Stopped', 'Cancelled', 'Transferred', 'Received', 'Issued')
		order by mr.creation desc limit %(limit)s""".format(
			approval="mr.custom_approval_status" if frappe.get_meta("Material Request").has_field("custom_approval_status") else "null as custom_approval_status"
		),
		{"company": company(), "stores": tuple(stores or [""]), "limit": limit},
		as_dict=True,
	)
	from imed_erp.imederp.library_desk import UNIT_NAMES

	for row in rows:
		row.store = frappe.get_cached_value("Warehouse", row.set_warehouse, "warehouse_name") or row.set_warehouse
		row.items = [
			{"name": i.item_name, "qty": flt(i.qty, 2), "unit": UNIT_NAMES.get(i.uom, i.uom) or ""}
			for i in frappe.get_all("Material Request Item", filters={"parent": row.name}, fields=["item_name", "qty", "uom"], order_by="idx")
		]
		row.state = row.custom_approval_status or row.status
	return rows
