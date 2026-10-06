# Recurring monthly expenses (EXP-05) for Mohamed Mamdouh group: the first rows of the Recurring Expense list.
#
# Run from bench console, after setup_coa.py and setup_expenses.py:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_recurring_expenses.py").read(), {"frappe": frappe})
#
# This only fills the list once. From then on the owner and the accountant keep it themselves from the
# Recurring Expense list: change an amount or a day, add a bill, or disable one that stopped.
#
# Idempotent: a bill already in the list for the same business is left as is, even if its amount was
# changed since. Safe to run again.

import frappe

# Hardcoded on purpose: a demo company "Mohamed Mamdouh group (Demo)" also exists on the site.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"

# The day of the month the bills are due. Not known yet; each bill's day can be changed from its own record.
DAY_OF_MONTH = 1

# (expense category, expected monthly amount or None, business, treasury)
# The center's premises (Imed Center and X Studio) share their bills; they are paid from the main treasury
# and allocated to the businesses later. With an amount, each month's draft is made automatically.
# Each library and the app pay their own bills from their own treasury. Their amounts are not known, so
# the accountant enters them himself, picking the bill on the Expense screen; set an amount on a bill from
# the list to have its drafts made too.
RECURRING = [
	("الإيجار", 46000, "مصروفات المقر المشتركة", "الخزينة الرئيسية"),
	("الكهرباء", 10000, "مصروفات المقر المشتركة", "الخزينة الرئيسية"),
	("الإنترنت", 3500, "مصروفات المقر المشتركة", "الخزينة الرئيسية"),
	("الغاز", 300, "مصروفات المقر المشتركة", "الخزينة الرئيسية"),
	*[
		(bill, None, library, f"خزينة {library}")
		for library in ("مكتبة الأزاريطة", "مكتبة المواساة")
		for bill in ("الإيجار", "الكهرباء", "الإنترنت")
	],
	("السيرفر", None, "تطبيق BA Plus", "خزينة تطبيق BA Plus"),
	("اشتراكات الذكاء الاصطناعي", None, "تطبيق BA Plus", "خزينة تطبيق BA Plus"),
]


def acc(name):
	return f"{name} - {ABBR}"


def make_recurring(category, amount, business, treasury):
	label = f"{category} / {business}"
	if name := frappe.db.exists("Recurring Expense", {"expense_category": category, "activity": acc(business)}):
		print(f"exists Recurring Expense {name} ({label})")
		return
	for doctype, link in (("Expense Category", category), ("Cost Center", acc(business)), ("Account", acc(treasury))):
		if not frappe.db.exists(doctype, link):
			print(f"SKIP   {label}: {doctype} {link} not found")
			return

	recurring = frappe.get_doc(
		{
			"doctype": "Recurring Expense",
			"activity": acc(business),
			"expense_category": category,
			"treasury": acc(treasury),
			"amount": amount,
			"day_of_month": DAY_OF_MONTH,
			# Copied into every month's draft, where it tells whoever opens it what to do.
			"description": amount
			and f"مصروف شهري: {category}. المبلغ متوقع؛ عدّله حسب الفاتورة الفعلية وارفع إيصال الشهر قبل الاعتماد.",
		}
	).insert()
	expected = f"{amount:,} EGP" if amount else "no amount"
	print(f"create Recurring Expense {recurring.name} ({label}, {expected}, first on {recurring.next_date})")


def run():
	if not frappe.db.exists("Company", COMPANY):
		print(f"STOP   Company '{COMPANY}' not found. Run setup_core.py first.")
		return

	for category, amount, business, treasury in RECURRING:
		make_recurring(category, amount, business, treasury)

	frappe.db.commit()
	print("DONE   Recurring expenses finished.")


run()
