# Library / POS / inventory setup (LIB) for Mohamed Mamdouh group: item groups, the product fields of
# LIB-06, the library services, item defaults and one POS Profile per library branch.
#
# Run from bench console (after setup_core.py and setup_users.py):
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_library.py").read(), {"frappe": frappe})
#
# Idempotent: anything that already exists is kept. It creates no account, cost center or warehouse:
# those come from setup_core.py / setup_coa.py, and a missing one is reported as WAIT and left empty,
# never invented. Names are the Arabic ones of setup_arabic_names.py.
#
# Where each default comes from when an item is sold:
#   Revenue account  <- the item (Item Defaults: Mawasah's library revenue); imederp/library_revenue.py
#                       then moves the row to the revenue account of the library it is sold in.
#   Warehouse        <- the branch's POS Profile; without one, the item's default (Mawasah's doctors' editions)
#   Cost center      <- the branch's POS Profile; without one, the item's default (Mawasah). An item has
#                       only one default per company and the same book is sold by both branches, so
#                       Azarita's sales must go through its POS Profile.

import frappe

# Hardcoded on purpose, like the other setup scripts.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"

# Created by setup_core.py as a plain group; made a parent here.
PARENT_GROUP = "منتجات المكتبات"
BOOKS_GROUP = "كتب"
MEMOS_GROUP = "مذكرات"
SERVICES_GROUP = "خدمات المكتبات"
ITEM_GROUPS = [BOOKS_GROUP, MEMOS_GROUP, SERVICES_GROUP]

# The five inventory groups: (group, parent, is_group). Books & Notebooks holds the books and memos
# groups above. Consumables is ERPNext's own "Consumable" group (renamed by setup_arabic_names.py),
# reused rather than duplicated. A group is the item's classification (LIB-06).
BOOKS_NOTEBOOKS_GROUP = "كتب وكشاكيل"
PAPER_GROUP = "ورق"
INVENTORY_GROUPS = [
	(PAPER_GROUP, "All Item Groups", 0),
	("أحبار", "All Item Groups", 0),
	(BOOKS_NOTEBOOKS_GROUP, PARENT_GROUP, 1),
	("مستهلكات", "All Item Groups", 0),
	("خامات تجليد", "All Item Groups", 0),
]
# (group, parent) for the library groups; books and memos sit under Books & Notebooks.
LIBRARY_GROUP_PARENTS = {
	BOOKS_GROUP: BOOKS_NOTEBOOKS_GROUP,
	MEMOS_GROUP: BOOKS_NOTEBOOKS_GROUP,
	SERVICES_GROUP: PARENT_GROUP,
}

# Books and memos are doctors' editions, the only goods the libraries sell (setup_core.py). Mawasah's
# store sits under the central store (LIB-02) and issues to Azarita (LIB-08).
CENTRAL_WAREHOUSE = "إصدارات الأطباء — المواساة"
# The branch of the central store; the item's fallback cost center (see the top of the file).
CENTRAL_COST_CENTER = "مكتبة المواساة"

# Accounting integration point. The accounts belong to the chart of accounts (setup_coa.py); this
# script only selects them. Every library item defaults to Mawasah's revenue, like setup_core.py does.
REVENUE_ACCOUNT = "إيراد مكتبة المواساة"
# Stock items only, as setup_core.py does for paper.
EXPENSE_ACCOUNT = "تكلفة البضاعة المباعة"

# (code, name). Non-stock: a service is sold, never stored. PRINT-SVC and BINDING-SVC already exist
# (setup_core.py) and are only moved into the library services group.
# COPY-SVC is separate from PRINT-SVC ("تصوير وطباعة") as the requirements list copying on its own.
SERVICES = [
	("COPY-SVC", "تصوير مستندات"),
	("PRINT-SVC", "تصوير وطباعة"),
	("BINDING-SVC", "تجليد"),
]

# Books and memos (stock items). The real catalogue is not in the requirements and comes from the
# existing library system (LIB-11), so only one generic item per group exists for now, without ISBN,
# author or prices. Add one dict per real title:
#   {"code": "BOOK-0001", "name": "...", "group": BOOKS_GROUP, "author": "...", "isbn": "9780000000000",
#    "cost": 100, "price": 150}
# "isbn" is optional (memos have none). Quantity is not set here: stock enters the central store
# through purchases (LIB-07) and reaches Azarita by transfer (LIB-08).
LIBRARY_ITEMS = [
	{"code": "BOOK", "name": "كتاب", "group": BOOKS_GROUP},
	{"code": "MEMO", "name": "مذكرة", "group": MEMOS_GROUP},
]

# (profile name, cost center, warehouse, cashier) - cashiers as in setup_users.py.
POS_PROFILES = [
	("نقطة بيع مكتبة المواساة", "مكتبة المواساة", "إصدارات الأطباء — المواساة", "raghad@imed.local"),
	("نقطة بيع مكتبة الأزاريطة", "مكتبة الأزاريطة", "إصدارات الأطباء — الأزاريطة", "sara@imed.local"),
]
# Payment methods (CORE-03, ACC-01): cash goes to the library's own cash box, not to the company's main
# treasury that ERPNext's "Cash" posts to. InstaPay and Vodafone Cash are one number for the whole group.
# (name, type, account) - accounts from setup_coa.py, as in imederp/treasuries.py.
CASH_MODES = {
	"مكتبة المواساة": ("نقدي — مكتبة المواساة", "Cash", "خزينة مكتبة المواساة"),
	"مكتبة الأزاريطة": ("نقدي — مكتبة الأزاريطة", "Cash", "خزينة مكتبة الأزاريطة"),
}
WALLET_MODES = [("InstaPay", "Bank", "محفظة InstaPay"), ("Vodafone Cash", "Bank", "محفظة Vodafone Cash")]

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

	for group, parent, is_group in INVENTORY_GROUPS:
		ensure_item_group(group, parent, is_group)
	for group, parent in LIBRARY_GROUP_PARENTS.items():
		ensure_item_group(group, parent)

	# A4 paper was first made directly in the library products group; it belongs in Paper.
	if frappe.db.get_value("Item", "A4-PAPER", "item_group") == PARENT_GROUP:
		frappe.db.set_value("Item", "A4-PAPER", "item_group", PAPER_GROUP)
		print(f"update Item A4-PAPER: group {PAPER_GROUP}")


