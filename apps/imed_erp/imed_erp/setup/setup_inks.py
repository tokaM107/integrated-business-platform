# The libraries' inks as stock items, like the paper (owner, 4 Nov 2026: the ink prices were only a cost per sheet
# in Printing Cost Settings, so nothing knew how much ink a library holds, where, or when it runs out).
#
#   أحبار (item group, beside the paper's)
#     INK-RISO    a Riso ink bottle, valued at Printing Cost Settings' Riso ink price
#     INK-EPSON   an Epson ink set, valued at the Epson ink set price
#
# The libraries enter what they hold from their own screen (مكتبتي: رصيد المخزون), and every bottle or set they
# finish is taken off (حاجة خلصت). More colours or kinds are added as items of the same group: the screen lists
# every item of the group by itself. A reorder level on an item turns on the stock alert ERPNext already sends.
#
# Run from bench console (after setup_core.py):
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_inks.py").read(), {"frappe": frappe})
# Idempotent: running it again changes nothing, except the valuation of an item with no stock yet, which follows
# the settings' price.

import frappe
from frappe.utils import flt

INK_GROUP = "أحبار"
PAPER_GROUP = "ورق"
INKS = [
	# code, name, the settings' field that holds its price
	("INK-RISO", "حبر ريزو (إزازة)", "riso_ink_price"),
	("INK-EPSON", "طقم حبر إبسون", "epson_ink_set_price"),
]


def ensure_group():
	if frappe.db.exists("Item Group", INK_GROUP):
		print(f"exists Item Group {INK_GROUP}")
		return
	parent = frappe.db.get_value("Item Group", PAPER_GROUP, "parent_item_group") or "All Item Groups"
	frappe.get_doc({"doctype": "Item Group", "item_group_name": INK_GROUP, "parent_item_group": parent, "is_group": 0}).insert()
	print(f"create Item Group {INK_GROUP} under {parent}")


def ensure_item(code, name, price_field):
	price = flt(frappe.db.get_single_value("Printing Cost Settings", price_field)) if frappe.db.exists("DocType", "Printing Cost Settings") else 0
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": INK_GROUP,
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"include_item_in_manufacturing": 0,
				"valuation_rate": price,
				"description": f"{name}: counted by the library, taken off when finished.",
			}
		).insert()
		print(f"create Item {code} {name}, valued {price}")
		if not price:
			print(f"WARN   Printing Cost Settings has no {price_field}: enter it and run this again, or the first count of {code} is refused")
		return
	has_stock = frappe.db.exists("Stock Ledger Entry", {"item_code": code, "is_cancelled": 0})
	if not has_stock and price and flt(frappe.db.get_value("Item", code, "valuation_rate")) != price:
		frappe.db.set_value("Item", code, "valuation_rate", price)
		print(f"update Item {code}: valued {price} (the settings' price)")
	else:
		print(f"exists Item {code}")


def run():
	ensure_group()
	for code, name, field in INKS:
		ensure_item(code, name, field)
	frappe.db.commit()
	print("DONE   Inks set up.")


run()
