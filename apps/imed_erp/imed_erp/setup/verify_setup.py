# Read-only check of what setup_core.py, setup_coa.py and setup_users.py should have created.
#
# Run from bench console:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/verify_setup.py").read(), {"frappe": frappe})
#
# Prints OK / MISSING / WRONG per record, then counts per category. Changes nothing.

import frappe

# Hardcoded on purpose: a demo company "Mohamed Mamdouh group (Demo)" also exists on the site.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
CURRENCY = "EGP"

ROOT_CC = f"{COMPANY} - {ABBR}"
ROOT_WH = f"كل المخازن - {ABBR}"


def acc(name):
	return f"{name} - {ABBR}"


# (name, parent, is_group)
COST_CENTERS = [
	("سنتر Imed", ROOT_CC, 1),
	("قاعات Imed", acc("سنتر Imed"), 0),
	("استوديو X", acc("سنتر Imed"), 0),
	("مصروفات المقر المشتركة", acc("سنتر Imed"), 0),
	("مكتبات 2Be Doctor", ROOT_CC, 1),
	("مكتبة الأزاريطة", acc("مكتبات 2Be Doctor"), 0),
	("مكتبة المواساة", acc("مكتبات 2Be Doctor"), 0),
	("تطبيق BA Plus", ROOT_CC, 0),
]

# (name, parent, account_type, is_group) - must match setup_coa.py.
ACCOUNTS = (
	[(n, acc("النقدية بالخزائن"), "Cash", 0) for n in ["خزينة مكتبة الأزاريطة", "خزينة مكتبة المواساة", "خزينة سنتر Imed", "خزينة X Studio"]]
	+ [(n, acc("الحسابات البنكية"), "Bank", 0) for n in ["محفظة InstaPay", "محفظة Vodafone Cash"]]
	+ [
		("مستحقات على الأطباء — رسوم المنصة", acc("الذمم المدينة"), "Receivable", 0),
		("مديونيات الأطباء — الكتب", acc("الذمم المدينة"), "Receivable", 0),
		("الجاري بين الأنشطة", acc("الأصول المتداولة"), "", 0),
		("مخزون مكتبة المواساة", acc("المخزون"), "Stock", 1),
		("مخزون المواساة — الخامات", acc("مخزون مكتبة المواساة"), "Stock", 0),
		("مخزون المواساة — إصدارات الأطباء", acc("مخزون مكتبة المواساة"), "Stock", 0),
		("مخزون مكتبة الأزاريطة", acc("المخزون"), "Stock", 1),
		("مخزون الأزاريطة — الخامات", acc("مخزون مكتبة الأزاريطة"), "Stock", 0),
		("مخزون الأزاريطة — إصدارات الأطباء", acc("مخزون مكتبة الأزاريطة"), "Stock", 0),
		("مستحقات للأطباء — الكتب", acc("الذمم الدائنة"), "Payable", 0),
		("مستحقات للمحاضرين", acc("الذمم الدائنة"), "Payable", 0),
	]
	+ [
		(n, acc("الإيرادات المباشرة"), "Income Account", 0)
		for n in [
			"إيراد مكتبة الأزاريطة",
			"إيراد مكتبة المواساة",
			"إيراد X Studio",
			"إيراد القاعات",
			"إيراد رسوم المنصة",
			"إيراد بيع التالف بالوزن",
		]
	]
	+ [
		(n, acc("التكاليف المباشرة"), "Expense Account", 0)
		for n in ["تكلفة التصنيع", "حصة الأطباء", "حصة المحاضرين", "الهالك والتالف"]
	]
	+ [
		(n, acc("المصروفات غير المباشرة"), "Expense Account", 0)
		for n in ["الخامات والمستهلكات", "فروقات الخزينة", "الخصومات الممنوحة"]
	]
)

# Replaced by one revenue account per library; setup_coa.py deletes them.
REMOVED_ACCOUNTS = ["Books Revenue", "Printing Revenue"]

# (name, parent, is_group)
WAREHOUSES = [
	("المخزن المركزي بالمواساة", ROOT_WH, 1),
	("خامات المواساة", acc("المخزن المركزي بالمواساة"), 0),
	("إصدارات الأطباء — المواساة", acc("المخزن المركزي بالمواساة"), 0),
	("خامات الأزاريطة", acc("المخزن المركزي بالمواساة"), 0),
	("إصدارات الأطباء — الأزاريطة", acc("المخزن المركزي بالمواساة"), 0),
]

# warehouse -> stock account it posts to - must match setup_coa.py.
WAREHOUSE_ACCOUNTS = {
	"خامات المواساة": "مخزون المواساة — الخامات",
	"إصدارات الأطباء — المواساة": "مخزون المواساة — إصدارات الأطباء",
	"خامات الأزاريطة": "مخزون الأزاريطة — الخامات",
	"إصدارات الأطباء — الأزاريطة": "مخزون الأزاريطة — إصدارات الأطباء",
}

UOMS = ["Nos", "رزمة", "كرتونة"]

