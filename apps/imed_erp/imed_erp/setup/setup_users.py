# Users, roles and User Permissions for Mohamed Mamdouh group.
#
# Run from bench console (after setup_master.py):
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_users.py").read(), {"frappe": frappe})
#
# Idempotent and declarative: USERS below is the source of truth for these users. Each run creates
# what is missing and brings existing users back in line with it (name, enabled flag, roles, and
# User Permissions on Company / Cost Center / Warehouse). Running it twice changes nothing the second time.
# Passwords of existing users are never touched.
#
# No password is stored in this file. New users get:
#   - the value of the environment variable IMED_INITIAL_PASSWORD, if set, or
#   - a random password each, printed once at the end of the run.
# Either way, users should change it at first login.

import os
import secrets

import frappe

# Hardcoded on purpose: a demo company "Mohamed Mamdouh group (Demo)" also exists on the site.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
EMAIL_DOMAIN = "imed.local"

# "Branch Manager" is a custom marker role. It grants nothing by itself, so branch managers
# also get the standard ERPNext roles they need to work; User Permissions below limit what they see.
BRANCH_ROLES = ["Branch Manager", "Sales User", "Accounts User"]
LIBRARY_ROLES = [*BRANCH_ROLES, "Stock User"]
CUSTOM_ROLES = ["Branch Manager"]

# Each branch manager is restricted to the company plus their own cost center / warehouse.
# Users without cost_centers / warehouses get no User Permissions: their roles alone decide access.
# Raghad's "Central Store Mawasah" is a group warehouse: the permission also covers its
# children (Store Mawasah and Store Azarita) so she can transfer stock to Azarita.
# "enabled" defaults to 1.
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

# User Permission doctypes this script owns for the users above. Rows on other doctypes are left alone.
MANAGED_ALLOW = ["Company", "Cost Center", "Warehouse"]

# Roles Frappe gives every user implicitly; they never appear in USERS and are never removed.
AUTOMATIC_ROLES = {"Administrator", "Guest", "All", "Desk User"}

INITIAL_PASSWORD = os.environ.get("IMED_INITIAL_PASSWORD")


def email_of(spec):
	return f"{spec['first_name'].lower()}@{EMAIL_DOMAIN}"


def desired_permissions(spec):
	"""(allow, value, is_default) rows the user must have; empty for unrestricted users."""
	rows = [("Cost Center", f"{c} - {ABBR}") for c in spec.get("cost_centers", [])]
	rows += [("Warehouse", f"{w} - {ABBR}") for w in spec.get("warehouses", [])]
	if not rows:
		return []
	# Pin to the real company so the demo company stays hidden.
	rows.insert(0, ("Company", COMPANY))
	# A value is the user's default only when it is their single value for that doctype.
	per_allow = {allow: sum(a == allow for a, _ in rows) for allow, _ in rows}
	return [(allow, value, int(per_allow[allow] == 1)) for allow, value in rows]


def preflight():
	"""Check everything the users depend on before writing anything. Returns a list of problems."""
	problems = []
	if frappe.db.get_value("Company", COMPANY, "abbr") != ABBR:
		return [f"Company '{COMPANY}' with abbr '{ABBR}' not found"]
	for spec in USERS:
		for role in spec["roles"]:
			if role not in CUSTOM_ROLES and not frappe.db.exists("Role", role):
				problems.append(f"Role {role} (for {email_of(spec)}) does not exist on this site")
		for allow, value, _ in desired_permissions(spec):
			if not frappe.db.exists(allow, value):
				problems.append(f"{allow} {value} (for {email_of(spec)}) not found; run setup_master.py first")
			elif allow == "Cost Center" and frappe.db.get_value("Cost Center", value, "is_group"):
				print(f"WARN   {value} is a group cost center; it cannot be used in transactions")
	return problems


def ensure_role(role):
	if frappe.db.exists("Role", role):
		if not frappe.db.get_value("Role", role, "desk_access"):
			frappe.db.set_value("Role", role, "desk_access", 1)
			print(f"update Role {role}: desk_access = 1")
		else:
			print(f"exists Role {role}")
		return
	frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()
	print(f"create Role {role}")


def ensure_user(spec, new_passwords):
	email = email_of(spec)
	enabled = spec.get("enabled", 1)

	if not frappe.db.exists("User", email):
		password = INITIAL_PASSWORD or secrets.token_urlsafe(12)
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": spec["first_name"],
				"enabled": enabled,
				"user_type": "System User",
				"send_welcome_email": 0,
				"new_password": password,
				"roles": [{"role": r} for r in spec["roles"]],
			}
		).insert()
		new_passwords[email] = None if INITIAL_PASSWORD else password
		print(f"create User {email}")
		return email

	user = frappe.get_doc("User", email)
	changes = []
	if user.first_name != spec["first_name"]:
		user.first_name = spec["first_name"]
		changes.append(f"first_name = {spec['first_name']}")
	if user.enabled != enabled:
		user.enabled = enabled
		changes.append(f"enabled = {enabled}")

	current = [d.role for d in user.roles]
	missing = [r for r in spec["roles"] if r not in current]
	extra = [r for r in current if r not in spec["roles"] and r not in AUTOMATIC_ROLES]
	for role in missing:
		user.append("roles", {"role": role})
	if extra:
		user.set("roles", [d for d in user.roles if d.role not in extra])
	if missing:
		changes.append(f"added roles {', '.join(missing)}")
	if extra:
		changes.append(f"removed roles {', '.join(extra)}")

	if changes:
		user.save()
		print(f"update User {email}: {'; '.join(changes)}")
	else:
		print(f"exists User {email}")
	return email


