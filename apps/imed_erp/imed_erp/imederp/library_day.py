# A library's day, for the owner when he asks (the owner, 15 Nov 2026: "how much paper Azarita has, how much paper
# and ink it used today"). Read from what each library records every day on its screen مكتبتي (library_desk.py):
#
#   counters    the day's Daily Counter Reading: the morning's and the evening's figure of each machine, the sheets
#               printed, the paper it took off the store, the sheets spoiled; whether the day is recorded at all
#   used        what left the library's store as used that day, item by item: paper (sheets and boxes) and ink
#               (sold, or taken off when finished: owner_periods.used_between, transfers and counts are not use)
#   on hand     what the store holds now, in the unit the library counts it in (paper in boxes, ink in bottles)
#   counted     the store's last count (Stock Count) and when it was
#
# The center's store too (the owner, 15 Nov 2026: one ink, the cheaper, is kept at Mawasah's library; the other, the
# dearer, at the center, مخزن سنتر Imed — أدوات مكتبية): what it holds of each ink, what it used that day, what it sent
# on to the libraries that day, its last count. Every ink, whichever machine it is for.
#
# Read as the owner (or the system's manager): each library's own store, never another's; nothing is written.
import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from imed_erp.imederp.center_store import INK_GROUP, center_items, center_store  # noqa: F401 (INK_GROUP: the tests)
from imed_erp.imederp.owner_periods import library_stores, store_library, used_between
from imed_erp.imederp.owner_yesterday import check_owner

CENTER_WORDS = ("سنتر", "center", "centre", "imed")


def asks_center(asked):
	text = str(asked or "").strip().lower()
	return bool(text) and any(w in text for w in CENTER_WORDS)


def libraries():
	"""{library cost center: its store}, from the stores the library accounts work in."""
	out = {}
	for store in library_stores():
		library = store_library(store)
		if library and library not in out:
			out[library] = store
	return out


def find_library(asked):
	"""The library asked for by any part of its name ("الأزاريطة", "Azarita", "مكتبة المواساة"), or all of them."""
	known = libraries()
	if not asked:
		return known
	if asks_center(asked):
		return {}
	words = {"azarita": "الأزاريطة", "azareeta": "الأزاريطة", "mawasah": "المواساة", "mowasah": "المواساة", "mawasa": "المواساة"}
	text = str(asked).strip().lower()
	text = words.get(text, text).replace("أ", "ا").replace("إ", "ا")
	found = {lib: store for lib, store in known.items() if text in lib.replace("أ", "ا").replace("إ", "ا").lower()}
	if not found:
		frappe.throw(_("No library called {0}. The libraries: {1}.").format(asked, "، ".join(lib.rsplit(" - ", 1)[0] for lib in known)))
	return found


def counters(library, day):
	doc = frappe.get_all(
		"Daily Counter Reading",
		filters={"branch": library, "reading_date": day, "docstatus": ["<", 2]},
		fields=["name", "docstatus", "total_consumed", "paper_issued", "spoiled_sheets", "sold_sheets", "variance"],
		limit=1,
	)
	if not doc:
		return {"state": "not_recorded", "note": _("No counters recorded for this day.")}
	d = doc[0]
	machines = frappe.get_all(
		"Daily Counter Reading Item",
		filters={"parent": d.name},
		fields=["machine", "opening_reading", "closing_reading", "consumed", "fault"],
		order_by="idx",
	)
	return {
		"state": "closed" if d.docstatus == 1 else "morning_only",
		"note": "" if d.docstatus == 1 else _("Only the morning's counters are recorded; the evening's are not yet."),
		"sheets_printed": cint(d.total_consumed),
		"paper_taken_from_store_sheets": cint(d.paper_issued),
		"spoiled_sheets": cint(d.spoiled_sheets),
		"sold_sheets": cint(d.sold_sheets),
		"machines": [
			{"machine": m.machine, "morning": cint(m.opening_reading), "evening": cint(m.closing_reading) if d.docstatus == 1 else None, "printed": cint(m.consumed), "fault": bool(m.fault)}
			for m in machines
		],
	}


def sent_between(item_code, store, start, end):
	"""What a store sent on to another (a Material Transfer): moved, not used."""
	return -flt(
		frappe.db.sql(
			"""select coalesce(sum(sle.actual_qty), 0) from `tabStock Ledger Entry` sle join `tabStock Entry` se on se.name = sle.voucher_no
			where sle.item_code = %s and sle.warehouse = %s and sle.is_cancelled = 0 and sle.actual_qty < 0 and sle.voucher_type = 'Stock Entry'
			and se.stock_entry_type = 'Material Transfer' and sle.posting_date between %s and %s""",
			(item_code, store, start, end),
		)[0][0]
	)


def supplies(library, store, day, items=None, sent=False):
	from imed_erp.imederp.library_desk import UNIT_NAMES, screen_unit, supply_items

	rows = []
	for item in supply_items(library) if items is None else items:
		unit, factor = screen_unit(item.name)
		on_hand = flt(frappe.db.get_value("Bin", {"item_code": item.name, "warehouse": store}, "actual_qty"))
		used = used_between(item.name, store, day, day)
		row = {
			"item": item.item_name,
			"unit": UNIT_NAMES.get(unit, unit) or item.stock_uom,
			"on_hand": flt(on_hand / factor, 2),
			"used_that_day": flt(used / factor, 2),
		}
		if sent:
			row["sent_to_libraries_that_day"] = flt(sent_between(item.name, store, day, day) / factor, 2)
		if factor > 1:  # paper: the sheets as well as the boxes
			row["on_hand_sheets"] = flt(on_hand, 0)
			row["used_that_day_sheets"] = flt(used, 0)
		rows.append(row)
	return rows


def last_count(store):
	last = frappe.get_all("Stock Count", filters={"store": store, "docstatus": 1}, fields=["name", "posting_date"], order_by="posting_date desc, creation desc", limit=1)
	return {"date": str(last[0].posting_date), "count": last[0].name} if last else None


def day_report(library=None, day=None):
	check_owner()
	day = getdate(day or nowdate())
	out = []
	for lib, store in find_library(library).items():
		out.append(
			{
				"library": lib.rsplit(" - ", 1)[0],
				"store": store.rsplit(" - ", 1)[0],
				"day": str(day),
				"counters": counters(lib, day),
				"supplies": supplies(lib, store, day),
				"last_stock_count": last_count(store),
			}
		)
	center = center_store()
	if center and (not library or asks_center(library)):
		out.append(
			{
				"store": center.rsplit(" - ", 1)[0],
				"kind": "center",
				"day": str(day),
				"note": _("The center's store: no counters of its own; what it sends on to the libraries is moved, not used."),
				"supplies": supplies(None, center, day, items=center_items(center), sent=True),
				"last_stock_count": last_count(center),
			}
		)
	return out


@frappe.whitelist()
def get_day(library=None, day=None):
	return day_report(library, day)
