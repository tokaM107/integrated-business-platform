# Chart of accounts for Mohamed Mamdouh group, built from section 2 of the posting rules
# document (قواعد الترحيل المحاسبي v2.0).
#
# setup_core.py runs this script itself, after it has created the company and the warehouses.
# To run it on its own from bench console:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_coa.py").read(), {"frappe": frappe})
#
# Idempotent: every account is guarded by frappe.db.exists, so anything that already exists is skipped.
# Safe to run again.
#
# Accounts the posting rules name that ERPNext already ships are used as they are, not duplicated:
#   العملاء، الموردون، مستحقات الموظفين، العرابين المقبوضة، سلف الموظفين، تكلفة البضاعة المباعة،
#   فروقات الجرد، الإيجار، المرافق، الرواتب والأجور، الصيانة، التسويق.
# setup_arabic_names.py gives them these Arabic names (ERPNext creates them in English with the company).
#
# Shared premises expenses are the "مصروفات المقر المشتركة" cost center (setup_core.py), not an account:
# each bill keeps its own expense account, and only the cost center changes when it is allocated.

import frappe

# Hardcoded on purpose: a demo company "Mohamed Mamdouh group (Demo)" also exists on the site.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"


def acc(name):
	return f"{name} - {ABBR}"


# (name, parent, account_type, is_group). A parent is always listed before its children.
ACCOUNTS = [
	# ---- Assets: treasuries ----
	("خزينة مكتبة الأزاريطة", "النقدية بالخزائن", "Cash", 0),
	("خزينة مكتبة المواساة", "النقدية بالخزائن", "Cash", 0),
	("خزينة سنتر Imed", "النقدية بالخزائن", "Cash", 0),
	("خزينة X Studio", "النقدية بالخزائن", "Cash", 0),
	("محفظة InstaPay", "الحسابات البنكية", "Bank", 0),
	("محفظة Vodafone Cash", "الحسابات البنكية", "Bank", 0),
	# ---- Assets: owed to us ----
	("مستحقات على الأطباء — رسوم المنصة", "الذمم المدينة", "Receivable", 0),
	# Negative doctor balances left when an edition is cancelled (DOC-20).
	("مديونيات الأطباء — الكتب", "الذمم المدينة", "Receivable", 0),
	# Money moving between businesses; never an expense (ACC-02).
	("الجاري بين الأنشطة", "الأصول المتداولة", None, 0),
	# ---- Assets: stock ----
	# ERPNext picks the stock account by warehouse, so each library gets one ledger per kind of stock.
	# Raw materials are paper, ink and binding supplies; doctors' editions are the only goods sold.
	("مخزون مكتبة المواساة", "المخزون", "Stock", 1),
	("مخزون المواساة — الخامات", "مخزون مكتبة المواساة", "Stock", 0),
	("مخزون المواساة — إصدارات الأطباء", "مخزون مكتبة المواساة", "Stock", 0),
	("مخزون مكتبة الأزاريطة", "المخزون", "Stock", 1),
	("مخزون الأزاريطة — الخامات", "مخزون مكتبة الأزاريطة", "Stock", 0),
	("مخزون الأزاريطة — إصدارات الأطباء", "مخزون مكتبة الأزاريطة", "Stock", 0),
	# ---- Liabilities ----
	# Money held for doctors from book sales; not group profit (RPT-11).
	("مستحقات للأطباء — الكتب", "الذمم الدائنة", "Payable", 0),
	# Lecturers' share under the hall revenue-share model (HAL-12).
	("مستحقات للمحاضرين", "الذمم الدائنة", "Payable", 0),
	# ---- Income: one account per business ----
	("إيراد مكتبة الأزاريطة", "الإيرادات المباشرة", "Income Account", 0),
	("إيراد مكتبة المواساة", "الإيرادات المباشرة", "Income Account", 0),
	("إيراد X Studio", "الإيرادات المباشرة", "Income Account", 0),
	("إيراد القاعات", "الإيرادات المباشرة", "Income Account", 0),
	("إيراد رسوم المنصة", "الإيرادات المباشرة", "Income Account", 0),
	("إيراد بيع التالف بالوزن", "الإيرادات المباشرة", "Income Account", 0),
	# ---- Costs ----
	("تكلفة التصنيع", "التكاليف المباشرة", "Expense Account", 0),
	("حصة الأطباء", "التكاليف المباشرة", "Expense Account", 0),
	("حصة المحاضرين", "التكاليف المباشرة", "Expense Account", 0),
	("الهالك والتالف", "التكاليف المباشرة", "Expense Account", 0),
	# ---- Expenses ----
	("الخامات والمستهلكات", "المصروفات غير المباشرة", "Expense Account", 0),
	("فروقات الخزينة", "المصروفات غير المباشرة", "Expense Account", 0),
	("الخصومات الممنوحة", "المصروفات غير المباشرة", "Expense Account", 0),
]

