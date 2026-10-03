# Renames Mohamed Mamdouh group's records from their English names to Arabic: accounts, cost centers,
# warehouses, item groups, UOMs and item names.
#
# setup_core.py runs this script itself, right after the company exists, so on a new site the
# English accounts and warehouses ERPNext creates with the company are renamed before anything uses them.
# To run it on its own from bench console:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_arabic_names.py").read(), {"frappe": frappe})
#
# Idempotent: a record is renamed only while its English name exists and its Arabic name does not.
# Renaming updates every link to the record (transactions, item defaults, User Permissions, company defaults).
#
# Left in English on purpose: the company itself, the "All Item Groups" root and the "Nos" UOM, which
# ERPNext uses as literal names (Nos is the default stock UOM of every new item).

import frappe
from erpnext.accounts.doctype.account.account import update_account_number
from erpnext.accounts.utils import update_cost_center

# Hardcoded on purpose: a demo company "Mohamed Mamdouh group (Demo)" also exists on the site.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"


def acc(name):
	return f"{name} - {ABBR}"


# English account name -> Arabic. Our own accounts use the names of the posting rules document (v2.0).
ACCOUNTS = {
	# ---- Assets ----
	"Application of Funds (Assets)": "الأصول",
	"Current Assets": "الأصول المتداولة",
	"Accounts Receivable": "الذمم المدينة",
	"Debtors": "العملاء",
	"Doctors Receivable - Platform Fees": "مستحقات على الأطباء — رسوم المنصة",
	"Doctors Receivable - Books": "مديونيات الأطباء — الكتب",
	"Bank Accounts": "الحسابات البنكية",
	"InstaPay Wallet": "محفظة InstaPay",
	"Vodafone Cash Wallet": "محفظة Vodafone Cash",
	"Cash In Hand": "النقدية بالخزائن",
	"Cash": "الخزينة الرئيسية",
	"Cash Azarita": "خزينة مكتبة الأزاريطة",
	"Cash Mawasah": "خزينة مكتبة المواساة",
	"Cash Center": "خزينة سنتر Imed",
	"Cash Studio": "خزينة X Studio",
	"Loans and Advances (Assets)": "القروض والسلف",
	"Employee Advances": "سلف الموظفين",
	"Prepaid Expenses": "مصروفات مدفوعة مقدماً",
	"Securities and Deposits": "التأمينات والودائع",
	"Earnest Money": "تأمينات مدفوعة",
	"Short-term Investments": "استثمارات قصيرة الأجل",
	"Stock Assets": "المخزون",
	"Stock In Hand": "المخزون العام",
	"Stock Mawasah": "مخزون مكتبة المواساة",
	"Stock Mawasah - Raw Materials": "مخزون المواساة — الخامات",
	"Stock Mawasah - Doctors Editions": "مخزون المواساة — إصدارات الأطباء",
	"Stock Azarita": "مخزون مكتبة الأزاريطة",
	"Stock Azarita - Raw Materials": "مخزون الأزاريطة — الخامات",
	"Stock Azarita - Doctors Editions": "مخزون الأزاريطة — إصدارات الأطباء",
	"Tax Assets": "أصول ضريبية",
	"Inter Business Current Account": "الجاري بين الأنشطة",
	"Fixed Assets": "الأصول الثابتة",
	"Accumulated Depreciation": "مجمع الإهلاك",
	"Buildings": "المباني",
	"Capital Equipment": "المعدات الرأسمالية",
	"CWIP Account": "مشروعات تحت التنفيذ",
	"Electronic Equipment": "الأجهزة الإلكترونية",
	"Furniture and Fixtures": "الأثاث والتجهيزات",
	"Office Equipment": "المعدات المكتبية",
	"Plants and Machineries": "الآلات والماكينات",
	"Software": "البرامج",
	"Investments": "الاستثمارات",
	"Temporary Accounts": "حسابات مؤقتة",
	"Temporary Opening": "أرصدة افتتاحية مؤقتة",
	# ---- Equity ----
	"Equity": "حقوق الملكية",
	"Capital Stock": "رأس المال",
	"Dividends Paid": "توزيعات الأرباح",
	"Opening Balance Equity": "حقوق ملكية الأرصدة الافتتاحية",
	"Retained Earnings": "الأرباح المحتجزة",
	"Revaluation Surplus": "فائض إعادة التقييم",
	# ---- Liabilities ----
	"Source of Funds (Liabilities)": "الالتزامات",
	"Current Liabilities": "الالتزامات المتداولة",
	"Accounts Payable": "الذمم الدائنة",
	"Creditors": "الموردون",
	"Payroll Payable": "مستحقات الموظفين",
	"Doctors Payable - Books": "مستحقات للأطباء — الكتب",
	"Lecturers Payable": "مستحقات للمحاضرين",
	"Accrued Expenses": "مصروفات مستحقة",
	"Customer Advances": "العرابين المقبوضة",
	"Duties and Taxes": "الضرائب والرسوم",
	"GST": "ضريبة القيمة المضافة",
	"Loans (Liabilities)": "القروض",
	"Bank Overdraft Account": "السحب على المكشوف",
	"Secured Loans": "قروض بضمان",
	"Unsecured Loans": "قروض بدون ضمان",
	"Short-term Provisions": "مخصصات قصيرة الأجل",
	"Stock Liabilities": "التزامات المخزون",
	"Asset Received But Not Billed": "أصول مستلمة لم تصل فاتورتها",
	"Stock Received But Not Billed": "بضاعة مستلمة لم تصل فاتورتها",
	"Non-Current Liabilities": "الالتزامات طويلة الأجل",
	"Employee Benefits Obligation": "التزامات مزايا الموظفين",
	"Long-term Provisions": "مخصصات طويلة الأجل",
	# ---- Income ----
	"Income": "الإيرادات",
	"Direct Income": "الإيرادات المباشرة",
	"Sales": "المبيعات",
	"Service": "إيراد الخدمات",
	"Azarita Library Revenue": "إيراد مكتبة الأزاريطة",
	"Mawasah Library Revenue": "إيراد مكتبة المواساة",
	"Studio Revenue": "إيراد X Studio",
	"Halls Revenue": "إيراد القاعات",
	"Platform Fees Revenue": "إيراد رسوم المنصة",
	"Scrap Sales Revenue": "إيراد بيع التالف بالوزن",
	"Indirect Income": "الإيرادات الأخرى",
	"Interest Income": "إيراد الفوائد",
	"Interest on Fixed Deposits": "فوائد الودائع",
	# ---- Costs and expenses ----
	"Expenses": "المصروفات",
	"Direct Expenses": "التكاليف المباشرة",
	"Stock Expenses": "تكاليف المخزون",
	"Cost of Goods Sold": "تكلفة البضاعة المباعة",
	"Expenses Included In Asset Valuation": "مصروفات محملة على قيمة الأصول",
	"Expenses Included In Valuation": "مصروفات محملة على تكلفة المخزون",
	"Stock Adjustment": "فروقات الجرد",
	"Manufacturing Cost": "تكلفة التصنيع",
	"Doctors Share Cost": "حصة الأطباء",
	"Lecturers Share Cost": "حصة المحاضرين",
	"Wastage and Scrap": "الهالك والتالف",
	"Indirect Expenses": "المصروفات غير المباشرة",
	"Administrative Expenses": "مصروفات إدارية",
	"Bank Charges": "مصروفات بنكية",
	"Commission on Sales": "عمولات المبيعات",
	"Depreciation": "الإهلاك",
	"Entertainment Expenses": "مصروفات ضيافة",
	"Exchange Gain/Loss": "أرباح وخسائر فروق العملة",
	"Freight and Forwarding Charges": "مصروفات الشحن والنقل",
	"Gain/Loss on Asset Disposal": "أرباح وخسائر بيع الأصول",
	"Impairment": "اضمحلال قيمة الأصول",
	"Interest Expense": "مصروفات الفوائد",
	"Legal Expenses": "مصروفات قانونية",
	"Marketing Expenses": "التسويق",
	"Miscellaneous Expenses": "مصروفات متنوعة",
	"Office Maintenance Expenses": "الصيانة",
	"Office Rent": "الإيجار",
	"Postal Expenses": "مصروفات البريد",
	"Print and Stationery": "أدوات مكتبية ومطبوعات",
	"Round Off": "فروق التقريب",
	"Salary": "الرواتب والأجور",
	"Sales Expenses": "مصروفات البيع",
	"Tax Expense": "مصروفات الضرائب",
	"Telephone Expenses": "مصروفات التليفون",
	"Travel Expenses": "مصروفات السفر",
	"Utility Expenses": "المرافق",
	"Write Off": "مبالغ مشطوبة",
	"Raw Materials and Consumables": "الخامات والمستهلكات",
	"Cash Over and Short": "فروقات الخزينة",
	"Discount Allowed": "الخصومات الممنوحة",
}

