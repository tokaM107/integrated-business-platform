# Checks the library setup (LIB): item groups, services, product fields, warehouses, and that a sale
# picks the revenue account, cost center and warehouse by itself. Creates a test book, a test memo,
# stock movements and POS sales, then ROLLS EVERYTHING BACK, so nothing is saved.
#
# Run from bench console (after setup_library.py):
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/check_library.py").read(), {"frappe": frappe})

import frappe
from frappe.utils import flt, now_datetime, nowdate

# Hardcoded on purpose, like the other setup scripts.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"

CENTRAL = f"Store Mawasah - {ABBR}"
AZARITA = f"Store Azarita - {ABBR}"
BOOKS_REVENUE = f"Books Revenue - {ABBR}"
PRINTING_REVENUE = f"Printing Revenue - {ABBR}"
MAWASAH_CC = f"2Be Doctor Mawasah - {ABBR}"

# (code, is stock item, revenue account) as configured by setup_library.py
ITEMS = [
	("BOOK", 1, BOOKS_REVENUE),
	("MEMO", 1, BOOKS_REVENUE),
	("COPY-SVC", 0, PRINTING_REVENUE),
	("PRINT-SVC", 0, PRINTING_REVENUE),
	("BINDING-SVC", 0, PRINTING_REVENUE),
]

# (profile, cost center, warehouse, items sold as (code, expected revenue account, is stock item))
SALES = [
	(
		"2Be Doctor Azarita POS",
		f"2Be Doctor Azarita - {ABBR}",
		AZARITA,
		[("CHECK-LIB-BOOK", BOOKS_REVENUE, 1), ("COPY-SVC", PRINTING_REVENUE, 0)],
	),
	(
		"2Be Doctor Mawasah POS",
		f"2Be Doctor Mawasah - {ABBR}",
		CENTRAL,
		[
			("CHECK-LIB-MEMO", BOOKS_REVENUE, 1),
			("PRINT-SVC", PRINTING_REVENUE, 0),
			("BINDING-SVC", PRINTING_REVENUE, 0),
		],
	),
]

results = []


def check(label, ok, detail=""):
	results.append(bool(ok))
	print(f"{'PASS' if ok else 'FAIL'}  {label}{'  -> ' + str(detail) if detail != '' else ''}")


def stock_qty(item, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty"))


def test_customer():
	group = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
	territory = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
	return (
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "Check Library Student",
				"customer_group": group[0] if group else "All Customer Groups",
				"territory": territory[0] if territory else "All Territories",
			}
		)
		.insert()
		.name
	)


def test_item(code, group, cost, price, isbn=None):
	"""A stock item with the LIB-06 product data, built the way setup_library.py builds the catalogue."""
	return frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": group,
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"include_item_in_manufacturing": 0,
			"custom_author": "Check Library Author",
			"valuation_rate": cost,
			"standard_rate": price,
			"barcodes": [{"barcode": isbn, "barcode_type": "ISBN"}] if isbn else [],
			"item_defaults": [
				{
					"company": COMPANY,
					"default_warehouse": CENTRAL,
					"income_account": BOOKS_REVENUE,
					"selling_cost_center": MAWASAH_CC,
				}
			],
		}
	).insert()


def stock_entry(purpose, rows):
	doc = frappe.get_doc(
		{"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": purpose, "purpose": purpose, "items": rows}
	).insert()
	doc.submit()
	return doc


def pos_sale(profile, customer, sold):
	"""Open the till, then sell with only the item code and quantity filled in."""
	cashier = frappe.db.get_value("POS Profile User", {"parent": profile, "default": 1}, "user")
	frappe.get_doc(
		{
			"doctype": "POS Opening Entry",
			"company": COMPANY,
			"pos_profile": profile,
			"user": cashier,
			"period_start_date": now_datetime(),
			"posting_date": nowdate(),
			"balance_details": [{"mode_of_payment": "Cash", "opening_amount": 0}],
		}
	).insert().submit()
	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": COMPANY,
			"customer": customer,
			"is_pos": 1,
			"pos_profile": profile,
			# Books and memos take their price from the price list. Services get a test price here:
			# copying and binding have no agreed price yet, and a zero line posts nothing to the ledger.
			"items": [
				{"item_code": code, "qty": 1, **({} if is_stock else {"rate": 2})} for code, _, is_stock in sold
			],
		}
	)
	# What the sale screen does when the profile is chosen: payment modes and defaults come from it.
	si.set_missing_values()
	si.insert()
	si.payments[0].amount = si.grand_total
	si.save()
	si.submit()
	return si


