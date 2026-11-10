# Lists a branch manager reads are their branch's only. A Journal Entry names its cost centers on its lines, not on
# itself, so Frappe's User Permissions kept another branch's entry from being opened but not from being listed:
# its title and total showed in a manager's list (API probe of 10 Nov 2026: Azarita's manager listed the halls'
# entry). Here a user limited to some cost centers (User Permissions on Cost Center) lists the entries with a line
# on one of them only; a user without such a limit (the owner, the accountant) keeps every entry.
import frappe

UNLIMITED = {"System Manager", "Super Admin"}


def my_cost_centers(user):
	if not user or user == "Administrator" or UNLIMITED & set(frappe.get_roles(user)):
		return None
	return frappe.get_all("User Permission", filters={"user": user, "allow": "Cost Center"}, pluck="for_value") or None


def journal_entry_conditions(user=None):
	centers = my_cost_centers(user or frappe.session.user)
	if not centers:
		return ""
	values = ", ".join(frappe.db.escape(c) for c in centers)
	return (
		"exists (select 1 from `tabJournal Entry Account` jea where jea.parent = `tabJournal Entry`.name"
		f" and jea.parenttype = 'Journal Entry' and jea.cost_center in ({values}))"
	)


def my_warehouses(user):
	"""The stores a user is limited to (User Permissions on Warehouse), with the stores under a group one; None
	when the user has no such limit."""
	if not user or user == "Administrator" or UNLIMITED & set(frappe.get_roles(user)):
		return None
	allowed = frappe.get_all("User Permission", filters={"user": user, "allow": "Warehouse"}, pluck="for_value")
	if not allowed:
		return None
	stores = set()
	for name in allowed:
		lft, rgt = frappe.db.get_value("Warehouse", name, ["lft", "rgt"]) or (0, 0)
		stores.update(frappe.get_all("Warehouse", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name") if lft else [name])
	return sorted(stores)


def stock_entry_conditions(user=None):
	"""A Stock Entry names its stores on its lines (its head's are often empty): a user limited to some stores lists
	the entries with a line from or into one of them only (the same probe: Azarita's manager listed Mawasah's)."""
	stores = my_warehouses(user or frappe.session.user)
	if not stores:
		return ""
	values = ", ".join(frappe.db.escape(s) for s in stores)
	return (
		"exists (select 1 from `tabStock Entry Detail` sed where sed.parent = `tabStock Entry`.name"
		f" and (sed.s_warehouse in ({values}) or sed.t_warehouse in ({values})))"
	)
