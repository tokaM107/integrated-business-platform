# Allocation rules (EXP-03/04) for Mohamed Mamdouh group: how the shared premises' expenses are split.
#
# Run from bench console, after setup_coa.py:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_allocation_rules.py").read(), {"frappe": frappe})
#
# Submits the first rule, which makes the ERPNext Cost Center Allocation that splits every expense posted
# on the shared premises from Valid From on. Later changes are new rules made from the Allocation Rule
# screen with a later Valid From, never edits of this one, so past months keep their split.
#
# Idempotent: a submitted rule for the same cost center and date is left as is. Safe to run again.

import frappe

# Hardcoded on purpose: a demo company "Mohamed Mamdouh group (Demo)" also exists on the site.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"

SHARED = "مصروفات المقر المشتركة"
VALID_FROM = "2026-11-01"
# Agreed with the owner: 8 halls, 4 of which also serve as the studio part of the time.
SHARES = [("قاعات Imed", 60), ("استوديو X", 40)]
NOTES = "8 قاعات، منهم 4 بيشتغلوا استوديو جزء من الوقت. نسبة 60% قاعات / 40% استوديو متفق عليها مع المالك."


def acc(name):
	return f"{name} - {ABBR}"


def run():
	if not frappe.db.exists("Company", COMPANY):
		print(f"STOP   Company '{COMPANY}' not found. Run setup_core.py first.")
		return
	for name in [SHARED, *(business for business, _ in SHARES)]:
		if not frappe.db.exists("Cost Center", acc(name)):
			print(f"STOP   Cost Center {acc(name)} not found. Run setup_core.py first.")
			return

	label = f"{SHARED} from {VALID_FROM}"
	if name := frappe.db.exists(
		"Allocation Rule", {"main_cost_center": acc(SHARED), "valid_from": VALID_FROM, "docstatus": 1}
	):
		print(f"exists Allocation Rule {name} ({label})")
	else:
		rule = frappe.get_doc(
			{
				"doctype": "Allocation Rule",
				"main_cost_center": acc(SHARED),
				"valid_from": VALID_FROM,
				"notes": NOTES,
				"businesses": [{"cost_center": acc(business), "percentage": share} for business, share in SHARES],
			}
		).insert()
		rule.submit()
		shares = ", ".join(f"{business} {share}%" for business, share in SHARES)
		print(f"create Allocation Rule {rule.name} ({label}: {shares}) -> {rule.cost_center_allocation}")

	frappe.db.commit()
	print("DONE   Allocation rules finished.")


run()
