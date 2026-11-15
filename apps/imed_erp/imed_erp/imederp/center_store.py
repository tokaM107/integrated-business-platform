# The center's store, kept by the owner himself (the owner, 15 Nov 2026: the dearer ink is kept at the center,
# مخزن سنتر Imed — أدوات مكتبية, and the owner is the one in charge of it). From his page (the stock section,
# owner_periods.stock) he does there what a library does on مكتبتي:
#
#   count   what the store holds now, item by item (a Stock Count of the store, as a library counts its own)
#   send    some of it on to a library (a Stock Entry, Material Transfer, into the library's store): moved, not used;
#           the library's own day then shows it held, and the center's day shows it sent (library_day.py)
#
# The owner's alone (or the system's manager): no library account, accountant or branch manager.
from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt, nowtime, today

from imed_erp.imederp.owner_yesterday import check_owner

CENTER_STORE = "مخزن سنتر Imed — أدوات مكتبية"
INK_GROUP = "أحبار"


def center_store():
	from imed_erp.imederp.business_figures import company

	return frappe.db.get_value("Warehouse", {"company": company(), "is_group": 0, "warehouse_name": CENTER_STORE})


def the_store():
	store = center_store()
	if not store:
		frappe.throw(_("The center's store ({0}) is not set up.").format(CENTER_STORE), title=_("Not Set Up"))
	return store


def center_items(store):
	"""The center's supplies: every ink, and any other supply it ever held."""
	from imed_erp.imederp.library_desk import supply_items

	held = set(frappe.get_all("Stock Ledger Entry", filters={"warehouse": store, "is_cancelled": 0}, pluck="item_code", distinct=True))
	return [i for i in supply_items() if i.name in held or frappe.db.get_value("Item", i.name, "item_group") == INK_GROUP]


def check_item(item_code, store):
	if item_code not in {i.name for i in center_items(store)}:
		frappe.throw(_("{0} is not one of the center's supplies.").format(item_code))


@frappe.whitelist()
def get_center():
	"""What the owner's two dialogs need: the center's supplies with what it holds, and the libraries to send to."""
	check_owner()
	from imed_erp.imederp.library_day import libraries
	from imed_erp.imederp.library_desk import UNIT_NAMES, on_hand, screen_unit

	store = the_store()
	items = []
	for i in center_items(store):
		unit, factor = screen_unit(i.name)
		name = UNIT_NAMES.get(unit, unit)
		items.append({"item_code": i.name, "item_name": f"{i.item_name} ({name})" if name else i.item_name, "qty": flt(on_hand(i.name, store) / factor, 2)})
	return {
		"store": store,
		"items": items,
		"libraries": [{"library": lib, "name": lib.rsplit(" - ", 1)[0]} for lib in libraries()],
	}


@frappe.whitelist(methods=["POST"])
def count(quantities):
	"""What the center's store holds now: a Stock Count of it."""
	check_owner()
	from imed_erp.imederp.doctype.stock_count.stock_count import first_rate
	from imed_erp.imederp.library_desk import on_hand, screen_unit

	store = the_store()
	quantities = json.loads(quantities) if isinstance(quantities, str) else (quantities or {})
	rows = []
	for item_code, qty in quantities.items():
		if qty in (None, ""):
			continue
		check_item(item_code, store)
		if flt(qty) < 0:
			frappe.throw(_("A quantity cannot be negative."))
		if not on_hand(item_code, store) and not first_rate(item_code):
			frappe.throw(
				_("{0} has no price in the system yet. Enter it in Printing Cost Settings, then count again.").format(frappe.db.get_value("Item", item_code, "item_name")),
				title=_("No Price"),
			)
		rows.append({"item_code": item_code, "counted_qty": flt(flt(qty) * screen_unit(item_code)[1], 3)})
	if not rows:
		frappe.throw(_("Enter at least one quantity."))
	doc = frappe.get_doc(
		{
			"doctype": "Stock Count",
			"store": store,
			"count_type": "Periodic (Consumables)",
			"posting_date": today(),
			"posting_time": nowtime(),
			"counted_by": frappe.session.user,
			"items": rows,
		}
	).insert()
	doc.submit()
	frappe.clear_messages()
	return {"count": doc.name, "items": {r["item_code"]: flt(on_hand(r["item_code"], store) / screen_unit(r["item_code"])[1], 2) for r in rows}}


@frappe.whitelist(methods=["POST"])
def send(item_code, qty, library, received_by=None):
	"""Some of the center's stock on to a library's store, never more than the center holds, with who received it
	(a transfer between branches always says who, material_issue.check_transfer_between_branches)."""
	check_owner()
	from imed_erp.imederp.library_day import libraries
	from imed_erp.imederp.library_desk import on_hand, screen_unit
	from imed_erp.imederp.material_issue import needs_machine
	from imed_erp.imederp.system_user import as_administrator

	store = the_store()
	check_item(item_code, store)
	to = libraries().get(library)
	if not to:
		frappe.throw(_("Choose the library to send to."))
	received_by = (received_by or "").strip()
	if not received_by:
		frappe.throw(_("Who received it at the library?"), title=_("Missing Recipient"))
	if needs_machine(item_code):
		frappe.throw(_("{0} goes to a printing machine: send it from a stock entry, with its machine.").format(frappe.db.get_value("Item", item_code, "item_name")))
	qty = flt(qty)
	if qty <= 0:
		frappe.throw(_("How many to send?"))
	unit, factor = screen_unit(item_code)
	qty = flt(qty * factor, 3)
	held = on_hand(item_code, store)
	if qty > held:
		frappe.throw(
			_("The center holds {0} of {1}. Count it first.").format(flt(held / factor, 2), frappe.db.get_value("Item", item_code, "item_name")),
			title=_("Not Enough"),
		)
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"company": frappe.db.get_value("Warehouse", store, "company"),
			"custom_received_by": received_by,
			"remarks": _("Sent from the center to {0} by {1}.").format(library.rsplit(" - ", 1)[0], frappe.utils.get_fullname(frappe.session.user)),
			"items": [{"item_code": item_code, "qty": qty, "s_warehouse": store, "t_warehouse": to, "cost_center": library}],
		}
	)
	with as_administrator():
		entry.insert()
		entry.submit()
	frappe.clear_messages()
	return {"entry": entry.name, "left": flt(on_hand(item_code, store) / factor, 2), "library_holds": flt(on_hand(item_code, to) / factor, 2)}
