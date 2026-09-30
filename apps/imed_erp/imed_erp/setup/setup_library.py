# Library / POS / inventory setup (LIB) for Mohamed Mamdouh group: item groups, the product fields of
# LIB-06, the library services, item defaults and one POS Profile per library branch.
#
# Run from bench console (after setup_core.py and setup_users.py):
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_library.py").read(), {"frappe": frappe})
#
# Idempotent: anything that already exists is kept. It creates no account, cost center or warehouse:
# those come from setup_core.py, and a missing one is reported as WAIT and left empty, never invented.
#
# Where each default comes from when an item is sold:
#   Revenue account  <- the item (Item Defaults)
#   Warehouse        <- the branch's POS Profile; without one, the item's default (the central store)
#   Cost center      <- the branch's POS Profile; without one, the item's default (Mawasah, where the
#                       central store is). An item has only one default per company and the same book
#                       is sold by both branches, so Azarita's sales must go through its POS Profile.

import frappe

# Hardcoded on purpose, like the other setup scripts.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"

PARENT_GROUP = "Library Products"
ITEM_GROUPS = ["Books", "Memos", "Library Services"]

# The central store (LIB-02) and the branch store it issues to (LIB-08), both created by setup_core.py.
CENTRAL_WAREHOUSE = "Store Mawasah"
# The branch of the central store; the item's fallback cost center (see the top of the file).
CENTRAL_COST_CENTER = "2Be Doctor Mawasah"

# Accounting integration point. These accounts belong to the chart of accounts (Toka); this script
# only selects them. To change the mapping, change the account name here and run the script again
# after clearing the item's income account.
REVENUE_ACCOUNT = {
	"Books": "Books Revenue",
	"Memos": "Books Revenue",
	"Library Services": "Printing Revenue",
}

# (code, name). Non-stock: a service is sold, never stored. PRINT-SVC and BINDING-SVC already exist
# (setup_core.py) and are only moved into the Library Services group.
SERVICES = [
	("COPY-SVC", "Copying Service"),
	("PRINT-SVC", "Printing Service"),
	("BINDING-SVC", "Binding Service"),
]

# Books and memos (stock items). The real catalogue is not in the requirements and comes from the
# existing library system (LIB-11), so only one generic item per group exists for now, without ISBN,
# author or prices. Add one dict per real title:
#   {"code": "BOOK-0001", "name": "...", "group": "Books", "author": "...", "isbn": "9780000000000",
#    "cost": 100, "price": 150}
# "isbn" is optional (memos have none). Quantity is not set here: stock enters the central store
# through purchases (LIB-07) and reaches Azarita by transfer (LIB-08).
LIBRARY_ITEMS = [
	{"code": "BOOK", "name": "Book", "group": "Books"},
	{"code": "MEMO", "name": "Memo", "group": "Memos"},
]

# (profile name, cost center, warehouse, cashier)
POS_PROFILES = [
	("2Be Doctor Mawasah POS", "2Be Doctor Mawasah", "Store Mawasah", "raghad@imed.local"),
	("2Be Doctor Azarita POS", "2Be Doctor Azarita", "Store Azarita", "sara@imed.local"),
]
PAYMENT_MODE = "Cash"

waiting = []


def acc(name):
	return f"{name} - {ABBR}"


def wait(what, needs):
	waiting.append(f"{what}: {needs}")
	print(f"WAIT   {what}: {needs}")


def make_item_groups():
	if not frappe.db.exists("Item Group", PARENT_GROUP):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": PARENT_GROUP,
				"parent_item_group": "All Item Groups",
				"is_group": 1,
			}
		).insert()
		print(f"create Item Group {PARENT_GROUP}")
	elif not frappe.db.get_value("Item Group", PARENT_GROUP, "is_group"):
		# Created as a leaf by setup_core.py; it must be a group to hold the three groups below.
		parent = frappe.get_doc("Item Group", PARENT_GROUP)
		parent.is_group = 1
		parent.save()
		print(f"update Item Group {PARENT_GROUP}: is_group = 1")
	else:
		print(f"exists Item Group {PARENT_GROUP}")

	for group in ITEM_GROUPS:
		if frappe.db.exists("Item Group", group):
			print(f"exists Item Group {group}")
			continue
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": group, "parent_item_group": PARENT_GROUP}
		).insert()
		print(f"create Item Group {group}")


def make_author_field():
	"""LIB-06. Only the author needs a field: ISBN is a row in the item's Barcodes table (type ISBN,
	so it can be scanned at the POS), category is the Item Group, cost price is the Valuation Rate,
	selling price is the Standard Selling price and quantity is the stock balance per warehouse."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_field

	if frappe.get_meta("Item").has_field("custom_author"):
		print("exists Custom Field Item.custom_author")
		return
	create_custom_field(
		"Item",
		{
			"fieldname": "custom_author",
			"label": "Author",
			"fieldtype": "Data",
			"insert_after": "item_group",
			"in_standard_filter": 1,
			"translatable": 0,
		},
	)
	print("create Custom Field Item.custom_author")


def item_default(group):
	"""Item Defaults row for this company. A missing account or cost center is left empty and reported."""
	row = {"company": COMPANY, "default_warehouse": acc(CENTRAL_WAREHOUSE)}
	income = acc(REVENUE_ACCOUNT[group])
	if frappe.db.exists("Account", income):
		row["income_account"] = income
	if frappe.db.exists("Cost Center", acc(CENTRAL_COST_CENTER)):
		row["selling_cost_center"] = acc(CENTRAL_COST_CENTER)
	return row


def sync_item_default(item, group):
	"""Fill what is missing in the item's defaults; values already set are never overwritten."""
	wanted = item_default(group)
	row = next((d for d in item.item_defaults if d.company == COMPANY), None)
	if not row:
		item.append("item_defaults", wanted)
		return True
	changed = False
	for field, value in wanted.items():
		if not row.get(field):
			row.set(field, value)
			changed = True
	return changed