COST_CENTERS = {
	"Main": "الإدارة الرئيسية",
	"Imed Center": "سنتر Imed",
	"Imed Halls": "قاعات Imed",
	"X Studio": "استوديو X",
	"Center Shared Expenses": "مصروفات المقر المشتركة",
	"Libraries": "مكتبات 2Be Doctor",
	"2Be Doctor Azarita": "مكتبة الأزاريطة",
	"2Be Doctor Mawasah": "مكتبة المواساة",
	"BA Plus App": "تطبيق BA Plus",
}

WAREHOUSES = {
	"All Warehouses": "كل المخازن",
	"Central Store Mawasah": "المخزن المركزي بالمواساة",
	"Store Mawasah": "خامات المواساة",
	"Doctors Editions Mawasah": "إصدارات الأطباء — المواساة",
	"Store Azarita": "خامات الأزاريطة",
	"Doctors Editions Azarita": "إصدارات الأطباء — الأزاريطة",
	"Stores": "المخزن العام",
	"Work In Progress": "تحت التشغيل",
	"Finished Goods": "إنتاج تام",
	"Goods In Transit": "بضاعة في الطريق",
}

ITEM_GROUPS = {
	"Library Products": "منتجات المكتبات",
	"Services": "الخدمات",
	"Products": "منتجات",
	"Raw Material": "خامات",
	"Consumable": "مستهلكات",
	"Sub Assemblies": "مكونات فرعية",
}

