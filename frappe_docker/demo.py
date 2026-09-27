import frappe

COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"

# ---------- مجموعات صالحة ----------
if not frappe.get_all("Customer Group", filters={"is_group": 0}):
    frappe.get_doc({"doctype": "Customer Group", "customer_group_name": "General",
                    "parent_customer_group": "All Customer Groups"}).insert()
if not frappe.get_all("Supplier Group", filters={"is_group": 0}):
    frappe.get_doc({"doctype": "Supplier Group", "supplier_group_name": "General",
                    "parent_supplier_group": "All Supplier Groups"}).insert()

cg = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name")[0]
sg = frappe.get_all("Supplier Group", filters={"is_group": 0}, pluck="name")[0]
terr = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name")[0]

# ---------- عميل ومورد ----------
if not frappe.db.exists("Supplier", "Paper Supplier"):
    frappe.get_doc({"doctype": "Supplier", "supplier_name": "Paper Supplier",
                    "supplier_group": sg}).insert()
if not frappe.db.exists("Customer", "Test Student"):
    frappe.get_doc({"doctype": "Customer", "customer_name": "Test Student",
                    "customer_group": cg, "territory": terr}).insert()

# ---------- حساب المرافق ----------
utility = f"Utility Expenses - {ABBR}"
if not frappe.db.exists("Account", utility):
    found = frappe.get_all("Account",
                           filters={"company": COMPANY, "is_group": 0,
                                    "account_name": ["like", "%Utility%"]}, pluck="name")
    utility = found[0] if found else f"Miscellaneous Expenses - {ABBR}"
print("Utility account:", utility)

# ---------- 1) شراء كرتونتين ورق ----------
pr = frappe.get_doc({
    "doctype": "Purchase Receipt", "company": COMPANY, "supplier": "Paper Supplier",
    "items": [{
        "item_code": "A4-PAPER", "qty": 2, "uom": "Box", "conversion_factor": 2500,
        "rate": 300, "warehouse": f"Store Mawasah - {ABBR}",
        "cost_center": f"2Be Doctor Mawasah - {ABBR}",
    }],
}).insert()
pr.submit()
print("1) Purchased 2 boxes =", pr.items[0].stock_qty, "sheets")

# ---------- 2) تحويل كرتونة للأزاريطة ----------
se = frappe.get_doc({
    "doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": "Material Transfer",
    "items": [{
        "item_code": "A4-PAPER", "qty": 1, "uom": "Box", "conversion_factor": 2500,
        "s_warehouse": f"Store Mawasah - {ABBR}", "t_warehouse": f"Store Azarita - {ABBR}",
    }],
}).insert()
se.submit()
print("2) Transferred 1 box to Azarita")

# ---------- 3) بيع 100 ورقة من الأزاريطة ----------
si = frappe.get_doc({
    "doctype": "Sales Invoice", "company": COMPANY, "customer": "Test Student",
    "update_stock": 1,
    "items": [{
        "item_code": "A4-PAPER", "qty": 100, "rate": 1,
        "warehouse": f"Store Azarita - {ABBR}",
        "cost_center": f"2Be Doctor Azarita - {ABBR}",
        "income_account": f"Printing Revenue - {ABBR}",
    }],
}).insert()
si.submit()
print("3) Sold 100 sheets from Azarita")

# ---------- 4) مصروف كهربا مشترك ----------
je = frappe.get_doc({
    "doctype": "Journal Entry", "company": COMPANY, "voucher_type": "Journal Entry",
    "posting_date": frappe.utils.nowdate(),
    "user_remark": "Shared electricity",
    "accounts": [
        {"account": utility, "debit_in_account_currency": 180,
         "cost_center": f"X Studio - {ABBR}"},
        {"account": utility, "debit_in_account_currency": 120,
         "cost_center": f"Imed Halls - {ABBR}"},
        {"account": f"Cash Center - {ABBR}", "credit_in_account_currency": 300,
         "cost_center": f"Center Shared Expenses - {ABBR}"},
    ],
}).insert()
je.submit()
print("4) Shared electricity 300 split: Studio 180 / Halls 120")

# ---------- 5) تحويل من المكتبة للسنتر ----------
je2 = frappe.get_doc({
    "doctype": "Journal Entry", "company": COMPANY, "voucher_type": "Journal Entry",
    "posting_date": frappe.utils.nowdate(),
    "user_remark": "Library funding the Center",
    "accounts": [
        {"account": f"Inter Business Current Account - {ABBR}", "debit_in_account_currency": 500,
         "cost_center": f"Imed Center - {ABBR}"},
        {"account": f"Cash Azarita - {ABBR}", "credit_in_account_currency": 500,
         "cost_center": f"2Be Doctor Azarita - {ABBR}"},
    ],
}).insert()
je2.submit()
print("5) Transferred 500 from Library to Center (NOT an expense)")

frappe.db.commit()
print("\nDemo data ready.")