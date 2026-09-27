import frappe

COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
print("Company:", COMPANY, "| Abbr:", ABBR)


def make_cc(name, parent, is_group=0):
    full = f"{name} - {ABBR}"
    if frappe.db.exists("Cost Center", full):
        print("exists:", full)
        return full
    doc = frappe.get_doc({
        "doctype": "Cost Center",
        "cost_center_name": name,
        "parent_cost_center": parent,
        "is_group": is_group,
        "company": COMPANY,
    }).insert()
    print("created CC:", doc.name)
    return doc.name


def make_account(name, parent, acc_type=None, is_group=0):
    full = f"{name} - {ABBR}"
    if frappe.db.exists("Account", full):
        print("exists:", full)
        return full
    if not frappe.db.exists("Account", parent):
        print("SKIP (parent not found):", name, "->", parent)
        return None
    doc = frappe.get_doc({
        "doctype": "Account",
        "account_name": name,
        "parent_account": parent,
        "account_type": acc_type,
        "is_group": is_group,
        "company": COMPANY,
    }).insert()
    print("created ACC:", doc.name)
    return doc.name


def make_wh(name, parent, is_group=0):
    full = f"{name} - {ABBR}"
    if frappe.db.exists("Warehouse", full):
        print("exists:", full)
        return full
    doc = frappe.get_doc({
        "doctype": "Warehouse",
        "warehouse_name": name,
        "parent_warehouse": parent,
        "is_group": is_group,
        "company": COMPANY,
    }).insert()
    print("created WH:", doc.name)
    return doc.name


# ---------- 1) Cost Centers ----------
root_cc = f"{COMPANY} - {ABBR}"

center = make_cc("Imed Center", root_cc, is_group=1)
make_cc("Imed Halls", center)
make_cc("X Studio", center)
make_cc("Center Shared Expenses", center)

libs = make_cc("Libraries", root_cc, is_group=1)
make_cc("2Be Doctor Azarita", libs)
make_cc("2Be Doctor Mawasah", libs)

make_cc("BA Plus App", root_cc)

# ---------- 2) Accounts ----------
cash_parent = f"Cash In Hand - {ABBR}"
bank_parent = f"Bank Accounts - {ABBR}"
ar_parent = f"Accounts Receivable - {ABBR}"
ap_parent = f"Accounts Payable - {ABBR}"
ca_parent = f"Current Assets - {ABBR}"
income_parent = f"Direct Income - {ABBR}"
exp_parent = f"Direct Expenses - {ABBR}"

for n in ["Cash Azarita", "Cash Mawasah", "Cash Center", "Cash Studio"]:
    make_account(n, cash_parent, "Cash")

for n in ["InstaPay Wallet", "Vodafone Cash Wallet"]:
    make_account(n, bank_parent, "Bank")

make_account("Doctors Receivable - Platform Fees", ar_parent, "Receivable")
make_account("Doctors Payable - Books", ap_parent, "Payable")
make_account("Inter Business Current Account", ca_parent)

for n in ["Books Revenue", "Printing Revenue", "Studio Revenue", "Halls Revenue",
          "Platform Fees Revenue", "Scrap Sales Revenue"]:
    make_account(n, income_parent, "Income Account")

for n in ["Doctors Share Cost", "Manufacturing Cost", "Wastage and Scrap"]:
    make_account(n, exp_parent, "Expense Account")

# ---------- 3) Warehouses ----------
root_wh = f"All Warehouses - {ABBR}"
central = make_wh("Central Store Mawasah", root_wh, is_group=1)
make_wh("Store Mawasah", central)
make_wh("Store Azarita", central)

# ---------- 4) UOMs ----------
for uom in ["Ream", "Box"]:
    if not frappe.db.exists("UOM", uom):
        frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert()
        print("created UOM:", uom)

# ---------- 5) Item Group ----------
if not frappe.db.exists("Item Group", "Library Products"):
    frappe.get_doc({
        "doctype": "Item Group",
        "item_group_name": "Library Products",
        "parent_item_group": "All Item Groups",
    }).insert()
    print("created Item Group: Library Products")


# ---------- 6) Items ----------
def make_item(code, name, group, stock_item, uom="Nos", rate=0, income=None, conversions=None):
    if frappe.db.exists("Item", code):
        print("exists item:", code)
        return code
    income_acc = f"{income} - {ABBR}" if income else None
    if income_acc and not frappe.db.exists("Account", income_acc):
        income_acc = None
    doc = frappe.get_doc({
        "doctype": "Item",
        "item_code": code,
        "item_name": name,
        "item_group": group,
        "stock_uom": uom,
        "is_stock_item": stock_item,
        "standard_rate": rate,
        "uoms": [{"uom": uom, "conversion_factor": 1}] + (conversions or []),
        "item_defaults": [{"company": COMPANY, "income_account": income_acc}],
    }).insert()
    print("created item:", doc.name)
    return doc.name


make_item("A4-PAPER", "A4 Paper", "Library Products", 1, "Nos", 0, "Printing Revenue",
          [{"uom": "Ream", "conversion_factor": 500},
           {"uom": "Box", "conversion_factor": 2500}])

make_item("PRINT-SVC", "Printing Service", "Library Products", 0, "Nos", 1, "Printing Revenue")
make_item("BINDING-SVC", "Binding Service", "Library Products", 0, "Nos", 10, "Printing Revenue")
make_item("STUDIO-HOUR", "Studio Hour", "Services", 0, "Nos", 0, "Studio Revenue")
make_item("HALL-HOUR", "Hall Hour", "Services", 0, "Nos", 0, "Halls Revenue")

frappe.db.commit()
print("Setup completed.")