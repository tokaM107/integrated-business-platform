# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Items at or below the reorder level of each warehouse (LIB-04). The stock compared is that one
# warehouse's, never the total of all warehouses. Each user sees only the warehouses their User
# Permissions allow (imederp/stock_reorder.py).

from frappe import _

from imed_erp.imederp.stock_reorder import get_reorder_alerts


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_reorder_alerts(filters.get("warehouse"))


def get_columns():
	return [
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 220},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 130},
		{"label": _("In Stock"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Reorder Level"), "fieldname": "reorder_level", "fieldtype": "Float", "width": 110},
		{"label": _("Shortage"), "fieldname": "shortage", "fieldtype": "Float", "width": 100},
		{"label": _("Reorder Qty"), "fieldname": "reorder_qty", "fieldtype": "Float", "width": 100},
		{"label": _("UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Request Type"), "fieldname": "material_request_type", "fieldtype": "Data", "width": 110},
	]
