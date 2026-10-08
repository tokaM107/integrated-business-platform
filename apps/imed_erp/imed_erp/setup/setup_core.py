# Core setup for Mohamed Mamdouh group: company, cost centers, warehouses, accounts, UOMs, items.
# The accounts themselves live in setup_coa.py, which this script runs after the warehouses.
#
# Run from bench console (first of the setup scripts):
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_core.py").read(), {"frappe": frappe})
#
# On a brand-new site (setup wizard not done yet) it completes the setup wizard itself, which creates
# the company, so no manual step in the browser is needed.
#
# Idempotent: every step is guarded by frappe.db.exists, so anything that already exists is skipped.
# Safe to run again.

import frappe

# Hardcoded on purpose: a demo company "Mohamed Mamdouh group (Demo)" (abbr MMGD) can exist on
# the site, and a loose get_value("Company", ...) lookup can pick it up by mistake.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
CURRENCY = "EGP"

# Paper is stocked in sheets and bought in boxes.
SHEET = "ورقة"
BOX = "كرتونة"
HOUR = "ساعة"

# Paper sits in ورق, one of the inventory groups of setup_library.py (LIB-06). Every item in it is valued at
# moving average and bought by the box (ensure_paper_items), including paper added later.
PAPER_GROUP = "ورق"
MOVING_AVERAGE = "Moving Average"

# First fiscal year, used only when this script runs the setup wizard on a new site.
# Must match the first entry of FISCAL_YEARS in setup_regional.py (academic year, Sep-Aug).
FISCAL_YEAR_START = "2026-09-01"
FISCAL_YEAR_END = "2027-08-31"

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
		current = frappe.db.get_value("Warehouse", full, "parent_warehouse")
		if current != parent and frappe.db.exists("Warehouse", parent):
			# Moving a warehouse keeps its stock, account and links; only the tree changes.
			doc = frappe.get_doc("Warehouse", full)
			doc.parent_warehouse = parent
			doc.save()
			print(f"move   Warehouse {full}: {current} -> {parent}")
		else:
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


def make_item(
	code, item_name, item_group, is_stock_item, income, rate=0, conversions=None, expense=None, stock_uom="Nos"
):
	income_account = acc(income)
	expense_account = acc(expense) if expense else None
	for account in filter(None, (income_account, expense_account)):
		if not frappe.db.exists("Account", account):
			print(f"SKIP   Item {code}: account {account} not found")
			return None
	# The warehouse is set explicitly: otherwise Frappe fills it from the site-wide default warehouse,
	# which belongs to another company when one exists (e.g. "Stores - I"), and the item is rejected.
	# خامات المواساة holds the central stock of raw materials.
	wanted = {
		"income_account": income_account,
		"expense_account": expense_account,
		"default_warehouse": acc("خامات المواساة"),
	}

	if frappe.db.exists("Item", code):
		ensure_stock_uom(code, stock_uom)
		ensure_conversions(code, conversions or [])
		# Only fill missing defaults for this company; anything already set is left as is.
		item = frappe.get_doc("Item", code)
		row = next((d for d in item.item_defaults if d.company == COMPANY), None)
		if not row:
			row = item.append("item_defaults", {"company": COMPANY})
		missing = {field: value for field, value in wanted.items() if value and not row.get(field)}
		if not missing:
			print(f"exists Item {code}")
		else:
			row.update(missing)
			item.save()
			print(f"fixed  Item {code}: default {', '.join(f'{k} = {v}' for k, v in missing.items())}")
		return code

	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": item_name,
			"item_group": item_group,
			"stock_uom": stock_uom,
			"is_stock_item": is_stock_item,
			"include_item_in_manufacturing": 0,
			"standard_rate": rate,
			"uoms": [{"uom": stock_uom, "conversion_factor": 1}] + (conversions or []),
			"item_defaults": [{"company": COMPANY, **{k: v for k, v in wanted.items() if v}}],
		}
	).insert()
	print(f"create Item {doc.name}")
	return doc.name


