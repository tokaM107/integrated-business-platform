# A library's own screen (مكتبتي), for its shared account (owner, 4 Nov 2026: one account a library, a very simple
# screen): today's counters, something finished (an ink bottle, a box of paper), the stock it holds, and a request
# for more. Each action here is checked on the server: the account works in its own library and store only, and
# never sees money.
#
#   used_up      takes the finished items off the library's store (a Stock Entry, Material Issue, posted by the
#                system: the account has no right on stock entries)
#   count        the quantities the library holds now (a Stock Count, as a library manager would make it)
#   ask_for      a stock request: from the store that supplies the branches (Raghad approves), or a purchase
#                request when the library's store is that store itself (Mawasah)

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, nowtime, today

ROLE = "Library Staff"
SUPPLY_GROUPS = ("ورق", "أحبار")
# What the role may do, nothing more (setup/setup_users.py applies it): its screen's documents, and reading what
# they link to. No sales, accounts, cash or stock entries (a finished item is taken off by the system, used_up).
STAFF_RIGHTS = {
	"Daily Counter Reading": {"read": 1, "write": 1, "create": 1, "submit": 1},
	"Printer Reading": {"read": 1, "write": 1, "create": 1, "submit": 1},
	"Stock Count": {"read": 1, "write": 1, "create": 1, "submit": 1},
	"Material Request": {"read": 1, "write": 1, "create": 1, "submit": 1},
	"Printing Machine": {"read": 1},
	"Item": {"read": 1},
	"Item Group": {"read": 1},
	"Warehouse": {"read": 1},
	"Cost Center": {"read": 1},
	"UOM": {"read": 1},
}


def check_staff():
	if ROLE not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
		frappe.throw(_("This screen is the library's."), frappe.PermissionError)


def allowed(doctype):
	return frappe.get_all("User Permission", filters={"user": frappe.session.user, "allow": doctype}, pluck="for_value")


def my_library() -> frappe._dict:
	"""The account's library (its Cost Center permission) and its store (its leaf Warehouse permission)."""
	libraries = allowed("Cost Center")
	stores = [w for w in allowed("Warehouse") if not frappe.db.get_value("Warehouse", w, "is_group")]
	if len(libraries) != 1 or len(stores) != 1:
		frappe.throw(_("This account is not set to one library and one store. Ask the owner."), title=_("Not Set Up"))
	return frappe._dict(library=libraries[0], store=stores[0], company=frappe.db.get_value("Warehouse", stores[0], "company"))


def supply_items() -> list[frappe._dict]:
	groups = [g for g in SUPPLY_GROUPS if frappe.db.exists("Item Group", g)]
	return frappe.get_all(
		"Item", filters={"item_group": ("in", groups), "disabled": 0, "is_stock_item": 1}, fields=["name", "item_name", "stock_uom"], order_by="item_group desc, item_name"
	)


UNIT_NAMES = {"Box": "كرتونة", "Ream": "رزمة", "Nos": "", "Unit": ""}


def screen_unit(item_code):
	"""(unit, sheets or pieces in one) the screen counts an item in: its largest unit (paper in boxes of 2,500 sheets,
	so "a box finished" takes off a box, not a sheet); its stock unit when it has no other."""
	rows = frappe.get_all("UOM Conversion Detail", filters={"parent": item_code, "parenttype": "Item"}, fields=["uom", "conversion_factor"])
	best = max(rows, key=lambda r: flt(r.conversion_factor), default=None)
	if best and flt(best.conversion_factor) > 1:
		return best.uom, flt(best.conversion_factor)
	return frappe.db.get_value("Item", item_code, "stock_uom"), 1.0


def on_hand(item_code, store):
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": store}, "actual_qty"))


def check_item(item_code):
	if item_code not in {i.name for i in supply_items()}:
		frappe.throw(_("{0} is not one of the library's supplies.").format(item_code))


@frappe.whitelist()
def get_desk():
	"""What the screen shows: the library, its supplies with what it holds, today's counters, its last requests."""
	check_staff()
	mine = my_library()
	items = []
	for i in supply_items():
		unit, factor = screen_unit(i.name)
		name = UNIT_NAMES.get(unit, unit)
		items.append({
			"item_code": i.name,
			"item_name": f"{i.item_name} ({name})" if name else i.item_name,
			"unit": unit,
			"qty": flt(on_hand(i.name, mine.store) / factor, 2),
		})
	counter = frappe.db.get_value("Daily Counter Reading", {"branch": mine.library, "reading_date": today(), "docstatus": ("<", 2)}, ["name", "docstatus"], as_dict=True)
	requests = frappe.get_all(
		"Material Request",
		filters={"owner": frappe.session.user, "docstatus": ("<", 2)},
		fields=["name", "transaction_date", "status", "custom_approval_status", "material_request_type"],
		order_by="creation desc",
		limit=5,
	) if frappe.get_meta("Material Request").has_field("custom_approval_status") else []
	return {
		"library": mine.library,
		"library_name": frappe.db.get_value("Cost Center", mine.library, "cost_center_name"),
		"store": mine.store,
		"items": items,
		"counter_today": counter,
		"requests": requests,
	}