def ensure_item(code, item_name, group, is_stock_item, extra=None):
	if frappe.db.exists("Item", code):
		item = frappe.get_doc("Item", code)
		changed = sync_item_default(item, group)
		if item.item_group != group:
			item.item_group = group
			changed = True
		if changed:
			item.save()
			print(f"update Item {code}: group {group}, defaults filled")
		else:
			print(f"exists Item {code}")
	else:
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": item_name,
				"item_group": group,
				"stock_uom": "Nos",
				"is_stock_item": is_stock_item,
				"include_item_in_manufacturing": 0,
				"item_defaults": [item_default(group)],
				**(extra or {}),
			}
		).insert()
		print(f"create Item {code}")

	row = next(d for d in item.item_defaults if d.company == COMPANY)
	if not row.income_account:
		wait(f"Item {code} revenue account", f"Account {acc(REVENUE_ACCOUNT[group])} does not exist yet")
	if not row.selling_cost_center:
		wait(f"Item {code} cost center", f"Cost Center {acc(CENTRAL_COST_CENTER)} does not exist yet")


def make_library_item(spec):
	extra = {"custom_author": spec.get("author"), "valuation_rate": spec.get("cost", 0), "standard_rate": spec.get("price", 0)}
	if spec.get("isbn"):
		extra["barcodes"] = [{"barcode": spec["isbn"], "barcode_type": "ISBN"}]
	ensure_item(spec["code"], spec["name"], spec["group"], 1, extra)


def make_pos_profile(name, cost_center, warehouse, user):
	if frappe.db.exists("POS Profile", name):
		print(f"exists POS Profile {name}")
		return

	missing = [
		f"{doctype} {value}"
		for doctype, value in [("Cost Center", acc(cost_center)), ("Warehouse", acc(warehouse)), ("User", user)]
		if not frappe.db.exists(doctype, value)
	]
	write_off = frappe.db.get_value("Company", COMPANY, "write_off_account")
	if not write_off:
		missing.append("Company write-off account")
	if not frappe.db.get_value("Mode of Payment Account", {"parent": PAYMENT_MODE, "company": COMPANY}):
		missing.append(f"an account on Mode of Payment {PAYMENT_MODE}")
	if missing:
		wait(f"POS Profile {name}", f"not created, missing {', '.join(missing)}")
		return

	# No income account on the profile: it would replace the item's own revenue account.
	frappe.get_doc(
		{
			"doctype": "POS Profile",
			"__newname": name,
			"company": COMPANY,
			"currency": frappe.db.get_value("Company", COMPANY, "default_currency"),
			"warehouse": acc(warehouse),
			"cost_center": acc(cost_center),
			"write_off_account": write_off,
			"write_off_cost_center": acc(cost_center),
			"selling_price_list": frappe.db.get_single_value("Selling Settings", "selling_price_list"),
			"update_stock": 1,
			"payments": [{"mode_of_payment": PAYMENT_MODE, "default": 1}],
			"item_groups": [{"item_group": g} for g in ITEM_GROUPS],
			"applicable_for_users": [{"user": user, "default": 1}],
		}
	).insert()
	print(f"create POS Profile {name}")


def run():
	if frappe.db.get_value("Company", COMPANY, "abbr") != ABBR:
		print(f"STOP   Company '{COMPANY}' with abbr '{ABBR}' not found; run setup_core.py first.")
		return
	if not frappe.db.exists("Warehouse", acc(CENTRAL_WAREHOUSE)):
		print(f"STOP   Warehouse {acc(CENTRAL_WAREHOUSE)} not found; run setup_core.py first.")
		return

	try:
		# ---------- 1) Item groups ----------
		make_item_groups()

		# ---------- 2) Product fields (LIB-06) ----------
		make_author_field()

		# ---------- 3) Services (non-stock) ----------
		for code, item_name in SERVICES:
			ensure_item(code, item_name, "Library Services", 0)

		# ---------- 4) Books and memos (stock) ----------
		for spec in LIBRARY_ITEMS:
			make_library_item(spec)

		# ---------- 5) POS Profiles: warehouse and cost center per branch ----------
		for spec in POS_PROFILES:
			make_pos_profile(*spec)

		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		print("FAILED Rolled back; nothing was changed.")
		raise

	print()
	if waiting:
		print(f"{len(waiting)} item(s) waiting for the accounting setup:")
		for w in waiting:
			print(f"  - {w}")
	print(f"DONE   Library setup finished for {COMPANY} ({ABBR}).")


run()
