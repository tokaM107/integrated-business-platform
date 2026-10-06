# Expense categories (EXP-07) for Mohamed Mamdouh group: the tree the Expense screen and the
# Expense Report group by.
#
# Run from bench console, after setup_coa.py:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_expenses.py").read(), {"frappe": frappe})
#
# Each category is posted to an expense account the chart of accounts already has (section 2 of the posting
# rules). This script creates no account: a missing one is printed as WAIT, and the category is made without
# an account until it exists. Accounts are looked up by their Arabic name, then by the English name ERPNext
# ships them with, so it works before and after setup_arabic_names.py.
#
# Idempotent: existing categories are kept; only a missing account link is filled in. Safe to run again.

import frappe

# Hardcoded on purpose: a demo company "Mohamed Mamdouh group (Demo)" also exists on the site.
COMPANY = "Mohamed Mamdouh group"

ROOT = "كل المصروفات"

# (category, Arabic account name, English account name). Add sub-categories under these in the tree;
# a sub-category without its own account is posted to its parent's.
CATEGORIES = [
	("الإيجار", "الإيجار", "Office Rent"),
	("المرافق", "المرافق", "Utility Expenses"),
	("الرواتب والأجور", "الرواتب والأجور", "Salary"),
	("الخامات والمستهلكات", "الخامات والمستهلكات", "Raw Materials and Consumables"),
	("الصيانة", "الصيانة", "Office Maintenance Expenses"),
	("التسويق", "التسويق", "Marketing Expenses"),
	("الهالك والتالف", "الهالك والتالف", "Wastage and Scrap"),
	("الاشتراكات والسيرفرات", "الاشتراكات والسيرفرات", "الاشتراكات والسيرفرات"),
]


# Monthly premises bills sit under utilities so the report shows each bill and their total. The bills have
# no account of their own, so they post to the utilities account. Rent sits with them but keeps its own
# account, so the profit and loss still shows rent on its own line.
UTILITIES = "المرافق"
UTILITY_BILLS = ["الكهرباء", "المياه", "الإنترنت", "الغاز"]
MOVED_UNDER_UTILITIES = ["الإيجار"]

# The app's monthly bills, the same way: each shown on its own, all posted to the subscriptions account.
SUBSCRIPTIONS = "الاشتراكات والسيرفرات"
SUBSCRIPTION_BILLS = ["السيرفر", "اشتراكات الذكاء الاصطناعي"]


def find_account(*names):
	for name in names:
		account = frappe.db.get_value(
			"Account", {"account_name": name, "company": COMPANY, "is_group": 0, "root_type": "Expense"}
		)
		if account:
			return account
	return None


def make_category(name, parent=None, is_group=0, expense_account=None):
	if frappe.db.exists("Expense Category", name):
		current = frappe.db.get_value("Expense Category", name, "expense_account")
		if expense_account and not current:
			frappe.db.set_value("Expense Category", name, "expense_account", expense_account)
			print(f"link   Expense Category {name} -> {expense_account}")
		elif expense_account and current != expense_account:
			print(f"WARN   Expense Category {name}: posts to {current}, expected {expense_account} (not changed)")
		else:
			print(f"exists Expense Category {name}")
		return
	frappe.get_doc(
		{
			"doctype": "Expense Category",
			"expense_category_name": name,
			"parent_expense_category": parent,
			"is_group": is_group,
			"expense_account": expense_account,
		}
	).insert()
	print(f"create Expense Category {name}" + (f" -> {expense_account}" if expense_account else ""))


def ensure_group(name):
	"""Turn a leaf category into a group; refused once expenses are recorded on it."""
	if frappe.db.get_value("Expense Category", name, "is_group"):
		return True
	if frappe.db.exists("Expense", {"expense_category": name}):
		print(f"WARN   Expense Category {name}: has expenses, cannot become a group (not changed)")
		return False
	doc = frappe.get_doc("Expense Category", name)
	doc.is_group = 1
	doc.save()
	print(f"update Expense Category {name}: now a group")
	return True


def ensure_parent(name, parent):
	if not frappe.db.exists("Expense Category", name):
		return
	if frappe.db.get_value("Expense Category", name, "parent_expense_category") == parent:
		print(f"exists Expense Category {name} under {parent}")
		return
	doc = frappe.get_doc("Expense Category", name)
	doc.parent_expense_category = parent
	doc.save()
	print(f"move   Expense Category {name} -> under {parent}")


def run():
	if not frappe.db.exists("Company", COMPANY):
		print(f"STOP   Company '{COMPANY}' not found. Run setup_core.py first.")
		return

	make_category(ROOT, is_group=1)
	for name, arabic, english in CATEGORIES:
		account = find_account(arabic, english)
		if not account:
			print(f"WAIT   Account {arabic} / {english} not found for {COMPANY} (setup_coa.py makes it)")
		make_category(name, ROOT, expense_account=account)

	if ensure_group(UTILITIES):
		for bill in UTILITY_BILLS:
			make_category(bill, UTILITIES)
		for name in MOVED_UNDER_UTILITIES:
			ensure_parent(name, UTILITIES)

	if ensure_group(SUBSCRIPTIONS):
		for bill in SUBSCRIPTION_BILLS:
			make_category(bill, SUBSCRIPTIONS)

	frappe.db.commit()
	print("DONE   Expense categories finished.")


run()
