# Core setup for Mohamed Mamdouh group: company, cost centers, accounts, warehouses, UOMs, items.
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

# First fiscal year, used only when this script runs the setup wizard on a new site.
# Must match the first entry of FISCAL_YEARS in setup_regional.py (academic year, Sep-Aug).
FISCAL_YEAR_START = "2026-09-01"
FISCAL_YEAR_END = "2027-08-31"

# Tree roots, built by name. Filtering on parent = "" returns nothing because the root's parent is NULL.
ROOT_CC = f"{COMPANY} - {ABBR}"
ROOT_WH = f"All Warehouses - {ABBR}"


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


def make_account(name, parent, account_type=None):
	full = acc(name)
	if frappe.db.exists("Account", full):
		print(f"exists Account {full}")
		return full
	if not frappe.db.exists("Account", parent):
		print(f"SKIP   Account {full}: parent {parent} not found")
		return None
	doc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": name,
			"parent_account": parent,
			"account_type": account_type,
			"is_group": 0,
			"company": COMPANY,
		}
	).insert()
	print(f"create Account {doc.name}")
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


def item_default(income_account):
	# The warehouse is set explicitly: otherwise Frappe fills it from the site-wide default warehouse,
	# which belongs to another company when one exists (e.g. "Stores - I"), and the item is rejected.
	# Store Mawasah holds the central stock.
	return {"company": COMPANY, "income_account": income_account, "default_warehouse": acc("Store Mawasah")}


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
				item.append("item_defaults", item_default(income_account))
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
			"item_defaults": [item_default(income_account)],
		}
	).insert()
	print(f"create Item {doc.name}")
	return doc.name


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

	# ---------- 1) Cost centers ----------
	# Imed Center and X Studio share premises, so they sit under one group.
	# Shared rent/electricity is booked to "Center Shared Expenses" (a leaf, so it can
	# be used in transactions) and then allocated to Imed Halls / X Studio.
	center = make_cost_center("Imed Center", ROOT_CC, is_group=1)
	if center:
		make_cost_center("Imed Halls", center)
		make_cost_center("X Studio", center)
		make_cost_center("Center Shared Expenses", center)

	libraries = make_cost_center("Libraries", ROOT_CC, is_group=1)
	if libraries:
		make_cost_center("2Be Doctor Azarita", libraries)
		make_cost_center("2Be Doctor Mawasah", libraries)

	make_cost_center("BA Plus App", ROOT_CC)

	# ---------- 2) Accounts ----------
	for name in ["Cash Azarita", "Cash Mawasah", "Cash Center", "Cash Studio"]:
		make_account(name, acc("Cash In Hand"), "Cash")

	for name in ["InstaPay Wallet", "Vodafone Cash Wallet"]:
		make_account(name, acc("Bank Accounts"), "Bank")

	make_account("Doctors Receivable - Platform Fees", acc("Accounts Receivable"), "Receivable")
	make_account("Doctors Payable - Books", acc("Accounts Payable"), "Payable")
	make_account("Inter Business Current Account", acc("Current Assets"))

	for name in [
		"Books Revenue",
		"Printing Revenue",
		"Studio Revenue",
		"Halls Revenue",
		"Platform Fees Revenue",
		"Scrap Sales Revenue",
	]:
		make_account(name, acc("Direct Income"), "Income Account")

	for name in ["Doctors Share Cost", "Manufacturing Cost", "Wastage and Scrap"]:
		make_account(name, acc("Direct Expenses"), "Expense Account")

	# ---------- 3) Warehouses ----------
	# The group's only central store is at Mawasah; branch stores sit under it.
	central = make_warehouse("Central Store Mawasah", ROOT_WH, is_group=1)
	if central:
		make_warehouse("Store Mawasah", central)
		make_warehouse("Store Azarita", central)

	# ---------- 4) UOMs ----------
	for uom in ["Ream", "Box"]:
		if frappe.db.exists("UOM", uom):
			print(f"exists UOM {uom}")
		else:
			frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert()
			print(f"create UOM {uom}")

	# ---------- 5) Items ----------
	for group in ["Library Products", "Services"]:
		if frappe.db.exists("Item Group", group):
			print(f"exists Item Group {group}")
		else:
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": group, "parent_item_group": "All Item Groups"}
			).insert()
			print(f"create Item Group {group}")

	# A4 paper is stocked in sheets (Nos): 1 Ream = 500 sheets, 1 Box = 5 Reams = 2500 sheets.
	make_item(
		"A4-PAPER",
		"A4 Paper",
		"Library Products",
		1,
		"Printing Revenue",
		conversions=[{"uom": "Ream", "conversion_factor": 500}, {"uom": "Box", "conversion_factor": 2500}],
	)
	make_item("PRINT-SVC", "Printing Service", "Library Products", 0, "Printing Revenue", rate=1)
	make_item("BINDING-SVC", "Binding Service", "Library Products", 0, "Printing Revenue")
	make_item("STUDIO-HOUR", "Studio Hour", "Services", 0, "Studio Revenue")
	make_item("HALL-HOUR", "Hall Hour", "Services", 0, "Halls Revenue")

	frappe.db.commit()
	print(f"DONE   Core setup finished for {COMPANY} ({ABBR}).")


run()
