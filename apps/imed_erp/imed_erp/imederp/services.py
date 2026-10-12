# Services sold (printing, copying, binding, hall and studio hours) are not stock, so they have no warehouse.
# ERPNext puts one on every invoice row all the same, from the item's defaults or the site's default
# warehouse, and a branch manager's User Permissions then refuse the invoice for a store that is not theirs
# (Raghad and Sara could not submit a desk Sales Invoice for printing). hooks.py runs this on Sales Invoice and
# POS Invoice validate, after ERPNext has filled the rows.

import frappe


def clear_service_warehouses(doc, method=None):
	for row in doc.items:
		if row.get("warehouse") and row.item_code and not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			row.warehouse = None
