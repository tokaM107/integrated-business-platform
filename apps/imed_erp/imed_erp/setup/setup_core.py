# Core setup for Mohamed Mamdouh group: company, cost centers, warehouses, accounts, UOMs, items.
# The accounts themselves live in setup_coa.py, which this script runs after the warehouses.
#
# Run from bench console:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_core.py").read(), {"frappe": frappe})
#
# Idempotent: every step is guarded by frappe.db.exists, so anything that already exists is skipped.
# Safe to run again.

import frappe

# Hardcoded on purpose: a demo company "Mohamed Mamdouh group (Demo)" (abbr MMGD) can exist on
# the site, and a loose get_value("Company", ...) lookup can pick it up by mistake.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
CURRENCY = "EGP"

# Tree roots, built by name. Filtering on parent = "" returns nothing because the root's parent is NULL.
ROOT_CC = f"{COMPANY} - {ABBR}"
ROOT_WH = f"كل المخازن - {ABBR}"


def acc(name):
	return f"{name} - {ABBR}"


def make_cost_center(name, parent, is_group=0):
	full = acc(name)
	if frappe.db.exists("Cost Center", full):
		if frappe.db.get_value("Cost Center", full, "is_group") != is_group:
			print(f"WARN   Cost Center {full}: exists but is_group should be {is_group} (not changed)")
		else:
			print(f"exists Cost Center {full}")
		return full
	if not frappe.db.exists("Cost Center", parent):
		print(f"SKIP   Cost Center {full}: parent {parent} not found")
		return None
	doc = frappe.get_doc(
		{
			"doctype": "Cost Center",
			"cost_center_name": name,
			"parent_cost_center": parent,
			"is_group": is_group,
			"company": COMPANY,
		}
	).insert()
	print(f"create Cost Center {doc.name}")
	return doc.name


def make_warehouse(name, parent, is_group=0):
	full = acc(name)
	if frappe.db.exists("Warehouse", full):
		print(f"exists Warehouse {full}")
		return full
	if not frappe.db.exists("Warehouse", parent):
		print(f"SKIP   Warehouse {full}: parent {parent} not found")
		return None
	doc = frappe.get_doc(
		{
			"doctype": "Warehouse",
			"warehouse_name": name,
			"parent_warehouse": parent,
			"is_group": is_group,
			"company": COMPANY,
		}
	).insert()
	print(f"create Warehouse {doc.name}")
	return doc.name


def make_item(code, item_name, item_group, is_stock_item, income, rate=0, conversions=None):
	income_account = acc(income)
	if not frappe.db.exists("Account", income_account):
		print(f"SKIP   Item {code}: income account {income_account} not found")
		return None

	if frappe.db.exists("Item", code):
		# Only fill a missing income default for this company; everything else is left as is.
		item = frappe.get_doc("Item", code)
		row = next((d for d in item.item_defaults if d.company == COMPANY), None)
		if row and row.income_account:
			print(f"exists Item {code}")
		else:
			if row:
				row.income_account = income_account
			else:
				item.append("item_defaults", {"company": COMPANY, "income_account": income_account})
			item.save()
			print(f"fixed  Item {code}: default income account set to {income_account}")
		return code

	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": item_name,
			"item_group": item_group,
			"stock_uom": "Nos",
			"is_stock_item": is_stock_item,
			"include_item_in_manufacturing": 0,
			"standard_rate": rate,
			"uoms": [{"uom": "Nos", "conversion_factor": 1}] + (conversions or []),
			"item_defaults": [{"company": COMPANY, "income_account": income_account}],
		}
	).insert()
	print(f"create Item {doc.name}")
	return doc.name


def ensure_company():
	"""Create the company if missing; stop if an existing one has another abbreviation."""
	if not frappe.db.exists("Company", COMPANY):
		# ERPNext also creates the standard chart of accounts, root cost center and default warehouses.
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": COMPANY,
				"abbr": ABBR,
				"default_currency": CURRENCY,
				"country": "Egypt",
				"chart_of_accounts": "Standard",
			}
		).insert()
		print(f"create Company {COMPANY} ({ABBR}, {CURRENCY})")
		return True

	company = frappe.db.get_value("Company", COMPANY, ["abbr", "default_currency"], as_dict=True)
	if company.abbr != ABBR:
		print(f"STOP   Company '{COMPANY}' has abbr '{company.abbr}', expected '{ABBR}'. Nothing was changed.")
		return False
	if company.default_currency != CURRENCY:
		# ERPNext locks the currency once transactions exist, so only report it.
		print(f"WARN   Company currency is {company.default_currency}, expected {CURRENCY} (not changed)")
	else:
		print(f"exists Company {COMPANY} ({ABBR}, {CURRENCY})")
	return True