def sync_user_permissions(user, desired):
	"""Make the user's Company / Cost Center / Warehouse permissions exactly match `desired`."""
	existing = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": ["in", MANAGED_ALLOW]},
		fields=["name", "allow", "for_value", "is_default", "apply_to_all_doctypes", "hide_descendants"],
		order_by="creation asc",
	)
	wanted = {(allow, value): is_default for allow, value, is_default in desired}

	# 1) Delete rows that are no longer wanted, and duplicates of wanted ones.
	kept = {}
	for row in existing:
		key = (row.allow, row.for_value)
		if key in wanted and key not in kept:
			kept[key] = row
			continue
		frappe.delete_doc("User Permission", row.name, ignore_permissions=True)
		print(f"remove User Permission {user} -> {row.allow} {row.for_value}")

	# 2) Fix flags on kept rows. Clearing defaults first avoids a transient "two defaults" error.
	for key, row in sorted(kept.items(), key=lambda kv: wanted[kv[0]]):
		target = {"is_default": wanted[key], "apply_to_all_doctypes": 1, "hide_descendants": 0}
		diff = {f: v for f, v in target.items() if row[f] != v}
		if diff:
			doc = frappe.get_doc("User Permission", row.name)
			doc.update(diff)
			doc.save(ignore_permissions=True)
			print(f"update User Permission {user} -> {key[0]} {key[1]}: {diff}")
		else:
			print(f"exists User Permission {user} -> {key[0]} {key[1]}")

	# 3) Create missing rows.
	for (allow, value), is_default in wanted.items():
		if (allow, value) in kept:
			continue
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": allow,
				"for_value": value,
				"apply_to_all_doctypes": 1,
				"is_default": is_default,
			}
		).insert(ignore_permissions=True)
		print(f"create User Permission {user} -> {allow} {value}")


def run():
	# Safety check: stop before writing anything if the company, a role, a cost center or a
	# warehouse is missing. Otherwise a user could be created with roles but without restrictions.
	problems = preflight()
	if problems:
		for p in problems:
			print(f"STOP   {p}")
		print("STOP   Nothing was changed.")
		return

	try:
		# ---------- 1) Roles ----------
		for role in CUSTOM_ROLES:
			ensure_role(role)

		# ---------- 2) Users and 3) User Permissions ----------
		summary = []
		new_passwords = {}
		for spec in USERS:
			email = ensure_user(spec, new_passwords)
			desired = desired_permissions(spec)
			sync_user_permissions(email, desired)
			restrictions = [f"{allow}: {value}" for allow, value, _ in desired]
			summary.append(
				(
					email,
					spec.get("enabled", 1),
					", ".join(spec["roles"]),
					restrictions or ["none (full access by role)"],
				)
			)

		# ---------- 4) Strict user permissions: OFF ----------
		# Strict mode hides every record that has an EMPTY Cost Center / Warehouse / Company link.
		# Tested on ERPNext v16: with it on, branch managers cannot read any Item, and Raghad / Sara
		# cannot read any Warehouse (Warehouse.default_in_transit_warehouse is empty). With it off,
		# records whose link points to another cost center / warehouse are still hidden; only
		# records with the link left empty stay visible.
		if frappe.db.get_single_value("System Settings", "apply_strict_user_permissions"):
			frappe.db.set_single_value("System Settings", "apply_strict_user_permissions", 0)
			print("update System Settings: apply_strict_user_permissions = 0")
		else:
			print("exists System Settings: apply_strict_user_permissions = 0")

		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		print("FAILED Rolled back; nothing was changed.")
		raise

	# ---------- 5) Summary ----------
	print()
	print(f"{'User':<24}{'On':<4}{'Roles':<56}Restrictions")
	print("-" * 128)
	for email, enabled, roles, restrictions in summary:
		print(f"{email:<24}{'yes' if enabled else 'no':<4}{roles:<56}{restrictions[0]}")
		for extra in restrictions[1:]:
			print(f"{'':<84}{extra}")
	print()
	if new_passwords:
		print("New users (share each password privately; change it at first login):")
		for email, password in new_passwords.items():
			print(f"  {email:<24}{password or '(IMED_INITIAL_PASSWORD)'}")
	print(f"DONE   User setup finished for {COMPANY}.")


run()
