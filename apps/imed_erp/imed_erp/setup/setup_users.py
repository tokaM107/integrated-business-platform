# Users, roles and User Permissions for Mohamed Mamdouh group.
#
# Run from bench console (after setup_master.py):
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_users.py").read(), {"frappe": frappe})
#
# Idempotent: existing users are kept (password untouched); only missing roles and
# missing User Permissions are added.

import frappe

# Hardcoded on purpose: a demo company "Mohamed Mamdouh group (Demo)" also exists on the site.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"

# Temporary password for newly created users only. Change it after first login,
# and never reuse it on a server reachable from the internet.
TEMP_PASSWORD = "Imed#Temp-2026"

# "Branch Manager" is a custom marker role. It grants nothing by itself, so branch managers
# also get the standard ERPNext roles they need to work; User Permissions below limit what they see.
BRANCH_ROLES = ["Branch Manager", "Sales User", "Accounts User"]
LIBRARY_ROLES = [*BRANCH_ROLES, "Stock User"]

# Each branch manager is restricted to the company plus their own cost center / warehouse.
# Raghad's "Central Store Mawasah" is a group warehouse: the permission also covers its
# children (Store Mawasah and Store Azarita) so she can transfer stock to Azarita.
USERS = [
	{"first_name": "Owner", "roles": ["System Manager", "Accounts Manager"]},
	{"first_name": "Nour", "roles": BRANCH_ROLES, "cost_centers": ["Imed Halls"]},
	{"first_name": "Gilan", "roles": BRANCH_ROLES, "cost_centers": ["X Studio"]},
	{"first_name": "Menna", "roles": BRANCH_ROLES, "cost_centers": ["BA Plus App"]},
	{
		"first_name": "Raghad",
		"roles": LIBRARY_ROLES,
		"cost_centers": ["2Be Doctor Mawasah"],
		"warehouses": ["Central Store Mawasah"],
	},
	{
		"first_name": "Sara",
		"roles": LIBRARY_ROLES,
		"cost_centers": ["2Be Doctor Azarita"],
		"warehouses": ["Store Azarita"],
	},
	{"first_name": "Accountant", "roles": ["Accounts User", "Accounts Manager"]},
	{"first_name": "HR", "roles": ["HR Manager"]},
]


def email_of(first_name):
	return f"{first_name.lower()}@imed.local"


def ensure_role(role):
	if frappe.db.exists("Role", role):
		print(f"exists Role {role}")
		return True
	frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()
	print(f"create Role {role}")
	return True


def ensure_user(spec):
	email = email_of(spec["first_name"])
	roles = [r for r in spec["roles"] if frappe.db.exists("Role", r)]
	for r in set(spec["roles"]) - set(roles):
		print(f"SKIP   Role {r} for {email}: role does not exist on this site")

	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		missing = [r for r in roles if r not in {d.role for d in user.roles}]
		if missing:
			user.add_roles(*missing)
			print(f"update User {email}: added roles {', '.join(missing)}")
		else:
			print(f"exists User {email}")
		return email

	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": spec["first_name"],
			"user_type": "System User",
			"send_welcome_email": 0,
			"new_password": TEMP_PASSWORD,
			"roles": [{"role": r} for r in roles],
		}
	).insert()
	print(f"create User {email}")
	return email


def ensure_user_permission(user, allow, value, is_default):
	if not frappe.db.exists(allow, value):
		print(f"SKIP   User Permission {user} -> {allow} {value}: not found")
		return False
	if frappe.db.exists("User Permission", {"user": user, "allow": allow, "for_value": value}):
		print(f"exists User Permission {user} -> {allow} {value}")
		return True
	# Only one default per user and doctype is allowed.
	if is_default and frappe.db.exists("User Permission", {"user": user, "allow": allow, "is_default": 1}):
		is_default = 0
	frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": allow,
			"for_value": value,
			"apply_to_all_doctypes": 1,
			"is_default": is_default,
		}
	).insert()
	print(f"create User Permission {user} -> {allow} {value}")
	return True


def run():
	# Safety check: stop if the company is missing or its abbreviation differs.
	if frappe.db.get_value("Company", COMPANY, "abbr") != ABBR:
		print(f"STOP   Company '{COMPANY}' with abbr '{ABBR}' not found. Nothing was changed.")
		return

	# ---------- 1) Roles ----------
	ensure_role("Branch Manager")

	# ---------- 2) Users ----------
	summary = []
	for spec in USERS:
		email = ensure_user(spec)
		restrictions = []

		# ---------- 3) User Permissions (branch managers only) ----------
		cost_centers = [f"{c} - {ABBR}" for c in spec.get("cost_centers", [])]
		warehouses = [f"{w} - {ABBR}" for w in spec.get("warehouses", [])]
		if cost_centers or warehouses:
			# Pin to the real company so the demo company stays hidden.
			if ensure_user_permission(email, "Company", COMPANY, 1):
				restrictions.append(f"Company: {COMPANY}")
			for cc in cost_centers:
				if frappe.db.get_value("Cost Center", cc, "is_group"):
					print(f"WARN   {cc} is a group cost center; it cannot be used in transactions")
				if ensure_user_permission(email, "Cost Center", cc, int(len(cost_centers) == 1)):
					restrictions.append(f"Cost Center: {cc}")
			for wh in warehouses:
				if ensure_user_permission(email, "Warehouse", wh, int(len(warehouses) == 1)):
					restrictions.append(f"Warehouse: {wh}")

		summary.append((email, ", ".join(spec["roles"]), restrictions or ["none (full access by role)"]))

	# ---------- 4) Strict user permissions ----------
	# Without this, documents with an empty cost center / warehouse stay visible to restricted users.
	# It only affects users who have User Permissions (the branch managers).
	if not frappe.db.get_single_value("System Settings", "apply_strict_user_permissions"):
		frappe.db.set_single_value("System Settings", "apply_strict_user_permissions", 1)
		print("update System Settings: apply_strict_user_permissions = 1")
	else:
		print("exists System Settings: apply_strict_user_permissions = 1")

	frappe.db.commit()

	# ---------- 5) Summary ----------
	print()
	print(f"{'User':<24}{'Roles':<56}Restrictions")
	print("-" * 124)
	for email, roles, restrictions in summary:
		print(f"{email:<24}{roles:<56}{restrictions[0]}")
		for extra in restrictions[1:]:
			print(f"{'':<80}{extra}")
	print()
	print(f"DONE   User setup finished for {COMPANY}. New users' temporary password: {TEMP_PASSWORD}")


run()
