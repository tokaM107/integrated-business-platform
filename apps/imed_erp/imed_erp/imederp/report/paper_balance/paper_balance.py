# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The paper in each store (PRN-04): kept and used in sheets, shown in boxes and reams too. 11,030 sheets are
# 4 boxes, 2 reams and 30 sheets. The sizes are the item's own units (setup_core.py: ream 500, box 2,500), read from
# the item, so a change there is followed here. A branch manager sees her own stores (User Permissions).

import frappe
from frappe import _
from frappe.utils import cint, flt

from imed_erp.imederp.doctype.book_edition.book_edition import PAPER

REAM, BOX = "رزمة", "كرتونة"


def execute(filters=None):
	return get_columns(), get_data()


def get_columns():
	return [
		{"label": _("Store"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 220},
		{"label": _("Sheets"), "fieldname": "sheets", "fieldtype": "Int", "width": 110},
		{"label": _("Boxes"), "fieldname": "boxes", "fieldtype": "Int", "width": 90},
		{"label": _("Reams"), "fieldname": "reams", "fieldtype": "Int", "width": 90},
		{"label": _("Loose Sheets"), "fieldname": "loose", "fieldtype": "Int", "width": 110},
		{"label": _("Value"), "fieldname": "value", "fieldtype": "Currency", "width": 120},
	]


def unit_sizes():
	sizes = dict(frappe.get_all("UOM Conversion Detail", filters={"parent": PAPER}, fields=["uom", "conversion_factor"], as_list=True))
	return cint(sizes.get(BOX)), cint(sizes.get(REAM))


def in_boxes_and_reams(sheets, box, ream):
	"""(boxes, reams, sheets) for a number of sheets: as many whole boxes as fit, then reams, then the rest."""
	sheets = cint(sheets)
	boxes = sheets // box if box and sheets > 0 else 0
	left = sheets - boxes * box
	reams = left // ream if ream and left > 0 else 0
	return boxes, reams, left - reams * ream


def get_data():
	box, ream = unit_sizes()
	allowed = set(frappe.get_list("Warehouse", filters={"is_group": 0, "company": frappe.defaults.get_global_default("company")}, pluck="name"))
	rows = []
	for b in frappe.get_all("Bin", filters={"item_code": PAPER}, fields=["warehouse", "actual_qty", "stock_value"], order_by="warehouse"):
		if b.warehouse not in allowed or (not b.actual_qty and not b.stock_value):
			continue
		boxes, reams, loose = in_boxes_and_reams(b.actual_qty, box, ream)
		rows.append(
			{"warehouse": b.warehouse, "sheets": cint(b.actual_qty), "boxes": boxes, "reams": reams, "loose": loose, "value": flt(b.stock_value, 2)}
		)
	return rows