def ensure_stock_uom(code, stock_uom):
	"""Move an existing item to its stock UOM. ERPNext refuses once stock has moved, so only before that."""
	current = frappe.db.get_value("Item", code, "stock_uom")
	if current == stock_uom:
		return
	# ERPNext counts cancelled movements too.
	if frappe.db.exists("Stock Ledger Entry", {"item_code": code}):
		print(f"WARN   Item {code}: stock UOM is {current}, expected {stock_uom}; stock has moved, so not changed")
		return
	item = frappe.get_doc("Item", code)
	item.stock_uom = stock_uom
	# ERPNext empties the conversion table when the stock UOM changes; ensure_conversions puts it back.
	item.save()
	print(f"update Item {code}: stock UOM {current} -> {stock_uom}")


def ensure_conversions(code, conversions):
	"""Keep the item's conversion factors as given, whatever removed or changed them.

	A UOM missing from the item is converted with a factor of 1 on purchases and sales, so a box of
	2,500 sheets would come in as one sheet.
	"""
	item = frappe.get_doc("Item", code)
	factors = {d.uom: d.conversion_factor for d in item.uoms}
	wrong = [c for c in conversions if factors.get(c["uom"]) != c["conversion_factor"]]
	if not wrong:
		return
	for c in wrong:
		row = next((d for d in item.uoms if d.uom == c["uom"]), None) or item.append("uoms", {"uom": c["uom"]})
		row.conversion_factor = c["conversion_factor"]
	item.save()
	print(f"update Item {code}: " + ", ".join(f"1 {c['uom']} = {c['conversion_factor']:g} {item.stock_uom}" for c in wrong))


def ensure_paper_items():
	"""Every paper item is valued at moving average and bought by the box.

	Moving average: all sheets in a store cost the same, the average of what was paid, so a box bought at a
	new price changes the cost of every sheet. ERPNext refuses to change the method once stock has moved.
	"""
	for code in frappe.get_all("Item", filters={"item_group": PAPER_GROUP}, pluck="name"):
		item = frappe.get_doc("Item", code)
		changes = []
		if item.valuation_method != MOVING_AVERAGE:
			if frappe.db.exists("Stock Ledger Entry", {"item_code": code}):
				print(f"WARN   Item {code}: valued by {item.valuation_method or 'the default'}; stock has moved, so not changed")
			else:
				item.valuation_method = MOVING_AVERAGE
				changes.append(f"valuation {MOVING_AVERAGE}")
		# Bought by the box, so a quantity of 2 means 2 boxes, not 2 sheets.
		if not item.purchase_uom and any(d.uom == BOX for d in item.uoms):
			item.purchase_uom = BOX
			changes.append(f"bought by the {BOX}")
		if changes:
			item.save()
			print(f"update Item {code}: {', '.join(changes)}")
		else:
			print(f"exists Item {code}: paper settings")


def complete_setup_wizard():
	"""On a brand-new site, run ERPNext's setup wizard in code; it also creates the company.

	Without it ERPNext's base records (warehouse types, item groups, UOMs, customer groups, ...) do not
	exist and creating the company fails with "Could not find Warehouse Type: Transit".
	"""
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	setup_complete(
		{
			"language": "English",
			"country": "Egypt",
			"timezone": "Africa/Cairo",
			"currency": CURRENCY,
			"company_name": COMPANY,
			"company_abbr": ABBR,
			"chart_of_accounts": "Standard",
			# Same Sep-Aug academic year as setup_regional.py, so no wrong fiscal year is ever created.
			"fy_start_date": FISCAL_YEAR_START,
			"fy_end_date": FISCAL_YEAR_END,
		}
	)
	frappe.db.commit()
	print(f"create Setup wizard completed: Company {COMPANY} ({ABBR}, {CURRENCY}), fiscal year from {FISCAL_YEAR_START}")


