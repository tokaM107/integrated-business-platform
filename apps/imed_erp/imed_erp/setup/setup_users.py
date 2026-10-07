# Users, roles, User Permissions and the permissions matrix (requirements section 3.2) for
# Mohamed Mamdouh group.
#
# Run from bench console (after setup_core.py):
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

# The roles of the requirements document (sections 3.1 / 3.2) are custom roles with the same names.
# Each user also gets the standard ERPNext roles they need to work; User Permissions below limit what
# branch managers see. "Super Admin" and "Accountant" also carry the full rights on financial documents
# (see FINANCIAL_DOCTYPES). "CRM Staff" has no user yet: nobody is named for it in the requirements.
BRANCH_ROLES = ["Branch Manager", "Sales User", "Accounts User"]
LIBRARY_ROLES = [*BRANCH_ROLES, "Stock User"]
# "Expense Approver" approves expenses above the threshold in Expense Settings; only the owner has it.
CUSTOM_ROLES = ["Super Admin", "Accountant", "Branch Manager", "HR", "CRM Staff", "Expense Approver"]

# Permissions matrix, section 3.2: "only the owner and the accountant can edit, cancel or delete a
# financial transaction". Branch managers keep create / edit draft / submit, but lose cancel, amend
# and delete on these documents; Super Admin and Accountant get every right on them.
FINANCIAL_DOCTYPES = [
	"Sales Invoice",
	"POS Invoice",
	"Purchase Invoice",
	"Payment Entry",
	"Journal Entry",
	"Stock Entry",
	"Delivery Note",
	"Purchase Receipt",
	"Stock Reconciliation",
]
MANAGER_STANDARD_ROLES = ["Accounts User", "Sales User", "Stock User"]
MANAGER_DENIED = {"cancel": 0, "amend": 0, "delete": 0}
FULL_RIGHTS = {
	p: 1
	for p in ("read", "write", "create", "submit", "cancel", "amend", "delete", "report", "print", "email", "export", "share")
}

# Each branch manager is restricted to the company plus their own cost center / warehouse.
# Users without cost_centers / warehouses get no User Permissions: their roles alone decide access.
# A permission on a group warehouse also covers the warehouses under it.
# Raghad keeps the main warehouse (Mawasah, with its damaged stock) and also gets Azarita's, because
# she supplies the branch: a transfer names both warehouses and is refused if either is not hers.
# Sara gets Azarita only, so the server refuses any document, report row or API call that touches
# Mawasah (or the center's office supplies) for her.
# "enabled" defaults to 1.
USERS = [
	{"email": "owner", "first_name": "المالك", "roles": ["Super Admin", "System Manager", "Accounts Manager", "Expense Approver"]},
	{"email": "nour", "first_name": "نور", "roles": BRANCH_ROLES, "cost_centers": ["قاعات Imed"]},
	{"email": "gilan", "first_name": "جيلان", "roles": BRANCH_ROLES, "cost_centers": ["استوديو X"]},
	{"email": "menna", "first_name": "منة", "roles": BRANCH_ROLES, "cost_centers": ["تطبيق BA Plus"]},
	{
		"email": "raghad",
		"first_name": "رغد",
		"roles": LIBRARY_ROLES,
		"cost_centers": ["مكتبة المواساة"],
		"warehouses": ["المخزن المركزي بالمواساة", "مخزن الأزاريطة"],
	},
	{
		"email": "sara",
		"first_name": "سارة",
		"roles": LIBRARY_ROLES,
		"cost_centers": ["مكتبة الأزاريطة"],
		"warehouses": ["مخزن الأزاريطة"],
	},
	{"email": "accountant", "first_name": "المحاسب", "roles": ["Accountant", "Accounts User", "Accounts Manager"]},
	{"email": "hr", "first_name": "شؤون الموظفين", "roles": ["HR", "HR Manager"]},
]

# User Permission doctypes this script owns for the users above. Rows on other doctypes are left alone.
MANAGED_ALLOW = ["Company", "Cost Center", "Warehouse"]

# Roles Frappe gives every user implicitly; they never appear in USERS and are never removed.
AUTOMATIC_ROLES = {"Administrator", "Guest", "All", "Desk User"}

INITIAL_PASSWORD = os.environ.get("IMED_INITIAL_PASSWORD")


def email_of(spec):
	# Names are Arabic, so the address comes from its own English key, not from the name.
	return f"{spec['email']}@{EMAIL_DOMAIN}"


def desired_permissions(spec):
	"""(allow, value, is_default) rows the user must have; empty for unrestricted users."""
	rows = [("Cost Center", f"{c} - {ABBR}") for c in spec.get("cost_centers", [])]
	rows += [("Warehouse", f"{w} - {ABBR}") for w in spec.get("warehouses", [])]
	if not rows:
		return []
	# Pin to the real company so the demo company stays hidden.
	rows.insert(0, ("Company", COMPANY))
	# A value is the user's default only when it is their single value for that doctype, and never a
	# group warehouse: forms would fill it in and stock transactions refuse group warehouses.
	per_allow = {allow: sum(a == allow for a, _ in rows) for allow, _ in rows}

	def is_default(allow, value):
		if allow == "Warehouse" and frappe.db.get_value("Warehouse", value, "is_group"):
			return 0
		return int(per_allow[allow] == 1)

	return [(allow, value, is_default(allow, value)) for allow, value in rows]


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
				problems.append(f"{allow} {value} (for {email_of(spec)}) not found; run setup_core.py first")
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


def ensure_docperm(doctype, role, rights, create):
	"""Make the role's level-0 rule on `doctype` have `rights`. Creates the rule only if `create`."""
	from frappe.permissions import add_permission, setup_custom_perms

	# The first custom rule copies the doctype's standard rules, so nothing else is lost.
	setup_custom_perms(doctype)
	filters = {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
	name = frappe.db.get_value("Custom DocPerm", filters)
	if not name:
		if not create:
			return
		name = add_permission(doctype, role, 0)
		print(f"create Permission {doctype} -> {role}")

	rule = frappe.get_doc("Custom DocPerm", name)
	diff = {p: v for p, v in rights.items() if (rule.get(p) or 0) != v}
	if diff:
		rule.update(diff)
		rule.save(ignore_permissions=True)
		print(f"update Permission {doctype} -> {role}: {diff}")
	else:
		print(f"exists Permission {doctype} -> {role}")


def apply_permission_matrix():
	from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype

	for doctype in FINANCIAL_DOCTYPES:
		for role in ["Super Admin", "Accountant"]:
			ensure_docperm(doctype, role, FULL_RIGHTS, create=True)
		for role in MANAGER_STANDARD_ROLES:
			ensure_docperm(doctype, role, MANAGER_DENIED, create=False)
		validate_permissions_for_doctype(doctype)
		frappe.clear_cache(doctype=doctype)

	# "Manage employees and payroll": Super Admin and HR manage, Accountant views.
	# HR already has it through HR Manager.
	manage = {p: 1 for p in ("read", "write", "create", "delete", "report", "print", "email", "export", "share")}
	ensure_docperm("Employee", "Super Admin", manage, create=True)
	ensure_docperm("Employee", "Accountant", {"read": 1, "report": 1}, create=True)
	validate_permissions_for_doctype("Employee")
	frappe.clear_cache(doctype="Employee")


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

		# ---------- 4) Permissions matrix (section 3.2) on financial documents ----------
		apply_permission_matrix()

		# ---------- 5) Strict user permissions: OFF ----------
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

	# ---------- 6) Summary ----------
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
