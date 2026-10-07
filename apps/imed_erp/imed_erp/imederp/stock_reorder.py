# Reorder levels per item AND per warehouse (LIB-04).
#
# The levels live in ERPNext's own table, the item's "Reorder Levels" (Item Reorder: warehouse, reorder
# level, reorder qty, request type), so A4 paper can be reordered at 1,000 in Mawasah and at 500 in
# Azarita. ERPNext's daily job raises a Material Request from it when Stock Settings > auto_indent is on
# (type Transfer for Azarita, which Mawasah supplies; Purchase for Mawasah). This module adds:
#
#   validate_reorder_levels  Item validate: one row per warehouse, never a group warehouse.
#   alert_on_reorder_level   on_submit of stock documents: when an item's stock in one warehouse drops to
#                            or below that warehouse's level, an in-app alert goes to the stock users who
#                            may see that warehouse (notification_service.notify).
#   get_reorder_alerts       Items at or below their level, warehouse by warehouse; used by the
#                            Reorder Alerts report.
#
# Quantities are compared in the item's stock UOM, as stored in the Bin: nothing here depends on how
# other units (ream, carton, ...) convert to it.

import frappe
from frappe import _
from frappe.utils import flt

from imed_erp.notification_service import notify

STOCK_ROLES = ("Stock User", "Stock Manager")


def validate_reorder_levels(doc, method=None):
	"""Item validate. Each warehouse has one level of its own; a group warehouse holds no stock."""
	seen = {}
	for row in doc.get("reorder_levels") or []:
		if not row.warehouse:
			continue
		if row.warehouse in seen:
			frappe.throw(
				_("Row #{0}: warehouse {1} already has a reorder level in row #{2}.").format(
					row.idx, frappe.bold(row.warehouse), seen[row.warehouse]
				)
			)
		seen[row.warehouse] = row.idx
		if frappe.db.get_value("Warehouse", row.warehouse, "is_group"):
			frappe.throw(
				_("Row #{0}: {1} is a group warehouse. Set the reorder level on a warehouse that holds stock.").format(
					row.idx, frappe.bold(row.warehouse)
				)
			)
		if flt(row.warehouse_reorder_level) < 0 or flt(row.warehouse_reorder_qty) < 0:
			frappe.throw(_("Row #{0}: reorder level and quantity cannot be negative.").format(row.idx))


def reorder_level(item_code, warehouse):
	"""The level set for this item in this warehouse, or None."""
	level = frappe.db.get_value(
		"Item Reorder", {"parent": item_code, "parenttype": "Item", "warehouse": warehouse}, "warehouse_reorder_level"
	)
	return flt(level) if level else None


def stock_qty(item_code, warehouse):
	"""Stock on hand of the item in this one warehouse (never the total of all warehouses)."""
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


def qty_before(sle):
	"""Stock of the SLE's item and warehouse just before this document moved it."""
	previous = frappe.db.sql(
		"""select qty_after_transaction from `tabStock Ledger Entry`
		where item_code = %(item_code)s and warehouse = %(warehouse)s and is_cancelled = 0
			and voucher_no != %(voucher_no)s
			and (posting_datetime < %(posting_datetime)s
				or (posting_datetime = %(posting_datetime)s and creation < %(creation)s))
		order by posting_datetime desc, creation desc limit 1""",
		sle,
	)
	return flt(previous[0][0]) if previous else 0


def alert_on_reorder_level(doc, method=None):
	"""on_submit of a stock document: alert once, when a warehouse's stock crosses its reorder level."""
	entries = frappe.get_all(
		"Stock Ledger Entry",
		filters={"voucher_type": doc.doctype, "voucher_no": doc.name, "is_cancelled": 0},
		fields=["item_code", "warehouse", "voucher_no", "posting_datetime", "creation"],
		order_by="posting_datetime asc, creation asc",
	)
	first_entry = {}
	for sle in entries:
		first_entry.setdefault((sle.item_code, sle.warehouse), sle)

	for (item_code, warehouse), sle in first_entry.items():
		level = reorder_level(item_code, warehouse)
		if level is None:
			continue
		qty = stock_qty(item_code, warehouse)
		# Only when this document takes it to the level: no repeat alert on every sale below it.
		if qty <= level < qty_before(sle):
			send_reorder_alert(item_code, warehouse, qty, level, doc)


def alert_recipients(warehouse):
	"""Enabled stock users whose User Permissions let them see this warehouse."""
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", STOCK_ROLES], "parenttype": "User", "parent": ["!=", "Administrator"]},
		pluck="parent",
		distinct=True,
	)
	enabled = frappe.get_all(
		"User", filters={"name": ["in", users or [""]], "enabled": 1, "user_type": "System User"}, pluck="name"
	)
	return [u for u in enabled if frappe.has_permission("Warehouse", "read", doc=warehouse, user=u)]


def send_reorder_alert(item_code, warehouse, qty, level, doc):
	recipients = alert_recipients(warehouse)
	if not recipients:
		return
	notify(
		"reorder_level_reached",
		recipients,
		{
			"item": frappe.db.get_value("Item", item_code, "item_name") or item_code,
			"item_code": item_code,
			"warehouse": warehouse,
			"qty": frappe.format_value(qty, {"fieldtype": "Float"}),
			"level": frappe.format_value(level, {"fieldtype": "Float"}),
			"uom": frappe.db.get_value("Item", item_code, "stock_uom"),
			"voucher": f"{doc.doctype} {doc.name}",
		},
	)


def get_reorder_alerts(warehouse=None):
	"""Rows (item, warehouse, stock, level, ...) at or below the warehouse's own level.

	Limited to the warehouses the current user may see (frappe.get_list applies User Permissions);
	asking for any other warehouse is refused.
	"""
	allowed = frappe.get_list("Warehouse", filters={"is_group": 0}, pluck="name")
	if warehouse:
		if not frappe.has_permission("Warehouse", "read", doc=warehouse):
			frappe.throw(_("Not permitted to view warehouse {0}").format(warehouse), frappe.PermissionError)
		wanted = [warehouse]
		if frappe.db.get_value("Warehouse", warehouse, "is_group"):
			wanted = frappe.db.get_descendants("Warehouse", warehouse)
		allowed = [w for w in allowed if w in wanted]
	if not allowed:
		return []

	reorder = frappe.qb.DocType("Item Reorder")
	item = frappe.qb.DocType("Item")
	bin = frappe.qb.DocType("Bin")
	rows = (
		frappe.qb.from_(reorder)
		.inner_join(item)
		.on(item.name == reorder.parent)
		.left_join(bin)
		.on((bin.item_code == reorder.parent) & (bin.warehouse == reorder.warehouse))
		.select(
			reorder.parent.as_("item_code"),
			item.item_name,
			item.item_group,
			item.stock_uom,
			reorder.warehouse,
			bin.actual_qty,
			reorder.warehouse_reorder_level.as_("reorder_level"),
			reorder.warehouse_reorder_qty.as_("reorder_qty"),
			reorder.material_request_type,
		)
		.where(
			(reorder.parenttype == "Item")
			& (item.disabled == 0)
			& (reorder.warehouse.isin(allowed))
			& (reorder.warehouse_reorder_level > 0)
		)
		.orderby(reorder.warehouse)
		.orderby(reorder.parent)
		.run(as_dict=True)
	)
	alerts = []
	for row in rows:
		row.actual_qty = flt(row.actual_qty)
		if row.actual_qty <= flt(row.reorder_level):
			row.shortage = flt(row.reorder_level) - row.actual_qty
			alerts.append(row)
	return alerts