def run():
	# ---------- 0) Company ----------
	if not ensure_company():
		return

	# ERPNext creates the company's accounts and warehouses in English; rename them before anything
	# below looks them up by their Arabic names.
	exec(open(frappe.get_app_path("imed_erp", "setup", "setup_arabic_names.py")).read(), {"frappe": frappe})

	# ---------- 1) Cost centers ----------
	# Imed Center and X Studio share premises, so they sit under one group.
	# Shared rent/electricity is booked to "مصروفات المقر المشتركة" (a leaf, so it can
	# be used in transactions) and then allocated to Imed Halls / X Studio.
	center = make_cost_center("سنتر Imed", ROOT_CC, is_group=1)
	if center:
		make_cost_center("قاعات Imed", center)
		make_cost_center("استوديو X", center)
		make_cost_center("مصروفات المقر المشتركة", center)

	libraries = make_cost_center("مكتبات 2Be Doctor", ROOT_CC, is_group=1)
	if libraries:
		make_cost_center("مكتبة الأزاريطة", libraries)
		make_cost_center("مكتبة المواساة", libraries)

	make_cost_center("تطبيق BA Plus", ROOT_CC)

	# ---------- 2) Warehouses ----------
	# The group's only central store is at Mawasah; branch stores sit under it.
	# Each library keeps raw materials (paper, ink, binding supplies) apart from doctors' editions,
	# the only goods sold; setup_coa.py gives each warehouse its own stock account.
	central = make_warehouse("المخزن المركزي بالمواساة", ROOT_WH, is_group=1)
	if central:
		make_warehouse("خامات المواساة", central)
		make_warehouse("إصدارات الأطباء — المواساة", central)
		make_warehouse("خامات الأزاريطة", central)
		make_warehouse("إصدارات الأطباء — الأزاريطة", central)

	# ---------- 3) Accounts ----------
	# Needs the company and the warehouses above; the items below need its income accounts.
	exec(open(frappe.get_app_path("imed_erp", "setup", "setup_coa.py")).read(), {"frappe": frappe})

	# ---------- 4) UOMs ----------
	for uom in ["رزمة", "كرتونة"]:
		if frappe.db.exists("UOM", uom):
			print(f"exists UOM {uom}")
		else:
			frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert()
			print(f"create UOM {uom}")

	# ---------- 5) Items ----------
	for group in ["منتجات المكتبات", "الخدمات"]:
		if frappe.db.exists("Item Group", group):
			print(f"exists Item Group {group}")
		else:
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": group, "parent_item_group": "All Item Groups"}
			).insert()
			print(f"create Item Group {group}")

	# Library revenue is split by library, but an item has one default income account per company.
	# Library items default to Mawasah; imederp/library_revenue.py moves each invoice row to the revenue
	# account of the library it is sold in.
	# A4 paper is stocked in sheets (Nos): 1 Ream = 500 sheets, 1 Box = 5 Reams = 2500 sheets.
	make_item(
		"A4-PAPER",
		"ورق A4 80 جرام",
		"منتجات المكتبات",
		1,
		"إيراد مكتبة المواساة",
		conversions=[{"uom": "رزمة", "conversion_factor": 500}, {"uom": "كرتونة", "conversion_factor": 2500}],
	)
	make_item("PRINT-SVC", "تصوير وطباعة", "منتجات المكتبات", 0, "إيراد مكتبة المواساة", rate=1)
	make_item("BINDING-SVC", "تجليد", "منتجات المكتبات", 0, "إيراد مكتبة المواساة")
	make_item("STUDIO-HOUR", "ساعة استوديو", "الخدمات", 0, "إيراد X Studio")
	make_item("HALL-HOUR", "ساعة قاعة", "الخدمات", 0, "إيراد القاعات")

	frappe.db.commit()
	print(f"DONE   Core setup finished for {COMPANY} ({ABBR}).")


run()
