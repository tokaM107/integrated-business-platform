# The accountant's account alone (the owner, 9 Nov 2026), without running the whole of setup_users.py on a site whose
# other users are already set: accountant@imed.local with the roles setup_users.py gives it (keep the two the same).
# No password here: set it apart, in the site's terminal, and share it privately:
#   bench --site frontend execute imed_erp.setup.setup_accountant.run
#   bench --site frontend set-password accountant@imed.local
# Idempotent: a second run changes nothing. The account lands on شاشة المحاسب (page imed-accountant) and its sidebar
# shows the money only (imed_desk_fixes.js); what it may open is its roles' (setup_users.py, the permissions matrix).
import frappe

EMAIL = "accountant@imed.local"
NAME = "المحاسب"
ROLES = ["Accountant", "Accounts User", "Accounts Manager", "Expense Approver"]
CUSTOM = {"Accountant", "Expense Approver"}


def run():
	for role in CUSTOM:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
			print(f"create Role {role}")
	if not frappe.db.exists("User", EMAIL):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": EMAIL,
				"first_name": NAME,
				"language": "ar",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in ROLES],
			}
		).insert(ignore_permissions=True)
		print(f"create User {EMAIL}: now set its password: bench --site <site> set-password {EMAIL}")
	else:
		user = frappe.get_doc("User", EMAIL)
		missing = [r for r in ROLES if r not in [d.role for d in user.roles]]
		if missing or not user.enabled:
			user.enabled = 1
			for role in missing:
				user.append("roles", {"role": role})
			user.save(ignore_permissions=True)
			print(f"update User {EMAIL}: roles {', '.join(missing) or '-'}; enabled")
		else:
			print(f"exists User {EMAIL}")
	frappe.db.commit()
