# Copyright (c) 2026, toka mohamed and contributors
# License information in license.txt

"""Who the test users are, before anyone disables them (read-only): identity, roles, what they own or changed,
their restrictions and open sessions. Run it, read it, then decide; `disable_users` turns off exactly the names it is
given (reversible: User > Enabled).

    bench --site <site> execute imed_erp.setup.review_test_users.run
    bench --site <site> execute imed_erp.setup.review_test_users.disable_users --kwargs "{'users': [...]}"
"""

import frappe

TEST_USERS = (
	"marcus@abc.com", "mathias@abc.com", "thalia@abc.com",
	"test@example.com", "test1@example.com", "test2@example.com", "test3@example.com", "test4@example.com", "test'5@example.com",
	"testdelete@example.com", "testpassword@example.com", "testperm@example.com",
)
DOCTYPES = (
	"Sales Invoice", "Payment Entry", "Journal Entry", "Booking", "Customer", "Expense", "Treasury Close", "Cash Handover",
	"ToDo", "Communication", "File", "Comment", "Integration Import Log", "Studio Hour Package", "Doctor Agreement",
	"Book Edition", "Material Request", "Stock Entry", "Item", "Company", "Note", "Event",
)


def run(users=None):
	out = {}
	for user in users or TEST_USERS:
		row = frappe.db.get_value("User", user, ["full_name", "user_type", "creation", "last_login", "last_active", "enabled"], as_dict=True)
		if not row:
			out[user] = "not on this site"
			continue
		owned = {}
		for doctype in DOCTYPES:
			if not frappe.db.exists("DocType", doctype):
				continue
			n = frappe.db.count(doctype, {"owner": user}) + frappe.db.count(doctype, {"modified_by": user})
			if n:
				owned[doctype] = n
		out[user] = {
			"full_name": row.full_name,
			"user_type": row.user_type,
			"enabled": row.enabled,
			"created": str(row.creation)[:19],
			"last_login": str(row.last_login)[:19] if row.last_login else None,
			"last_active": str(row.last_active)[:19] if row.last_active else None,
			"roles": frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, pluck="role"),
			"owner_or_modifier_of": owned,
			"user_permissions": [f"{p.allow}: {p.for_value}" for p in frappe.get_all("User Permission", filters={"user": user}, fields=["allow", "for_value"])],
			"open_sessions": frappe.db.count("Sessions", {"user": user}),
			"made_by_frappe_test_fixtures": user.endswith("@example.com") or user.endswith("@abc.com"),
		}
	return out


def disable_users(users):
	"""Disable exactly these users (no deletion: their records and history stay). Returns what changed."""
	if isinstance(users, str):
		users = frappe.parse_json(users)
	changed = []
	for user in users:
		if user in ("Administrator", "Guest") or user.endswith("@imed.local"):
			frappe.throw(f"{user} is not a test user; refused.")
		if frappe.db.get_value("User", user, "enabled"):
			frappe.db.set_value("User", user, "enabled", 0)
			frappe.db.delete("Sessions", {"user": user})
			changed.append(user)
	frappe.db.commit()
	return {"disabled": changed}