# (code, is_stock_item, income account, extra UOM conversions)
ITEMS = [
	("A4-PAPER", 1, "إيراد مكتبة المواساة", {"رزمة": 500, "كرتونة": 2500}),
	("PRINT-SVC", 0, "إيراد مكتبة المواساة", {}),
	("BINDING-SVC", 0, "إيراد مكتبة المواساة", {}),
	("STUDIO-HOUR", 0, "إيراد X Studio", {}),
	("HALL-HOUR", 0, "إيراد القاعات", {}),
]

# (email, first name, roles, cost centers, warehouses) - must match setup_users.py.
# All of these users must be enabled, have exactly these roles and exactly these
# Company / Cost Center / Warehouse User Permissions.
BRANCH_ROLES = ["Branch Manager", "Sales User", "Accounts User"]
USERS = [
	("owner@imed.local", "المالك", ["System Manager", "Accounts Manager"], [], []),
	("nour@imed.local", "نور", BRANCH_ROLES, ["قاعات Imed"], []),
	("gilan@imed.local", "جيلان", BRANCH_ROLES, ["استوديو X"], []),
	("menna@imed.local", "منة", BRANCH_ROLES, ["تطبيق BA Plus"], []),
	(
		"raghad@imed.local",
		"رغد",
		[*BRANCH_ROLES, "Stock User"],
		["مكتبة المواساة"],
		["المخزن المركزي بالمواساة"],
	),
	(
		"sara@imed.local",
		"سارة",
		[*BRANCH_ROLES, "Stock User"],
		["مكتبة الأزاريطة"],
		["خامات الأزاريطة", "إصدارات الأطباء — الأزاريطة"],
	),
	("accountant@imed.local", "المحاسب", ["Accounts User", "Accounts Manager"], [], []),
	("hr@imed.local", "شؤون الموظفين", ["HR Manager"], [], []),
]
AUTOMATIC_ROLES = {"Administrator", "Guest", "All", "Desk User"}

counts = {}
problems = []


def report(category, label, errors):
	found, expected = counts.get(category, (0, 0))
	missing = errors == ["missing"]
	counts[category] = (found + (0 if missing else 1), expected + 1)
	if not errors:
		print(f"OK      {category:<12} {label}")
	elif missing:
		print(f"MISSING {category:<12} {label}")
		problems.append(f"{category} {label}: missing")
	else:
		print(f"WRONG   {category:<12} {label}: {'; '.join(errors)}")
		problems.append(f"{category} {label}: {'; '.join(errors)}")


def check_tree(doctype, category, parent_field, specs):
	for name, parent, is_group in specs:
		full = acc(name)
		row = frappe.db.get_value(doctype, full, [parent_field, "is_group", "company"], as_dict=True)
		if not row:
			report(category, full, ["missing"])
			continue
		errors = []
		if row[parent_field] != parent:
			errors.append(f"parent is {row[parent_field]}, expected {parent}")
		if row.is_group != is_group:
			errors.append("should be a group" if is_group else "is a group, must be a leaf")
		if row.company != COMPANY:
			errors.append(f"belongs to company {row.company}")
		report(category, full, errors)


