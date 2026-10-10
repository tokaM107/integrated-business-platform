# Read-only. Prints what each user can and cannot do, and checks it against the permissions matrix
# in section 3.2 of the requirements document.
#
# Run from bench console (after setup_users.py):
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/verify_users.py").read(), {"frappe": frappe})
#
# Users are read from the site (every user @imed.local), so there is no user list to keep in sync here.
# Matrix rows for modules that are not built yet (bookings, integrations, price approval) are listed as such.

import frappe

COMPANY = "Mohamed Mamdouh group"
EMAIL_DOMAIN = "imed.local"

# Matrix column of each user, by the requirement role they hold.
COLUMNS = ["Super Admin", "Accountant", "Branch Manager", "HR"]

# (matrix row, doctype, right, expected per column: Super Admin, Accountant, Branch Manager, HR)
CHECKS = [
	("Record revenue / a sale", "Sales Invoice", "create", (1, 1, 1, 0)),
	("Record an expense", "Expense", "create", (1, 1, 1, 0)),
	("Journal entry", "Journal Entry", "create", (1, 1, 1, 0)),
	("Submit a sale", "Sales Invoice", "submit", (1, 1, 1, 0)),
	("Cancel a financial transaction", "Sales Invoice", "cancel", (1, 1, 0, 0)),
	("Cancel a financial transaction", "Journal Entry", "cancel", (1, 1, 0, 0)),
	("Cancel a financial transaction", "Payment Entry", "cancel", (1, 1, 0, 0)),
	("Cancel a financial transaction", "Stock Entry", "cancel", (1, 1, 0, 0)),
	# Only the owner deletes, and only a draft; posted and cancelled documents never are (imederp/no_delete.py).
	("Delete a draft", "Sales Invoice", "delete", (1, 0, 0, 0)),
	("Delete a draft", "Expense", "delete", (1, 0, 0, 0)),
	("Delete a month closing", "Accounting Period", "delete", (1, 0, 0, 0)),
	("Delete the shared expenses split", "Cost Center Allocation", "delete", (1, 0, 0, 0)),
	("Close or reopen a month", "Accounting Period", "write", (1, 1, 0, 0)),
	("Change the chart of accounts", "Account", "create", (1, 1, 0, 0)),
	("Cancel the shared expenses split", "Cost Center Allocation", "cancel", (1, 1, 0, 0)),
	("Approve edition pricing", "Book Edition", "submit", (1, 1, 0, 0)),
	("Doctor settlements", "Doctor Ledger Entry", "submit", (1, 1, 0, 0)),
	("View employees", "Employee", "read", (1, 1, 0, 1)),
	("Manage employees", "Employee", "write", (1, 0, 0, 1)),
]
NOT_BUILT = [
	"Create / edit / cancel a booking (Studio / Halls modules)",
	"Integrations screen and re-sync",
	"Edit prices (Accountant: with approval) - approval flow",
]

problems = []


def column_of(roles):
	for column in COLUMNS:
		if column in roles:
			return column
	return None


def visible(doctype, user):
	"""Names of `doctype` records the user can list, after their User Permissions."""
	current = frappe.session.user
	try:
		frappe.set_user(user)
		return frappe.get_list(doctype, filters={"company": COMPANY}, pluck="name")
	except frappe.PermissionError:
		return None
	finally:
		frappe.set_user(current)


def run():
	users = frappe.get_all(
		"User", filters={"name": ["like", f"%@{EMAIL_DOMAIN}"], "enabled": 1}, pluck="name", order_by="creation"
	)
	if not users:
		print(f"STOP    No enabled users @{EMAIL_DOMAIN}; run setup_users.py first.")
		return

	all_ccs = frappe.get_all("Cost Center", filters={"company": COMPANY, "is_group": 0}, pluck="name")
	for user in users:
		roles = set(frappe.get_roles(user))
		column = column_of(roles)
		print()
		print(f"=== {user}  ({column or 'no matrix role'})")
		restrictions = frappe.get_all(
			"User Permission", filters={"user": user}, fields=["allow", "for_value"], order_by="allow"
		)
		print("    Restricted to: " + (", ".join(f"{r.allow} {r.for_value}" for r in restrictions) or "nothing (sees all)"))

		ccs = visible("Cost Center", user)
		if ccs is None:
			print("    Cost centers:  cannot read cost centers")
		else:
			leaves = [c for c in ccs if c in all_ccs]
			shown = "all" if set(all_ccs) <= set(leaves) else ", ".join(leaves) or "none"
			print(f"    Cost centers:  {shown}")
			# Matrix rows 1-2: a branch manager sees only their own activity, others see all.
			if column == "Branch Manager" and set(all_ccs) <= set(leaves):
				problems.append(f"{user}: branch manager can see every cost center")
			if column in ("Super Admin", "Accountant") and not set(all_ccs) <= set(leaves):
				problems.append(f"{user}: should see every cost center, sees {shown}")

		for row, doctype, right, expected in CHECKS:
			can = bool(frappe.has_permission(doctype, right, user=user))
			if column is None:
				mark = ""
			else:
				want = bool(expected[COLUMNS.index(column)])
				mark = "PASS" if can == want else "FAIL"
				if mark == "FAIL":
					problems.append(f"{user}: {row} ({doctype} {right}) is {'allowed' if can else 'denied'}, matrix says {'allowed' if want else 'denied'}")
			print(f"    {'yes' if can else 'no ':<4}{mark:<5}{row:<34}{doctype} {right}")

	print()
	print("Not built yet, so not checked: " + "; ".join(NOT_BUILT))
	print()
	if problems:
		print(f"{len(problems)} problem(s) found:")
		for p in problems:
			print(f"  - {p}")
	else:
		print("No problems found: every user matches the permissions matrix.")
	print("DONE    User verification finished. Nothing was changed.")


run()
