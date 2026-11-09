# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The owner's prices, a business at a time (owner, 9 Nov 2026: "a page where the owner picks the business and sees the
# prices of everything in it; a change is heard by every account and applies to new records, not old ones").
#
#   libraries  what the supplies cost to buy (paper, inks, wire, covers), what a printed sheet costs from them, and
#              the selling prices beside their cost and margin: the selling price is set from what was bought
#   app        the fee per student, by the number of students in a course (Platform Fee Schedule)
#   halls      Sparkle's prices, shown (they are changed on Sparkle, which the ERP reads only)
#   studio     XStudio's prices, shown (changed on XStudio)
#
# A change is dated today: a selling or buying price is a new Item Price from today (the one before closes
# yesterday), the fee per student a new schedule from today, a supply's cost the settings' field. What was sold,
# booked or charged before keeps the price it was given (booking_pricing.py, the documents' own rates).

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from imed_erp.imederp.owner_yesterday import check_owner

SETTINGS = "Printing Cost Settings"
PAPER = "A4-PAPER"
SHEETS_PER_BOX = 2500
LIBRARY_SERVICES = "خدمات المكتبات"
# A supply's cost: the settings' field, its label, its unit, and the items valued from it (with the part of the
# price one piece is: an Epson set is four colours).
COSTS = [
	("riso_ink_price", "Riso ink, one bottle", "bottle", [("INK-RISO", 1)]),
	("epson_ink_set_price", "Epson ink set (4 colours)", "set", [("INK-EPSON-BK", 4), ("INK-EPSON-C", 4), ("INK-EPSON-M", 4), ("INK-EPSON-Y", 4)]),
	("binding_wire_price", "Binding wire, one piece", "piece", [("BIND-WIRE", 1)]),
	("binding_cover_price", "Plastic cover, one piece", "piece", [("BIND-COVER", 1)]),
]
YIELDS = [("riso_sheets_per_ink", "Sheets one Riso bottle prints"), ("epson_sheets_per_set", "Sheets one Epson set prints")]


@frappe.whitelist()
def get_prices(business):
	check_owner()
	return {"libraries": libraries, "app": app, "halls": halls, "studio": studio}[business]()


# ---------- libraries ----------


def current_price(item_code, price_list, selling=1, day=None):
	"""The item's price in force on `day` (today): the latest from a day not after it."""
	day = getdate(day or nowdate())
	row = frappe.db.sql(
		"""select name, price_list_rate, valid_from from `tabItem Price`
		where item_code = %s and price_list = %s and selling = %s and buying = %s and ifnull(customer, '') = '' and ifnull(supplier, '') = ''
			and (valid_from is null or valid_from <= %s) and (valid_upto is null or valid_upto >= %s)
		order by valid_from desc, modified desc limit 1""",
		(item_code, price_list, cint(selling), 1 - cint(selling), day, day),
		as_dict=True,
	)
	return row[0] if row else None


def buying_list():
	return frappe.db.get_single_value("Buying Settings", "buying_price_list") or "Standard Buying"


def selling_list():
	return frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"


def libraries():
	settings = frappe.get_single(SETTINGS)
	paper = current_price(PAPER, buying_list(), selling=0)
	per_sheet_paper = flt(paper.price_list_rate) if paper else 0
	costs = [{"key": "paper_box", "label": _("A4 paper, one box (2,500 sheets)"), "unit": _("box"), "value": flt(per_sheet_paper * SHEETS_PER_BOX, 2)}]
	costs += [{"key": field, "label": _(label), "unit": _(unit), "value": flt(settings.get(field), 2)} for field, label, unit, _items in COSTS]
	yields = [{"key": field, "label": _(label), "value": cint(settings.get(field))} for field, label in YIELDS]
	# A printed sheet: its paper, its waste, the overheads, and its machine's ink.
	waste, overheads = flt(settings.waste_per_sheet), flt(settings.overheads_per_sheet)
	sheet = []
	for kind, field in (("Riso", "riso_ink_per_sheet"), ("Epson", "epson_ink_per_sheet")):
		ink = flt(settings.get(field)) or flt(frappe.get_meta(SETTINGS).get_field(field).default)
		sheet.append({"machine": kind, "paper": flt(per_sheet_paper, 4), "ink": flt(ink, 4), "waste": waste, "overheads": overheads, "total": flt(per_sheet_paper + ink + waste + overheads, 4)})
	riso_sheet = sheet[0]["total"]
	# What each service costs, for its margin: a printed sheet (Riso); a binding, its wire and its cover.
	cost_of = {"PRINT-SVC": riso_sheet, "BINDING-SVC": flt(settings.binding_wire_price) + flt(settings.binding_cover_price)}
	selling = []
	for item in frappe.get_all("Item", filters={"item_group": LIBRARY_SERVICES, "disabled": 0}, fields=["name", "item_name", "stock_uom"], order_by="item_name"):
		price = current_price(item.name, selling_list())
		cost = cost_of.get(item.name)
		rate = flt(price.price_list_rate) if price else 0
		selling.append(
			{
				"key": item.name,
				"label": item.item_name,
				"value": rate,
				"since": price.valid_from if price else None,
				"cost": cost,
				"margin": flt(rate - cost, 4) if cost is not None and price else None,
			}
		)
	return {"costs": costs, "yields": yields, "sheet": sheet, "selling": selling}


# ---------- app ----------


def current_schedule(day=None):
	name = frappe.db.get_value(
		"Platform Fee Schedule", {"docstatus": 1, "valid_from": ["<=", getdate(day or nowdate())]}, "name", order_by="valid_from desc"
	)
	return frappe.get_doc("Platform Fee Schedule", name) if name else None


