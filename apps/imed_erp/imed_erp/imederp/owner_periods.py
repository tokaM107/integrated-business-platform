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
	return {
		"today": today,
		"currency": frappe.get_cached_value("Company", company(), "default_currency"),
		"periods": [
			period("today", _("Today"), today, today, centers),
			period("week", _("This Week"), getdate(week_start), today, centers),
			period("month", _("This Month"), getdate(get_first_day(today)), today, centers),
		],
	}


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
	return {"currency": frappe.get_cached_value("Company", company(), "default_currency"), "boxes": boxes(), "stock": stock()}


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


def stock(today=None):
	"""Each supply (paper, inks, and any binding supplies), in the unit the libraries count it in (paper in boxes):
	what the group's stores hold now, what they held a week ago (the arrow), what a week used, how many days that
	lasts, and each store's part."""
	from imed_erp.imederp.library_desk import SUPPLY_GROUPS, UNIT_NAMES, screen_unit

	today = getdate(today or nowdate())
	week_ago = add_days(today, -WEEK)
	groups = [g for g in SUPPLY_GROUPS if frappe.db.exists("Item Group", g)]
	groups += frappe.get_all("Item Group", filters={"is_group": 0, "item_group_name": ["like", "%سلك%"]}, pluck="name")
	groups += frappe.get_all("Item Group", filters={"is_group": 0, "item_group_name": ["like", "%تجليد%"]}, pluck="name")
	stores = frappe.get_all("Warehouse", filters={"company": company(), "is_group": 0}, pluck="name")
	if not groups or not stores:
		return []
	rows = []
	for item in frappe.get_all(
		"Item", filters={"item_group": ["in", list(dict.fromkeys(groups))], "disabled": 0, "is_stock_item": 1}, fields=["name", "item_name", "item_group"], order_by="item_group desc, item_name"
	):
		unit, factor = screen_unit(item.name)
		per_store = frappe.db.sql(
			"select warehouse, actual_qty from `tabBin` where item_code = %s and warehouse in %s and actual_qty != 0", (item.name, tuple(stores)), as_dict=True
		)
		now = sum(flt(b.actual_qty) for b in per_store)
		before = sum(
			flt(r[0])
			for r in frappe.db.sql(
				"""select (select qty_after_transaction from `tabStock Ledger Entry` s
					where s.item_code = %(item)s and s.warehouse = w.name and s.is_cancelled = 0 and s.posting_date <= %(day)s
					order by s.posting_date desc, s.posting_time desc, s.creation desc limit 1)
				from `tabWarehouse` w where w.name in %(stores)s""",
				{"item": item.name, "day": week_ago, "stores": tuple(stores)},
			)
			if r[0] is not None
		)
		used = -flt(
			frappe.db.sql(
				"""select coalesce(sum(actual_qty), 0) from `tabStock Ledger Entry`
				where item_code = %s and warehouse in %s and is_cancelled = 0 and actual_qty < 0 and voucher_type not in ('Stock Entry', 'Stock Reconciliation')
					and posting_date > %s and posting_date <= %s""",
				(item.name, tuple(stores), week_ago, today),
			)[0][0]
		)
		# A transfer between the group's stores moves it and a count corrects it: neither is use. What a sale took,
		# and what a library took off as finished (a Material Issue), is.
		used += -flt(
			frappe.db.sql(
				"""select coalesce(sum(sle.actual_qty), 0) from `tabStock Ledger Entry` sle join `tabStock Entry` se on se.name = sle.voucher_no
				where sle.item_code = %s and sle.warehouse in %s and sle.is_cancelled = 0 and sle.actual_qty < 0 and sle.voucher_type = 'Stock Entry'
					and se.stock_entry_type = 'Material Issue' and sle.posting_date > %s and sle.posting_date <= %s""",
				(item.name, tuple(stores), week_ago, today),
			)[0][0]
		)
		daily = used / WEEK
		rows.append(
			{
				"item_code": item.name,
				"name": item.item_name,
				"group": item.item_group,
				"unit": UNIT_NAMES.get(unit, unit) or "",
				"qty": flt(now / factor, 2),
				"week_ago": flt(before / factor, 2),
				"change": flt((now - before) / factor, 2),
				"used_week": flt(used / factor, 2),
				"days_left": cint(now / daily) if daily > 0 else None,
				"stores": [
					{"store": frappe.get_cached_value("Warehouse", b.warehouse, "warehouse_name") or b.warehouse, "qty": flt(flt(b.actual_qty) / factor, 2)}
					for b in sorted(per_store, key=lambda b: -flt(b.actual_qty))
				],
			}
		)
	return rows
