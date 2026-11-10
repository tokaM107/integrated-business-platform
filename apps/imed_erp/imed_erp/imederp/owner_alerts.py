# What the owner is told on their phone (notification_service, channels "telegram" and "whatsapp"):
#
#   stock_requested      a branch asked the main warehouse for materials (material_issue.request_approval): which
#                        warehouse they are for, and what was asked for
#   send_daily_summary   every day at 10 pm (hooks.py: scheduler_events): the day's revenue and the number of
#                        bookings held that day, the total and business by business
#
# The owner is every enabled user holding the owner's role. Only those listed in the site's
# imed_telegram_chats or imed_whatsapp_recipients get a message, on the channel they are listed for (see
# notification_service.py); with nobody listed, nothing is sent and nothing fails. Each owner reads the message in their own language (User > Language), whoever or whatever
# caused it: the scheduler runs in the site's language, and a branch user may work in another.
#
# The figures are the dashboard's own: revenue from the general ledger by cost center
# (owner_dashboard.revenue_by_business), bookings by the "held" rule (booking_rules.NOT_HELD).

from collections import Counter
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, formatdate, today

from imed_erp import notification_service
from imed_erp.imederp.booking_rules import NOT_HELD
from imed_erp.imederp.owner_dashboard import revenue_by_business
from imed_erp.imederp.roles import OWNER


def owners():
	users = frappe.get_all("Has Role", filters={"role": OWNER, "parenttype": "User"}, pluck="parent")
	return frappe.get_all("User", filters={"name": ("in", users), "enabled": 1}, pluck="name") if users else []


@contextmanager
def language_of(user):
	before = frappe.local.lang
	frappe.local.lang = frappe.db.get_value("User", user, "language") or before
	try:
		yield
	finally:
		frappe.local.lang = before


def short(name):
	"""A warehouse or cost center without the company's abbreviation: "مخزن الأزاريطة - MMG" -> "مخزن الأزاريطة"."""
	return (name or "").rsplit(" - ", 1)[0]


def stock_requested(doc):
	"""Tell the owner about a branch's Material Request that was just sent for approval."""
	warehouses = "، ".join(sorted({short(row.warehouse) for row in doc.items if row.warehouse}))
	items = "، ".join(f"{row.item_name or row.item_code} × {flt(row.qty):g} {row.uom or ''}".strip() for row in doc.items)
	for user in owners():
		with language_of(user):
			notification_service.notify(
				"owner_stock_request", [user], {"warehouse": warehouses, "items": items, "request": doc.name}
			)


def bookings_by_business(date):
	"""{cost center: number of bookings held on that date}."""
	return Counter(
		frappe.get_all("Booking", filters={"booking_date": date, "status": ("not in", NOT_HELD)}, pluck="cost_center")
	)


def daily_summary(date=None):
	"""The message: the day's totals, then a line for each business that had revenue or bookings."""
	date = date or today()
	revenue = revenue_by_business(date, date)
	bookings = bookings_by_business(date)
	lines = [
		_("IMED on {0}").format(formatdate(date)),
		_("Revenue: {0}").format(fmt_money(sum(revenue.values()), precision=2)),
		_("Bookings: {0}").format(sum(bookings.values())),
	]
	businesses = sorted(set(revenue) | set(bookings), key=lambda b: (-flt(revenue.get(b)), b or ""))
	if businesses:
		lines.append("")
	for business in businesses:
		line = f"{short(business) or _('No business')}: {fmt_money(flt(revenue.get(business)), precision=2)}"
		if bookings.get(business):
			line += " · " + _("{0} bookings").format(bookings[business])
		lines.append(line)
	return "\n".join(lines)


def send_daily_summary():
	for user in owners():
		with language_of(user):
			message = daily_summary()
			notification_service.notify(
				"owner_daily_summary", [user], {"subject": message.split("\n", 1)[0], "message": message}
			)