def app():
	schedule = current_schedule()
	tiers = sorted(schedule.tiers, key=lambda t: cint(t.from_students)) if schedule else []
	return {
		"since": schedule.valid_from if schedule else None,
		"tiers": [{"from": cint(t.from_students), "to": cint(t.to_students), "value": flt(t.fee_per_student)} for t in tiers],
	}


# ---------- halls and studio: shown, changed where they are booked ----------


def halls():
	try:
		from imed_erp.imederp.sparkle.client import SparkleClient

		client = SparkleClient(frappe.get_single("Sparkle Settings"))
		try:
			rows = client.rows(
				"""select distinct on (hall_slug) hall_slug, first_hour, two_hours, extra_hour, effective_from
				from public.hall_rates where is_active order by hall_slug, effective_from desc"""
			)
		finally:
			client.close()
	except Exception as e:
		return {"error": _("Sparkle's prices cannot be read yet: {0}").format(str(e).splitlines()[0][:160])}
	names = {r.sparkle_hall: r.resource for r in frappe.get_single("Sparkle Settings").hall_map}
	return {
		"rows": [
			{"label": names.get(r["hall_slug"], r["hall_slug"]), "first_hour": r["first_hour"], "two_hours": r["two_hours"], "extra_hour": r["extra_hour"], "since": r["effective_from"]}
			for r in rows
		]
	}


def studio():
	try:
		from imed_erp.imederp.xstudio.client import XStudioClient

		client = XStudioClient(frappe.get_single("XStudio Settings"))
		rooms = client.halls()
	except Exception as e:
		return {"error": _("XStudio's prices cannot be read now: {0}").format(str(e).splitlines()[0][:160])}
	return {"rows": [{"label": r.get("name"), "value": flt(r.get("price_per_hour"))} for r in rooms if r.get("is_active", True)]}


# ---------- changes ----------


@frappe.whitelist(methods=["POST"])
def set_price(business, key, value):
	"""One price, from today. Returns the business's prices as they now are."""
	check_owner()
	value = flt(value)
	if value < 0:
		frappe.throw(_("A price cannot be negative."))
	if business == "libraries":
		if key == "paper_box":
			new_item_price(PAPER, buying_list(), flt(value / SHEETS_PER_BOX, 6), selling=0)
			value_items([(PAPER, SHEETS_PER_BOX)], value)
		elif key in [c[0] for c in COSTS] + [y[0] for y in YIELDS]:
			settings = frappe.get_single(SETTINGS)
			settings.set(key, cint(value) if key in [y[0] for y in YIELDS] else value)
			settings.flags.ignore_permissions = True
			settings.save()
			for field, _label, _unit, items in COSTS:
				if field == key:
					value_items(items, value)
		elif frappe.db.get_value("Item", key, "item_group") == LIBRARY_SERVICES:
			new_item_price(key, selling_list(), value, selling=1)
		else:
			frappe.throw(_("Unknown price."))
	elif business == "app":
		frappe.throw(_("Change the fee per student with its whole table (set_fees)."))
	else:
		frappe.throw(_("These prices are changed where the business is booked."))
	frappe.clear_messages()
	return get_prices(business)


@frappe.whitelist(methods=["POST"])
def set_fees(tiers):
	"""The fee per student from today: a new Platform Fee Schedule (the one in force before stays, as courses were
	charged by it)."""
	check_owner()
	tiers = frappe.parse_json(tiers) or []
	today = getdate(nowdate())
	rows = [{"from_students": cint(t.get("from")), "to_students": cint(t.get("to")), "fee_per_student": flt(t.get("value"))} for t in tiers]
	existing = frappe.db.get_value("Platform Fee Schedule", {"valid_from": today, "docstatus": 1}, "name")
	if existing:
		frappe.throw(_("The fee per student was already changed today ({0}). It can change again from tomorrow.").format(existing), title=_("Changed Today"))
	doc = frappe.get_doc({"doctype": "Platform Fee Schedule", "valid_from": today, "tiers": rows})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	frappe.clear_messages()
	return app()


def new_item_price(item_code, price_list, rate, selling):
	"""The item's price from today: today's price changed if there is one, else a new one from today, and the one in
	force till now closed yesterday."""
	today = getdate(nowdate())
	todays = frappe.db.get_value(
		"Item Price", {"item_code": item_code, "price_list": price_list, "valid_from": today, "customer": ["is", "not set"], "supplier": ["is", "not set"]}, "name"
	)
	if todays:
		frappe.db.set_value("Item Price", todays, "price_list_rate", rate)
		return todays
	before = current_price(item_code, price_list, selling=selling)
	if before and flt(before.price_list_rate) == flt(rate):
		return before.name
	if before:
		frappe.db.set_value("Item Price", before.name, "valid_upto", add_days(today, -1))
	doc = frappe.get_doc(
		{
			"doctype": "Item Price",
			"item_code": item_code,
			"price_list": price_list,
			"price_list_rate": rate,
			"valid_from": today,
			"selling": selling,
			"buying": 1 - selling,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def value_items(items, price):
	"""A supply never counted yet takes its new cost (its first count is valued at it); one with stock keeps its
	moving average, the next purchase brings the new cost in."""
	for item_code, parts in items:
		if not frappe.db.exists("Item", item_code):
			continue
		if frappe.db.exists("Stock Ledger Entry", {"item_code": item_code, "is_cancelled": 0}):
			continue
		frappe.db.set_value("Item", item_code, "valuation_rate", flt(price / parts, 4))