def ensure_company():
	"""Create the company if missing; stop if an existing one has another abbreviation."""
	if not frappe.is_setup_complete():
		complete_setup_wizard()
		return True

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
	# Mawasah is the main warehouse and supplies Azarita by stock transfer (never a purchase).
	# Azarita is a separate branch warehouse, not under Mawasah, so Mawasah's totals never include
	# the branch's stock and Azarita's staff are kept out of Mawasah (setup_users.py).
	# Each library keeps raw materials (paper, ink, binding supplies) apart from doctors' editions,
	# the only goods sold; setup_coa.py gives each warehouse its own stock account.
	#   المخزن المركزي بالمواساة   (main)
	#     خامات المواساة / إصدارات الأطباء — المواساة / التالف — المواساة
	#   مخزن الأزاريطة             (branch)
	#     خامات الأزاريطة / إصدارات الأطباء — الأزاريطة
	#   مخزن سنتر Imed — أدوات مكتبية (the center's office supplies: ink, toner, ...)
	# Damaged goods are kept apart under Mawasah until they are sold by weight.
	central = make_warehouse("المخزن المركزي بالمواساة", ROOT_WH, is_group=1)
	if central:
		make_warehouse("خامات المواساة", central)
		make_warehouse("إصدارات الأطباء — المواساة", central)
		make_warehouse("التالف — المواساة", central)
	azarita = make_warehouse("مخزن الأزاريطة", ROOT_WH, is_group=1)
	if azarita:
		make_warehouse("خامات الأزاريطة", azarita)
		make_warehouse("إصدارات الأطباء — الأزاريطة", azarita)
	make_warehouse("مخزن سنتر Imed — أدوات مكتبية", ROOT_WH)

	# ---------- 3) Accounts ----------
	# Needs the company and the warehouses above; the items below need its income accounts.
	exec(open(frappe.get_app_path("imed_erp", "setup", "setup_coa.py")).read(), {"frappe": frappe})

	# ---------- 4) UOMs ----------
	# Paper is stocked in sheets, and a sheet cannot be split.
	for uom in ["رزمة", "كرتونة", "ورقة", "ساعة"]:
		whole = int(uom == SHEET)
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": whole}).insert()
			print(f"create UOM {uom}")
		elif whole and not frappe.db.get_value("UOM", uom, "must_be_whole_number"):
			frappe.db.set_value("UOM", uom, "must_be_whole_number", 1)
			print(f"update UOM {uom}: whole numbers only")
		else:
			print(f"exists UOM {uom}")

	# ---------- 5) Items ----------
	# ورق is one of the inventory groups of setup_library.py; made here too because A4 paper below needs it.
	for group in ["منتجات المكتبات", "الخدمات", "ورق"]:
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
	# A4 paper is stocked in sheets: 1 Ream = 500 sheets, 1 Box = 5 Reams = 2500 sheets.
	# Paper used up printing and photocopying for customers is a cost of what was sold (decided with the
	# owner); without this default, issuing it from stock would land on stock differences.
	make_item(
		"A4-PAPER",
		"ورق A4 80 جرام",
		"ورق",
		1,
		"إيراد مكتبة المواساة",
		conversions=[{"uom": "رزمة", "conversion_factor": 500}, {"uom": "كرتونة", "conversion_factor": 2500}],
		expense="تكلفة البضاعة المباعة",
		stock_uom=SHEET,
	)
	make_item("PRINT-SVC", "تصوير وطباعة", "منتجات المكتبات", 0, "إيراد مكتبة المواساة", rate=1)
	make_item("BINDING-SVC", "تجليد", "منتجات المكتبات", 0, "إيراد مكتبة المواساة")
	make_item("STUDIO-HOUR", "ساعة استوديو", "الخدمات", 0, "إيراد X Studio", stock_uom=HOUR)
	make_item("HALL-HOUR", "ساعة قاعة", "الخدمات", 0, "إيراد القاعات", stock_uom=HOUR)
	# Paper used to sit with the library products; it moves once to the paper group. Other items keep the
	# group they are in: setup_library.py moves the library services to their own group.
	if frappe.db.get_value("Item", "A4-PAPER", "item_group") != PAPER_GROUP:
		frappe.db.set_value("Item", "A4-PAPER", "item_group", PAPER_GROUP)
		print(f"update Item A4-PAPER: group -> {PAPER_GROUP}")
	ensure_paper_items()

	frappe.db.commit()
	print(f"DONE   Core setup finished for {COMPANY} ({ABBR}).")


run()
