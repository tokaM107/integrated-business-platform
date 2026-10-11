# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Stock count variances (LIB-03, PRN-06): every item counted on submitted Stock Counts, with what was recorded,
# what was counted and the difference in quantity and value, by branch and by who counted. Items that matched
# are listed too unless Only Differences is ticked, so every count shows, not only the ones that found
# something.

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	return [
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Stock Count"), "fieldname": "stock_count", "fieldtype": "Link", "options": "Stock Count", "width": 140},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Cost Center", "width": 160},
		{"label": _("Store"), "fieldname": "store", "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 110},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{"label": _("Recorded Qty"), "fieldname": "recorded_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Counted Qty"), "fieldname": "counted_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Difference"), "fieldname": "difference_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Difference Value"), "fieldname": "difference_value", "fieldtype": "Currency", "width": 120},
		{"label": _("Count Type"), "fieldname": "count_type", "fieldtype": "Data", "width": 130},
		{"label": _("Counted By"), "fieldname": "counted_by", "fieldtype": "Link", "options": "User", "width": 170},
	]


def get_data(filters):
	# Submitted counts only: a draft was not finished and a cancelled one was taken back.
	conditions = {"docstatus": 1}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		conditions["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		conditions["posting_date"] = ["<=", filters.to_date]
	if filters.get("branch"):
		conditions["branch"] = ["in", [filters.branch, *frappe.db.get_descendants("Cost Center", filters.branch)]]
	for fieldname in ("store", "count_type", "counted_by"):
		if filters.get(fieldname):
			conditions[fieldname] = filters[fieldname]

	# get_list (not get_all) applies User Permissions, so a branch manager sees only their own branch.
	counts = frappe.get_list(
		"Stock Count",
		filters=conditions,
		fields=["name", "posting_date", "branch", "store", "count_type", "counted_by"],
		order_by="posting_date desc, name desc",
	)
	if not counts:
		return []
	items = frappe.get_all(
		"Stock Count Item",
		filters={"parenttype": "Stock Count", "parent": ["in", [count.name for count in counts]]},
		fields=["parent", "idx", "item_code", "item_name", "recorded_qty", "counted_qty", "difference_qty", "difference_value"],
		order_by="idx",
	)
	items_of = {}
	for item in items:
		items_of.setdefault(item.parent, []).append(item)

	data = []
	for count in counts:
		for item in items_of.get(count.name, []):
			if filters.get("only_differences") and not flt(item.difference_qty):
				continue
			data.append(
				frappe._dict(
					{
						"posting_date": count.posting_date,
						"stock_count": count.name,
						"branch": count.branch,
						"store": count.store,
						"item_code": item.item_code,
						"item_name": item.item_name,
						"recorded_qty": item.recorded_qty,
						"counted_qty": item.counted_qty,
						"difference_qty": item.difference_qty,
						"difference_value": item.difference_value,
						"count_type": _(count.count_type),
						"counted_by": count.counted_by,
					}
				)
			)
	return data


def get_summary(data):
	shortage = sum(flt(row.difference_value) for row in data if flt(row.difference_value) < 0)
	surplus = sum(flt(row.difference_value) for row in data if flt(row.difference_value) > 0)
	return [
		{"label": _("Counts"), "value": len({row.stock_count for row in data}), "datatype": "Int"},
		{"label": _("Items with a Difference"), "value": len([row for row in data if flt(row.difference_qty)]), "datatype": "Int"},
		{"label": _("Shortage Value"), "value": shortage, "datatype": "Currency", "indicator": "Red"},
		{"label": _("Surplus Value"), "value": surplus, "datatype": "Currency", "indicator": "Green"},
		{"label": _("Net Difference"), "value": shortage + surplus, "datatype": "Currency"},
	]
