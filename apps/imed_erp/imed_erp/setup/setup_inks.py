# The libraries' inks and binding supplies as stock items, like the paper (owner, 4 Nov 2026: the ink prices were only a cost per sheet
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
BINDING_GROUP = "خامات تجليد"
# An Epson set is four colours, and one runs out before another (owner, 9 Nov 2026): each colour is its own item,
# a quarter of the set's price, so the owner sees which finishes first. The set itself (INK-EPSON) is disabled
# while nothing was ever counted of it.
EPSON_COLOURS = [("INK-EPSON-BK", "حبر إبسون أسود"), ("INK-EPSON-C", "حبر إبسون سماوي"), ("INK-EPSON-M", "حبر إبسون ماجنتا"), ("INK-EPSON-Y", "حبر إبسون أصفر")]
INKS = [
	# code, name, group, the settings' field that holds its price, the part of that price one piece costs
	("INK-RISO", "حبر ريزو (إزازة)", INK_GROUP, "riso_ink_price", 1),
	*[(code, name, INK_GROUP, "epson_ink_set_price", 4) for code, name in EPSON_COLOURS],
	("BIND-WIRE", "سلك تغليف", BINDING_GROUP, "binding_wire_price", 1),
	("BIND-COVER", "كافر بلاستك", BINDING_GROUP, "binding_cover_price", 1),
]


def ensure_group(group):
	if frappe.db.exists("Item Group", group):
		print(f"exists Item Group {group}")
		return
	parent = frappe.db.get_value("Item Group", PAPER_GROUP, "parent_item_group") or "All Item Groups"
	frappe.get_doc({"doctype": "Item Group", "item_group_name": group, "parent_item_group": parent, "is_group": 0}).insert()
	print(f"create Item Group {group} under {parent}")


def ensure_item(code, name, group, price_field, parts=1):
	price = flt(frappe.db.get_single_value("Printing Cost Settings", price_field)) if frappe.db.exists("DocType", "Printing Cost Settings") else 0
	price = flt(price / parts, 2)
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": group,
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


def retire_epson_set():
	if frappe.db.exists("Item", "INK-EPSON") and not frappe.db.get_value("Item", "INK-EPSON", "disabled"):
		if frappe.db.exists("Stock Ledger Entry", {"item_code": "INK-EPSON", "is_cancelled": 0}):
			print("KEEP   INK-EPSON: the set has stock movements; count its colours, then disable it by hand")
			return
		frappe.db.set_value("Item", "INK-EPSON", "disabled", 1)
		print("disable Item INK-EPSON: the set is counted by its four colours")


def run():
	for group in (INK_GROUP, BINDING_GROUP):
		ensure_group(group)
	for code, name, group, field, parts in INKS:
		ensure_item(code, name, group, field, parts)
	retire_epson_set()
	frappe.db.commit()
	print("DONE   Inks set up.")


run()