UOMS = {"Ream": "رزمة", "Box": "كرتونة"}

# Item codes stay as they are (they are what people type and scan); only the shown name changes.
ITEM_NAMES = {
	"A4-PAPER": "ورق A4 80 جرام",
	"PRINT-SVC": "تصوير وطباعة",
	"BINDING-SVC": "تجليد",
	"STUDIO-HOUR": "ساعة استوديو",
	"HALL-HOUR": "ساعة قاعة",
}


def needs_rename(doctype, old, new):
	if frappe.db.exists(doctype, new):
		print(f"exists {doctype} {new}")
		return False
	if not frappe.db.exists(doctype, old):
		return False
	return True


def rename_accounts():
	for old, new in ACCOUNTS.items():
		old_name = acc(old)
		if not needs_rename("Account", old_name, acc(new)):
			continue
		if frappe.db.get_value("Account", old_name, "company") != COMPANY:
			continue
		update_account_number(old_name, new)
		print(f"rename Account {old_name} -> {acc(new)}")


def rename_cost_centers():
	for old, new in COST_CENTERS.items():
		if needs_rename("Cost Center", acc(old), acc(new)):
			update_cost_center(acc(old), new, None, COMPANY, False)
			print(f"rename Cost Center {acc(old)} -> {acc(new)}")


def rename_warehouses():
	# ERPNext hides Rename on warehouses; force it. warehouse_name is the label without the abbreviation.
	for old, new in WAREHOUSES.items():
		if needs_rename("Warehouse", acc(old), acc(new)):
			frappe.rename_doc("Warehouse", acc(old), acc(new), force=True)
			frappe.db.set_value("Warehouse", acc(new), "warehouse_name", new)
			print(f"rename Warehouse {acc(old)} -> {acc(new)}")


def rename_plain(doctype, mapping):
	for old, new in mapping.items():
		if needs_rename(doctype, old, new):
			frappe.rename_doc(doctype, old, new, force=True)
			print(f"rename {doctype} {old} -> {new}")


def rename_items():
	for code, name in ITEM_NAMES.items():
		item = frappe.db.get_value("Item", code, ["item_name", "description"], as_dict=True)
		if not item:
			continue
		if item.item_name == name:
			print(f"exists Item {code} ({name})")
			continue
		values = {"item_name": name}
		# ERPNext copies the name into the description; keep them together unless someone wrote a real one.
		if not item.description or item.description in (item.item_name, f"<p>{item.item_name}</p>"):
			values["description"] = name
		frappe.db.set_value("Item", code, values)
		print(f"rename Item {code}: {item.item_name} -> {name}")


def run():
	if not frappe.db.exists("Company", COMPANY):
		print(f"STOP   Company '{COMPANY}' not found. Run setup_core.py first.")
		return

	rename_accounts()
	rename_cost_centers()
	rename_warehouses()
	rename_plain("Item Group", ITEM_GROUPS)
	rename_plain("UOM", UOMS)
	rename_items()

	frappe.db.commit()
	print(f"DONE   Arabic names finished for {COMPANY} ({ABBR}).")


run()