def run():
	if frappe.db.get_value("Company", COMPANY, "abbr") != ABBR:
		print(f"STOP  Company '{COMPANY}' with abbr '{ABBR}' not found.")
		return

	# ---------- 1) Item groups ----------
	check("Library Products is a group", frappe.db.get_value("Item Group", "Library Products", "is_group"))
	for group in ["Books", "Memos", "Library Services"]:
		parent = frappe.db.get_value("Item Group", group, "parent_item_group")
		check(f"Item Group {group} is under Library Products", parent == "Library Products", parent)

	# ---------- 2) Items: books and memos are stock items, services are not; item defaults ----------
	for code, is_stock, income in ITEMS:
		item = frappe.db.get_value("Item", code, ["is_stock_item", "item_group"], as_dict=True)
		check(
			f"{code} is a {'stock item' if is_stock else 'non-stock service'}",
			item and item.is_stock_item == is_stock,
			item or "missing",
		)
		default = frappe.db.get_value(
			"Item Default",
			{"parent": code, "company": COMPANY},
			["income_account", "selling_cost_center", "default_warehouse"],
		)
		check(f"{code} item defaults", default == (income, MAWASAH_CC, CENTRAL), default)

	# ---------- 3) Product fields (LIB-06) ----------
	check("Item has an Author field", frappe.get_meta("Item").has_field("custom_author"))
	barcode_types = frappe.get_meta("Item Barcode").get_options("barcode_type").split("\n")
	check("Item barcodes accept the ISBN type", "ISBN" in barcode_types)

	# ---------- 4) Warehouses (LIB-02) ----------
	for warehouse in [CENTRAL, AZARITA]:
		row = frappe.db.get_value("Warehouse", warehouse, ["is_group", "company"], as_dict=True)
		check(f"Warehouse {warehouse} exists and can hold stock", row and not row.is_group and row.company == COMPANY)

	# Everything below writes test data, so commits are disabled and the whole block is rolled back.
	real_commit = frappe.db.commit
	frappe.db.commit = lambda *args, **kwargs: None
	try:
		customer = test_customer()
		book = test_item("CHECK-LIB-BOOK", "Books", cost=100, price=150, isbn="9780306406157")
		test_item("CHECK-LIB-MEMO", "Memos", cost=40, price=60)

		# ---------- 5) Product data ----------
		check("Book keeps its ISBN and author", book.barcodes[0].barcode_type == "ISBN" and book.custom_author)
		by_isbn = frappe.db.get_value("Item Barcode", {"barcode": "9780306406157"}, "parent")
		check("Book is found by its ISBN", by_isbn == book.name, by_isbn)
		price = frappe.db.get_value("Item Price", {"item_code": book.name, "selling": 1}, "price_list_rate")
		check("Book selling price is 150", price == 150, price)

		# ---------- 6) Stock: into the central store, then issued to Azarita (LIB-02, LIB-08) ----------
		stock_entry(
			"Material Receipt",
			[
				{"item_code": "CHECK-LIB-BOOK", "qty": 10, "t_warehouse": CENTRAL, "basic_rate": 100},
				{"item_code": "CHECK-LIB-MEMO", "qty": 10, "t_warehouse": CENTRAL, "basic_rate": 40},
			],
		)
		stock_entry(
			"Material Transfer",
			[{"item_code": "CHECK-LIB-BOOK", "qty": 4, "s_warehouse": CENTRAL, "t_warehouse": AZARITA}],
		)
		check("Central store holds 6 books after issuing 4", stock_qty("CHECK-LIB-BOOK", CENTRAL) == 6)
		check("Azarita holds the 4 books issued to it", stock_qty("CHECK-LIB-BOOK", AZARITA) == 4)
		cost = frappe.db.get_value("Bin", {"item_code": "CHECK-LIB-BOOK", "warehouse": AZARITA}, "valuation_rate")
		check("Book cost price is 100 in Azarita", cost == 100, cost)

		# ---------- 7) POS sales: nothing but item and quantity is entered ----------
		for profile, cost_center, warehouse, sold in SALES:
			if not frappe.db.exists("POS Profile", profile):
				check(f"{profile} exists", False, "run setup_library.py")
				continue
			before = {code: stock_qty(code, warehouse) for code, _, is_stock in sold if is_stock}
			si = pos_sale(profile, customer, sold)
			print(f"      {profile}: invoice of {len(si.items)} items, total {si.grand_total}")
			for row, (code, income, is_stock) in zip(si.items, sold):
				check(f"{code}: revenue account", row.income_account == income, row.income_account)
				check(f"{code}: cost center", row.cost_center == cost_center, row.cost_center)
				if is_stock:
					check(f"{code}: warehouse", row.warehouse == warehouse, row.warehouse)
					check(f"{code}: stock in {warehouse} went down by 1", stock_qty(code, warehouse) == before[code] - 1)
					check(f"{code}: sold at its selling price", row.rate > 0, row.rate)
				else:
					moved = frappe.db.count("Stock Ledger Entry", {"voucher_no": si.name, "item_code": code})
					check(f"{code}: service moves no stock", moved == 0, moved)

			# The ledger must agree with the invoice rows.
			ledger = frappe.get_all(
				"GL Entry",
				filters={"voucher_no": si.name, "account": ["in", [BOOKS_REVENUE, PRINTING_REVENUE]], "is_cancelled": 0},
				fields=["account", "cost_center"],
			)
			check(
				f"{profile}: revenue is posted to {cost_center}",
				ledger and all(g.cost_center == cost_center for g in ledger),
				sorted({g.cost_center for g in ledger}),
			)
			check(
				f"{profile}: revenue accounts in the ledger",
				{g.account for g in ledger} == {income for _, income, _ in sold},
				sorted({g.account for g in ledger}),
			)

		# ---------- 8) Plain sales invoice (no POS Profile): the item's own defaults apply ----------
		# get_item_details is what the form calls when an item is picked in a row. A row inserted
		# through the API without a cost center gets the company's default one instead, so an
		# integration must send the cost center itself.
		from erpnext.stock.get_item_details import get_item_details

		rows = []
		for code, income in [("BOOK", BOOKS_REVENUE), ("COPY-SVC", PRINTING_REVENUE)]:
			picked = get_item_details(
				{
					"doctype": "Sales Invoice",
					"company": COMPANY,
					"customer": customer,
					"item_code": code,
					"qty": 1,
					"currency": "EGP",
					"conversion_rate": 1,
					"selling_price_list": "Standard Selling",
				}
			)
			check(f"Sales invoice, {code}: revenue account", picked.income_account == income, picked.income_account)
			check(f"Sales invoice, {code}: cost center", picked.cost_center == MAWASAH_CC, picked.cost_center)
			check(f"Sales invoice, {code}: warehouse", picked.warehouse == CENTRAL, picked.warehouse)
			rows.append(
				{
					"item_code": code,
					"qty": 1,
					"rate": 10,
					"income_account": picked.income_account,
					"cost_center": picked.cost_center,
					"warehouse": picked.warehouse,
				}
			)
		si = frappe.get_doc(
			{"doctype": "Sales Invoice", "company": COMPANY, "customer": customer, "due_date": nowdate(), "items": rows}
		).insert()
		si.submit()
		ledger = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": si.name, "account": ["in", [BOOKS_REVENUE, PRINTING_REVENUE]], "is_cancelled": 0},
			fields=["account", "cost_center"],
		)
		check(
			f"Sales invoice: both revenue accounts are posted to {MAWASAH_CC}",
			{(g.account, g.cost_center) for g in ledger} == {(BOOKS_REVENUE, MAWASAH_CC), (PRINTING_REVENUE, MAWASAH_CC)},
			sorted({(g.account, g.cost_center) for g in ledger}),
		)
	finally:
		frappe.db.rollback()
		frappe.db.commit = real_commit

	print()
	print(f"{sum(results)}/{len(results)} checks passed. [test data rolled back, nothing saved]")


run()