def ensure_item_group(group, parent, is_group=0):
	"""Create the group under `parent`, or move it there. An existing group's is_group is kept."""
	if not frappe.db.exists("Item Group", group):
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": group, "parent_item_group": parent, "is_group": is_group}
		).insert()
		print(f"create Item Group {group}")
		return
	doc = frappe.get_doc("Item Group", group)
	if doc.parent_item_group == parent:
		print(f"exists Item Group {group}")
		return
	doc.parent_item_group = parent
	doc.save()
	print(f"move   Item Group {group} -> {parent}")


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


def item_default(is_stock_item):
	"""Item Defaults row for this company. A missing account or cost center is left empty and reported."""
	row = {"company": COMPANY, "default_warehouse": acc(CENTRAL_WAREHOUSE)}
	if frappe.db.exists("Account", acc(REVENUE_ACCOUNT)):
		row["income_account"] = acc(REVENUE_ACCOUNT)
	if is_stock_item and frappe.db.exists("Account", acc(EXPENSE_ACCOUNT)):
		row["expense_account"] = acc(EXPENSE_ACCOUNT)
	if frappe.db.exists("Cost Center", acc(CENTRAL_COST_CENTER)):
		row["selling_cost_center"] = acc(CENTRAL_COST_CENTER)
	return row


def sync_item_default(item):
	"""Fill what is missing in the item's defaults; values already set are never overwritten."""
	wanted = item_default(item.is_stock_item)
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
		changed = sync_item_default(item)
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
				"item_defaults": [item_default(is_stock_item)],
				**(extra or {}),
			}
		).insert()
		print(f"create Item {code}")

	row = next(d for d in item.item_defaults if d.company == COMPANY)
	if not row.income_account:
		wait(f"Item {code} revenue account", f"Account {acc(REVENUE_ACCOUNT)} does not exist yet")
	if not row.selling_cost_center:
		wait(f"Item {code} cost center", f"Cost Center {acc(CENTRAL_COST_CENTER)} does not exist yet")


def make_library_item(spec):
	extra = {"custom_author": spec.get("author"), "valuation_rate": spec.get("cost", 0), "standard_rate": spec.get("price", 0)}
	if spec.get("isbn"):
		extra["barcodes"] = [{"barcode": spec["isbn"], "barcode_type": "ISBN"}]
	ensure_item(spec["code"], spec["name"], spec["group"], 1, extra)


def make_mode_of_payment(name, mode_type, account):
	"""A payment method posting to `account` for this company. Returns False if the account is missing."""
	if not frappe.db.exists("Account", acc(account)):
		wait(f"Mode of Payment {name}", f"account {acc(account)} not found (setup_coa.py makes it)")
		return False
	if not frappe.db.exists("Mode of Payment", name):
		frappe.get_doc(
			{
				"doctype": "Mode of Payment",
				"mode_of_payment": name,
				"type": mode_type,
				"enabled": 1,
				"accounts": [{"company": COMPANY, "default_account": acc(account)}],
			}
		).insert()
		print(f"create Mode of Payment {name} -> {acc(account)}")
		return True
	mode = frappe.get_doc("Mode of Payment", name)
	row = next((r for r in mode.accounts if r.company == COMPANY), None)
	if row and row.default_account == acc(account):
		print(f"exists Mode of Payment {name}")
		return True
	if not row:
		row = mode.append("accounts", {"company": COMPANY})
	row.default_account = acc(account)
	mode.save()
	print(f"update Mode of Payment {name} -> {acc(account)}")
	return True


def make_pos_profile(name, cost_center, warehouse, user):
	modes = [CASH_MODES[cost_center], *WALLET_MODES]
	if not all([make_mode_of_payment(*mode) for mode in modes]):
		wait(f"POS Profile {name}", "not created or updated, a payment method is missing its account")
		return
	# The library's cash first, as the default; then the wallets.
	payments = [{"mode_of_payment": mode[0], "default": int(i == 0)} for i, mode in enumerate(modes)]

	if frappe.db.exists("POS Profile", name):
		profile = frappe.get_doc("POS Profile", name)
		current = [(p.mode_of_payment, p.default) for p in profile.payments]
		if current == [(p["mode_of_payment"], p["default"]) for p in payments]:
			print(f"exists POS Profile {name}")
		else:
			profile.set("payments", payments)
			profile.save()
			print(f"update POS Profile {name}: payments {', '.join(p['mode_of_payment'] for p in payments)}")
		return

	missing = [
		f"{doctype} {value}"
		for doctype, value in [("Cost Center", acc(cost_center)), ("Warehouse", acc(warehouse)), ("User", user)]
		if not frappe.db.exists(doctype, value)
	]
	write_off = frappe.db.get_value("Company", COMPANY, "write_off_account")
	if not write_off:
		missing.append("Company write-off account")
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
			"payments": payments,
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
			ensure_item(code, item_name, SERVICES_GROUP, 0)

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