@frappe.whitelist(methods=["POST"])
def used_up(item_code, qty=1):
	"""Something finished in the library: taken off its store, never more than the store holds."""
	check_staff()
	mine = my_library()
	check_item(item_code)
	qty = flt(qty)
	if qty <= 0:
		frappe.throw(_("How many finished?"))
	unit, factor = screen_unit(item_code)
	qty = flt(qty * factor, 3)  # in the stock unit (sheets for paper)
	held = on_hand(item_code, mine.store)
	if qty > held:
		frappe.throw(
			_("The store holds {0} of {1}. Enter what you hold first (رصيد المخزون).").format(flt(held / factor, 2), frappe.db.get_value("Item", item_code, "item_name")),
			title=_("Not Enough"),
		)
	from imed_erp.imederp.paper_use import paper_expense_account
	from imed_erp.imederp.system_user import as_administrator

	user = frappe.session.user
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Issue",
			"company": mine.company,
			"remarks": _("Finished in the library, entered by {0}.").format(frappe.utils.get_fullname(user)),
			"items": [
				{"item_code": item_code, "qty": qty, "s_warehouse": mine.store, "cost_center": mine.library, "expense_account": paper_expense_account(mine.company)}
			],
		}
	)
	with as_administrator():
		entry.insert()
		entry.submit()
	frappe.clear_messages()
	return {"entry": entry.name, "qty": flt(on_hand(item_code, mine.store) / factor, 2)}


@frappe.whitelist(methods=["POST"])
def count(quantities):
	"""What the library holds now, item by item: a Stock Count of its store (paper and ink, a periodic count)."""
	check_staff()
	mine = my_library()
	quantities = json.loads(quantities) if isinstance(quantities, str) else (quantities or {})
	rows = []
	for item_code, qty in quantities.items():
		if qty in (None, ""):
			continue
		check_item(item_code)
		if flt(qty) < 0:
			frappe.throw(_("A quantity cannot be negative."))
		from imed_erp.imederp.doctype.stock_count.stock_count import first_rate

		if not on_hand(item_code, mine.store) and not first_rate(item_code):
			# A first count needs the item's price (the inks' come from Printing Cost Settings, setup_inks.py).
			frappe.throw(
				_("{0} has no price in the system yet. Ask the owner to enter it, then count again.").format(frappe.db.get_value("Item", item_code, "item_name")),
				title=_("No Price"),
			)
		rows.append({"item_code": item_code, "counted_qty": flt(flt(qty) * screen_unit(item_code)[1], 3)})
	if not rows:
		frappe.throw(_("Enter at least one quantity."))
	doc = frappe.get_doc(
		{
			"doctype": "Stock Count",
			"store": mine.store,
			"branch": mine.library,
			"count_type": "Periodic (Consumables)",  # paper and ink, counted every few days (setup_library.py)
			"posting_date": today(),
			"posting_time": nowtime(),
			"counted_by": frappe.session.user,
			"items": rows,
		}
	).insert()
	doc.submit()
	frappe.clear_messages()
	return {"count": doc.name, "items": {r["item_code"]: flt(on_hand(r["item_code"], mine.store) / screen_unit(r["item_code"])[1], 2) for r in rows}}


@frappe.whitelist(methods=["POST"])
def ask_for(item_code, qty, note=None):
	"""A stock request: to the store that supplies the branches, for Raghad's approval; a purchase request when the
	library's store is that store itself (Mawasah)."""
	check_staff()
	mine = my_library()
	check_item(item_code)
	qty = flt(qty)
	if qty <= 0:
		frappe.throw(_("How many do you need?"))
	unit, factor = screen_unit(item_code)
	from imed_erp.imederp.material_issue import is_supplying_warehouse

	supplier = None
	if not is_supplying_warehouse(mine.store):
		suppliers = frappe.get_all("Warehouse", filters={"company": mine.company, "is_group": 0, "custom_supplies_branches": 1}, pluck="name")
		# The supplying store that holds the item, else the first one.
		supplier = max(suppliers, key=lambda w: on_hand(item_code, w)) if suppliers else None
	doc = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Transfer" if supplier else "Purchase",
			"company": mine.company,
			"transaction_date": today(),
			"schedule_date": today(),
			"set_warehouse": mine.store,
			"set_from_warehouse": supplier,
			"items": [
				{"item_code": item_code, "qty": qty, "uom": unit, "conversion_factor": factor, "warehouse": mine.store, "from_warehouse": supplier, "schedule_date": today(), "cost_center": mine.library, "description": (note or "").strip()[:500] or None}
			],
		}
	).insert()
	if supplier:
		from imed_erp.imederp.material_issue import request_approval

		request_approval(doc.name)  # Pending Approval: Raghad approves it
	else:
		doc.submit()  # a purchase request, for whoever buys
	frappe.clear_messages()  # ERPNext's own notes ("Item rates have been updated...") mean nothing to the library
	return {"request": doc.name, "type": doc.material_request_type}
