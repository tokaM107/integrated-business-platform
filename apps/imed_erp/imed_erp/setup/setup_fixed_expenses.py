# The group's fixed monthly bills as the owner gave them (12 Nov 2026), as Recurring Expenses: the owner's page
# compares each month's income with them (imederp/owner_cover.py), and each bill reminds the owner and the
# accountant on its day and leaves them a draft Expense to complete (recurring_expense.py).
#
#   bench --site frontend execute imed_erp.setup.setup_fixed_expenses.run
#
# Idempotent: a bill already listed (the same category for the same business) keeps its amount when it has one,
# so what the owner or the accountant set is never overwritten; one listed without an amount (setup_recurring_
# expenses.py left the libraries' rents empty) takes the owner's figure. Every amount and day can be changed
# afterwards from Recurring Expenses. The days of the month are the 1st until someone sets the real ones.
import frappe

COMPANY = "Mohamed Mamdouh group"
MAIN, SHARED = "الإدارة الرئيسية", "مصروفات المقر المشتركة"
AZARITA, MAWASAH = "مكتبة الأزاريطة", "مكتبة المواساة"

# (category, business, treasury, monthly amount, what it is). The centre's bills go on the shared premises, which
# the allocation rule splits between the halls and the studio (setup_allocation_rules.py).
BILLS = [
	("الرواتب والأجور", MAIN, "الخزينة الرئيسية", 70000, "مرتبات الموظفين"),
	("الإيجار", SHARED, "الخزينة الرئيسية", 46000, "إيجار المكان اللي فيه السنتر والاستوديو"),
	("الإيجار", AZARITA, "خزينة مكتبة الأزاريطة", 15000, "إيجار مكتبة الأزاريطة"),
	("الكهرباء", SHARED, "الخزينة الرئيسية", 10000, "الكهربا"),
	("الإيجار", MAWASAH, "خزينة مكتبة المواساة", 7500, "إيجار مكتبة المواساة"),
	("الإنترنت", SHARED, "الخزينة الرئيسية", 3500, "النت"),
	# Water and gas about 1,000 together: gas is listed at 300 already (setup_recurring_expenses.py).
	("المياه", SHARED, "الخزينة الرئيسية", 700, "الماية (تقريبًا)"),
	("الغاز", SHARED, "الخزينة الرئيسية", 300, "الغاز (تقريبًا)"),
]


def run():
	abbr = frappe.get_cached_value("Company", COMPANY, "abbr")
	made = kept = 0
	for category, business, treasury, amount, what in BILLS:
		activity, box = f"{business} - {abbr}", f"{treasury} - {abbr}"
		missing = [n for n, d in ((category, "Expense Category"), (activity, "Cost Center"), (box, "Account")) if not frappe.db.exists(d, n)]
		if missing:
			print(f"SKIP   {what}: not on this site: {', '.join(missing)}")
			continue
		existing = frappe.db.get_value("Recurring Expense", {"expense_category": category, "activity": activity}, ["name", "amount"], as_dict=True)
		if existing and existing.amount:
			print(f"exists {existing.name}: {existing.amount} (left as it is)")
			kept += 1
			continue
		if existing:
			frappe.db.set_value("Recurring Expense", existing.name, "amount", amount)
			print(f"update {existing.name}: no amount -> {amount}")
			made += 1
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Recurring Expense",
				"activity": activity,
				"expense_category": category,
				"treasury": box,
				"amount": amount,
				"day_of_month": 1,
				"enabled": 1,
				"description": what,
			}
		)
		doc.insert(ignore_permissions=True)
		print(f"create {doc.name}: {amount}")
		made += 1
	if not frappe.flags.in_test:
		frappe.db.commit()
	total = sum(b[3] for b in BILLS)
	print(f"DONE   {made} made or filled in, {kept} already set. The bills given come to {total:,} a month.")
