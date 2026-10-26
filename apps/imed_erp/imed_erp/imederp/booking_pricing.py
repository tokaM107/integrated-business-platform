# The price of a booking entered here (HAL-03, STU-04, STU-05, HAL-11, HAL-12), worked out on the server when it
# is saved. Everything is priced the way the rest of the system sells: by the Item Price of a service item, which
# only the owner changes (SEC-02). Nothing is priced in code.
#
#   price list   the customer's category's (Customer Group > Default Price List, or the customer's own), HAL-03;
#                an item with no price there takes the default selling price list's. The list used is kept.
#   by the hour  the resource's service item: its price x the booking's hours.
#   package      Once: the package's price is the booking's price, for a booking up to the package's hours; a
#                longer booking is refused (the requirements say nothing of extra hours on a package). Per Hour: its
#                price x the hours (a podcast with two cameras).
#   extras       each extra's price x its pieces, x the hours when it is charged per piece per hour (requirements
#                4.8: 50 a piece an hour). Each extra is listed once.
#   hall         Fixed Rent: priced as above (the hall's price, HAL-03). Revenue Share: no rent; the center's
#                income is its share of what was collected from the attendees (revenue_share below), and the
#                customer pays only the extras.
#
# Hours are the booking's exact length (90 minutes = 1.5 hours); nothing is rounded up to a whole hour, since
# no rounding rule was given. Amounts are rounded to the piastre.
#
# Prices are those in force on the day the booking is priced, when its price is agreed, not on the day booked
# (a booking entered the day after it took place is priced at today's prices).
#
# The prices found are kept on the booking (its rate, each extra's rate). They are looked up again only when
# what the price depends on changes (resource, customer, hours, package, model, extras): a later change of the
# price list does not change a booking already priced.

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money, getdate, today

FIXED_RENT, REVENUE_SHARE = "Fixed Rent", "Revenue Share"
ONCE, PER_HOUR = "Once", "Per Hour"
PIECE_PER_HOUR, PIECE = "Per Piece per Hour", "Per Piece"
HALL = "Hall"


def money(value):
	return fmt_money(flt(value, 2), precision=2)


def price_lists(customer):
	"""The customer's category's price list first, then the default selling one."""
	from erpnext.accounts.party import get_default_price_list

	default = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	own = get_default_price_list(frappe.get_cached_doc("Customer", customer)) if customer else None
	return [p for p in dict.fromkeys([own, default]) if p]


def item_price(item, lists, on_date):
	"""(price, price list) of `item` on `on_date`, from the first list that has one; None when none has."""
	for price_list in lists:
		rows = frappe.db.sql(
			"""select price_list_rate from `tabItem Price`
			where item_code = %(item)s and price_list = %(list)s and selling = 1 and ifnull(customer, '') = ''
			and (valid_from is null or valid_from <= %(day)s) and (valid_upto is null or valid_upto >= %(day)s)
			order by valid_from desc limit 1""",
			{"item": item, "list": price_list, "day": getdate(on_date)},
		)
		if rows:
			return flt(rows[0][0]), price_list
	return None


def price_of(item, lists, on_date, what):
	found = item_price(item, lists, on_date)
	if not found or found[0] <= 0:
		frappe.throw(
			_("{0} has no price for {1} in {2}. The owner sets it in Item Price.").format(
				what, item, " / ".join(lists) or "-"
			),
			title=_("No Price"),
		)
	return found


def pricing_key(doc):
	"""What the price depends on: when it changes, the booking is priced again."""
	key = [
		doc.resource,
		doc.customer,
		flt(doc.hours, 2),
		doc.package or "",
		doc.rental_model or "",
		[[row.extra, cint(row.quantity)] for row in doc.extras],
	]
	# Only a session on prepaid hours adds these, so the bookings priced before keep their key (and their prices).
	if doc.get("hour_package"):
		key.append([doc.hour_package, flt(doc.extra_hours, 4)])
	return json.dumps(key, ensure_ascii=False)


def price_booking(doc):
	"""Set the booking's rate, base amount, extras and total. Prices are looked up only when what they depend on
	changed (or the booking is new); otherwise the kept prices are used again."""
	reprice = doc.is_new() or doc.pricing_key != pricing_key(doc) or not doc.price_list
	lists = price_lists(doc.customer) if reprice else [doc.price_list]
	set_base(doc, lists, reprice)
	set_extras(doc, lists, reprice)
	doc.total_amount = flt(flt(doc.base_amount) + flt(doc.extras_amount), 2)
	doc.pricing_key = pricing_key(doc)