def run():
	# ---------- Company ----------
	company = frappe.db.get_value("Company", COMPANY, ["abbr", "default_currency"], as_dict=True)
	if not company:
		print(f"STOP    Company '{COMPANY}' not found.")
		return
	errors = []
	if company.abbr != ABBR:
		errors.append(f"abbr is {company.abbr}, expected {ABBR}")
	if company.default_currency != CURRENCY:
		errors.append(f"currency is {company.default_currency}, expected {CURRENCY}")
	report("Company", COMPANY, errors)

	# ---------- Cost centers ----------
	check_tree("Cost Center", "Cost Center", "parent_cost_center", COST_CENTERS)

	# ---------- Accounts ----------
	for name, parent, account_type, is_group in ACCOUNTS:
		full = acc(name)
		row = frappe.db.get_value(
			"Account", full, ["parent_account", "account_type", "is_group", "company"], as_dict=True
		)
		if not row:
			report("Account", full, ["missing"])
			continue
		errors = []
		if row.parent_account != parent:
			errors.append(f"parent is {row.parent_account}, expected {parent}")
		if (row.account_type or "") != account_type:
			errors.append(f"type is '{row.account_type or ''}', expected '{account_type}'")
		if row.is_group != is_group:
			errors.append("should be a group" if is_group else "is a group, must be a ledger")
		if row.company != COMPANY:
			errors.append(f"belongs to company {row.company}")
		report("Account", full, errors)

	for name in REMOVED_ACCOUNTS:
		if frappe.db.exists("Account", acc(name)):
			report("Account", acc(name), ["should be deleted (replaced by per-library revenue)"])

	# ---------- Warehouses ----------
	check_tree("Warehouse", "Warehouse", "parent_warehouse", WAREHOUSES)
	for warehouse, account in WAREHOUSE_ACCOUNTS.items():
		current = frappe.db.get_value("Warehouse", acc(warehouse), "account")
		if current != acc(account):
			report("Stock link", acc(warehouse), [f"posts to {current}, expected {acc(account)}"])
		else:
			report("Stock link", acc(warehouse), [])

	# ---------- UOMs ----------
	for uom in UOMS:
		report("UOM", uom, [] if frappe.db.exists("UOM", uom) else ["missing"])

	# ---------- Items ----------
	for code, is_stock_item, income, conversions in ITEMS:
		if not frappe.db.exists("Item", code):
			report("Item", code, ["missing"])
			continue
		item = frappe.get_doc("Item", code)
		errors = []
		if item.is_stock_item != is_stock_item:
			errors.append("should be a stock item" if is_stock_item else "should be a non-stock service")
		default = next((d for d in item.item_defaults if d.company == COMPANY), None)
		if not default or default.income_account != acc(income):
			found = default.income_account if default else None
			errors.append(f"default income account is {found}, expected {acc(income)}")
		factors = {d.uom: d.conversion_factor for d in item.uoms}
		for uom, factor in conversions.items():
			if factors.get(uom) != factor:
				errors.append(f"{uom} conversion is {factors.get(uom)}, expected {factor}")
		report("Item", code, errors)

	# ---------- Users and User Permissions ----------
	for email, first_name, roles, cost_centers, warehouses in USERS:
		if not frappe.db.exists("User", email):
			report("User", email, ["missing"])
			continue
		errors = []
		user = frappe.db.get_value("User", email, ["enabled", "first_name"], as_dict=True)
		if not user.enabled:
			errors.append("disabled")
		if user.first_name != first_name:
			errors.append(f"first name is {user.first_name}, expected {first_name}")
		has_roles = set(frappe.get_roles(email)) - AUTOMATIC_ROLES
		missing_roles = [r for r in roles if r not in has_roles]
		if missing_roles:
			errors.append(f"missing roles {', '.join(missing_roles)}")
		extra_roles = sorted(has_roles - set(roles))
		if extra_roles:
			errors.append(f"unexpected roles {', '.join(extra_roles)}")
		expected = [("Cost Center", acc(c)) for c in cost_centers] + [("Warehouse", acc(w)) for w in warehouses]
		if expected:
			expected.append(("Company", COMPANY))
		actual = {
			(p.allow, p.for_value)
			for p in frappe.get_all(
				"User Permission",
				filters={"user": email, "allow": ["in", ["Company", "Cost Center", "Warehouse"]]},
				fields=["allow", "for_value"],
			)
		}
		for allow, value in expected:
			if (allow, value) not in actual:
				errors.append(f"no User Permission for {allow} {value}")
		for allow, value in sorted(actual - set(expected)):
			errors.append(f"unexpected User Permission for {allow} {value}")
		report("User", email, errors)

	# ---------- Leaf / group misuse ----------
	# Transactions can only post to leaf cost centers; flag any user default or ledger row on a group.
	for up in frappe.get_all("User Permission", filters={"allow": "Cost Center"}, fields=["user", "for_value"]):
		if frappe.db.get_value("Cost Center", up.for_value, "is_group"):
			problems.append(f"User Permission {up.user} -> group cost center {up.for_value}")
			print(f"WRONG   Permission   {up.user} is restricted to group cost center {up.for_value}")

	group_ccs = frappe.get_all("Cost Center", filters={"company": COMPANY, "is_group": 1}, pluck="name")
	if group_ccs:
		used = frappe.get_all(
			"GL Entry",
			filters={"company": COMPANY, "cost_center": ["in", group_ccs], "is_cancelled": 0},
			fields=["voucher_type", "voucher_no", "cost_center"],
			distinct=True,
		)
		for row in used:
			problems.append(f"{row.voucher_type} {row.voucher_no} posted to group cost center {row.cost_center}")
			print(f"WRONG   Ledger       {row.voucher_type} {row.voucher_no} posted to group {row.cost_center}")

	default_cc = frappe.db.get_value("Company", COMPANY, "cost_center")
	if default_cc and frappe.db.get_value("Cost Center", default_cc, "is_group"):
		problems.append(f"Company default cost center {default_cc} is a group")
		print(f"WRONG   Company      default cost center {default_cc} is a group")

	# See setup_users.py: strict mode locks branch managers out of Items and Warehouses.
	if frappe.db.get_single_value("System Settings", "apply_strict_user_permissions"):
		problems.append("System Settings: apply_strict_user_permissions is on")
		print("WRONG   Settings     apply_strict_user_permissions is on (branch managers cannot read Items)")

	# ---------- Summary ----------
	print()
	print(f"{'Category':<14}Found / Expected")
	print("-" * 32)
	for category, (found, expected) in counts.items():
		print(f"{category:<14}{found} / {expected}")
	print()
	if problems:
		print(f"{len(problems)} problem(s) found:")
		for p in problems:
			print(f"  - {p}")
	else:
		print("No problems found.")

	# Nothing was written; the commit is kept so every setup script ends the same way.
	frappe.db.commit()
	print(f"DONE    Verification finished for {COMPANY} ({ABBR}).")


run()
