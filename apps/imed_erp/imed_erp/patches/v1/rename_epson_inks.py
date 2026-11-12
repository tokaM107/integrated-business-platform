# The Epson inks by their everyday names (the user, 11 Nov 2026): "blue" and "red", not "cyan" and "magenta",
# which the libraries' staff do not use. Same items, same stock: only the name shown changes (setup/setup_inks.py
# gives a new site these names from the start). Run once by bench migrate.
import frappe

NAMES = {"INK-EPSON-C": "حبر إبسون أزرق", "INK-EPSON-M": "حبر إبسون أحمر"}


def execute():
	for code, name in NAMES.items():
		if frappe.db.exists("Item", code) and frappe.db.get_value("Item", code, "item_name") != name:
			frappe.db.set_value("Item", code, {"item_name": name, "description": f"{name}: counted by the library."}, update_modified=False)