# Each warehouse (made by setup_core.py) posts its stock to this account.
WAREHOUSE_ACCOUNTS = {
	"خامات المواساة": "مخزون المواساة — الخامات",
	"إصدارات الأطباء — المواساة": "مخزون المواساة — إصدارات الأطباء",
	"خامات الأزاريطة": "مخزون الأزاريطة — الخامات",
	"إصدارات الأطباء — الأزاريطة": "مخزون الأزاريطة — إصدارات الأطباء",
}

# Revenue was split by business instead of by kind. These two existed only in English, before the
# Arabic rename. Item defaults on an old account move to its
# replacement, then the old account is deleted.
REPLACED_ACCOUNTS = {
	"Books Revenue": "إيراد مكتبة المواساة",
	"Printing Revenue": "إيراد مكتبة المواساة",
}


def make_account(name, parent, account_type, is_group):
	full = acc(name)
	if frappe.db.exists("Account", full):
		print(f"exists Account {full}")
		return full
	if not frappe.db.exists("Account", acc(parent)):
		print(f"SKIP   Account {full}: parent {acc(parent)} not found")
		return None
	doc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": name,
			"parent_account": acc(parent),
			"account_type": account_type,
			"is_group": is_group,
			"company": COMPANY,
		}
	).insert()
	print(f"create Account {doc.name}")
	return doc.name


def link_warehouse(warehouse, account):
	warehouse, account = acc(warehouse), acc(account)
	if not frappe.db.exists("Warehouse", warehouse):
		print(f"SKIP   Warehouse {warehouse}: not found (setup_core.py makes it)")
		return
	if not frappe.db.exists("Account", account):
		print(f"SKIP   Warehouse {warehouse}: account {account} not found")
		return
	current = frappe.db.get_value("Warehouse", warehouse, "account")
	if current == account:
		print(f"exists Warehouse {warehouse} -> {account}")
		return
	# Moving a warehouse that already holds stock to another account would split its value
	# across two ledgers, so only report it.
	if current and frappe.db.exists("Stock Ledger Entry", {"warehouse": warehouse, "is_cancelled": 0}):
		print(f"WARN   Warehouse {warehouse}: has stock on {current}, expected {account} (not changed)")
		return
	frappe.db.set_value("Warehouse", warehouse, "account", account)
	print(f"link   Warehouse {warehouse} -> {account}")


def remove_account(name, replacement):
	full, replacement = acc(name), acc(replacement)
	if not frappe.db.exists("Account", full):
		print(f"gone   Account {full}")
		return
	if frappe.db.exists("GL Entry", {"account": full}):
		print(f"WARN   Account {full}: has ledger entries, not deleted. Move them to {replacement} first.")
		return
	for row in frappe.get_all("Item Default", filters={"income_account": full}, fields=["name", "parent"]):
		frappe.db.set_value("Item Default", row.name, "income_account", replacement)
		print(f"fixed  Item {row.parent}: default income account {full} -> {replacement}")
	frappe.delete_doc("Account", full)
	print(f"delete Account {full}")


def run():
	if not frappe.db.exists("Company", COMPANY):
		print(f"STOP   Company '{COMPANY}' not found. Run setup_core.py first.")
		return

	for name, parent, account_type, is_group in ACCOUNTS:
		make_account(name, parent, account_type, is_group)

	for warehouse, account in WAREHOUSE_ACCOUNTS.items():
		link_warehouse(warehouse, account)

	for name, replacement in REPLACED_ACCOUNTS.items():
		remove_account(name, replacement)

	frappe.db.commit()
	print(f"DONE   Chart of accounts finished for {COMPANY} ({ABBR}).")


run()