def set_base(doc, lists, reprice):
	resource = frappe.get_doc("Booking Resource", doc.resource)
	if doc.resource_type == HALL and doc.rental_model == REVENUE_SHARE:
		if doc.package:
			frappe.throw(_("A revenue-share booking pays no rent, so it takes no package."))
		doc.rate, doc.base_amount = 0, 0
		doc.price_list = doc.price_list or (lists[0] if lists else None)
		doc.pricing_note = _("Revenue share: no rent; the center keeps its share of what it collects.")
		return

	hours = exact_hours(doc)
	if doc.get("hour_package"):
		# Prepaid hours (studio_hour_package.py): the hours the package covers are paid by its own invoice; only the
		# hours beyond it, once that is decided, are priced, at the hourly price.
		extra = flt(doc.extra_hours, 4)
		if not extra:
			doc.rate, doc.base_amount = 0, 0
			doc.price_list = doc.price_list or (lists[0] if lists else None)
			doc.pricing_note = _("Prepaid hours {0}: {1} hours from the package.").format(doc.hour_package, flt(doc.package_hours, 2))
			return
		if not resource.item:
			frappe.throw(_("{0} has no price by the hour for the hours beyond the package.").format(doc.resource), title=_("No Price"))
		if reprice or not flt(doc.rate):
			doc.rate, doc.price_list = price_of(resource.item, lists, today(), doc.resource)
		doc.base_amount = flt(flt(doc.rate) * extra, 2)
		doc.pricing_note = _("Prepaid hours {0}: {1} hours from the package; {2} hours beyond it x {3} ({4}), approved by {5}.").format(
			doc.hour_package, flt(doc.package_hours, 2), flt(extra, 2), money(doc.rate), doc.price_list, doc.extra_hours_approved_by
		)
		return
	if doc.package:
		package = frappe.get_doc("Booking Package", doc.package)
		if package.resource != doc.resource:
			frappe.throw(
				_("Package {0} is for {1}, not {2}.").format(doc.package, package.resource, doc.resource)
			)
		if reprice:
			if package.disabled:
				frappe.throw(_("Package {0} is disabled.").format(doc.package))
			doc.rate, doc.price_list = price_of(package.item, lists, today(), doc.package)
		if package.charged == ONCE:
			if flt(package.hours) and flt(hours, 2) > flt(package.hours):
				frappe.throw(
					_("Package {0} covers up to {1} hours; this booking is {2}. Book the rest separately, or choose another package.").format(
						doc.package, flt(package.hours), flt(hours, 2)
					),
					title=_("Longer Than the Package"),
				)
			doc.base_amount = flt(doc.rate, 2)
			doc.pricing_note = _("Package {0}: {1} ({2}).").format(
				doc.package, money(doc.rate), doc.price_list
			)
		else:
			doc.base_amount = flt(flt(doc.rate) * hours, 2)
			doc.pricing_note = _("Package {0}: {1} hours x {2} ({3}).").format(doc.package, flt(hours, 2), money(doc.rate), doc.price_list)
		return

	if not resource.item:
		frappe.throw(
			_("{0} has no price by the hour. Choose one of its packages.").format(doc.resource),
			title=_("No Price"),
		)
	if reprice:
		doc.rate, doc.price_list = price_of(resource.item, lists, today(), doc.resource)
	doc.base_amount = flt(flt(doc.rate) * hours, 2)
	doc.pricing_note = _("{0} hours x {1} ({2}).").format(flt(hours, 2), money(doc.rate), doc.price_list)


def set_extras(doc, lists, reprice):
	seen = set()
	total = 0
	hours = exact_hours(doc)
	for row in doc.extras:
		if row.extra in seen:
			frappe.throw(
				_("{0} is listed twice. Put all its pieces on one row.").format(row.extra),
				title=_("Extra Listed Twice"),
			)
		seen.add(row.extra)
		if cint(row.quantity) <= 0 or flt(row.quantity) != cint(row.quantity):
			frappe.throw(_("Enter the pieces of {0}: a whole number, more than zero.").format(row.extra))
		extra = frappe.get_doc("Booking Extra", row.extra)
		if extra.applies_to not in ("Hall and Studio", doc.resource_type):
			frappe.throw(_("{0} is not offered on a {1} booking.").format(row.extra, _(doc.resource_type)))
		if reprice or not row.rate:
			if extra.disabled:
				frappe.throw(_("Extra {0} is disabled.").format(row.extra))
			row.rate = price_of(extra.item, lists, today(), row.extra)[0]
			row.item, row.charged = extra.item, extra.charged
		row.hours = flt(hours, 2) if row.charged == PIECE_PER_HOUR else 0
		row.amount = flt(cint(row.quantity) * flt(row.rate) * (hours if row.charged == PIECE_PER_HOUR else 1), 2)
		total += row.amount
	doc.extras_amount = flt(total, 2)


def exact_hours(doc):
	"""QA-13: the booking's length in hours, unrounded (40 minutes = 2/3 hour), for working out money. Booking.hours
	is rounded to 2 decimals for the screen; a price from it would be off (0.67 x 2,250 = 1,507.50, not 1,500)."""
	from datetime import datetime

	from frappe.utils import get_time

	from datetime import timedelta

	from frappe.utils import cint, getdate

	if not (doc.from_time and doc.to_time):
		return flt(doc.hours)
	# A booking across midnight (ends_next_day) ends on the next day; the length is the exact gap between the two.
	day = getdate(doc.booking_date) if doc.get("booking_date") else datetime.min
	starts = datetime.combine(day, get_time(doc.from_time))
	ends = datetime.combine(day + timedelta(days=cint(doc.get("ends_next_day"))), get_time(doc.to_time))
	return (ends - starts).total_seconds() / 3600


def revenue_share(collected, percent):
	"""(lecturer's share, center's share) of what was collected from the attendees (HAL-12). Shared is what was
	collected, not the expected revenue: money not collected is not shared. The lecturer's share is rounded to the
	piastre and the center keeps the rest, so the two always add up to what was collected."""
	collected = flt(collected, 2)
	lecturer = flt(collected * flt(percent) / 100, 2)
	return lecturer, flt(collected - lecturer, 2)
