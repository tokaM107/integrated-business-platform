# The home screen's app tiles (Frappe's Desktop Icons), kept to what the group uses (owner's request of 21 Oct
# 2026: "remove what is of no use"). The ImedERP tile itself is imed_erp/desktop_icon/imederp.json.
#
#   hidden for everyone   ERPNext areas the group does not use: no manufacturing, projects, quality inspection,
#                         subcontracting or fixed assets in the requirements; in Accounting, taxes (no VAT
#                         is charged), budgets, share management and ERPNext's subscriptions.
#   Administrator only    the technical areas (Framework: users, email, printing, system; ERPNext Settings;
#                         Organization): set up by the developer, not used by the owner or the branches.
#   no update pop-up      System Settings > Disable System Update Notification.
#
# Nothing is deleted: a hidden tile's screens are still reached by search and by their links. Applied after every
# migrate, since an ERPNext update may bring its tiles back. Written straight to the database: saving a standard
# icon in developer mode would write it into ERPNext's own files.

import frappe

HIDDEN = [
	"Manufacturing",
	"Projects",
	"Quality",
	"Subcontracting",
	"Assets",
	# Inside Accounting: no VAT is charged, and no budgets, shares or ERPNext subscriptions are kept.
	"Taxes",
	"Budget",
	"Share Management",
	"Subscription",
]
ADMINISTRATOR_ONLY = ["Framework", "ERPNext Settings", "Organization"]


def tidy_home():
	"""after_migrate hook."""
	changed = False
	for label in HIDDEN:
		if frappe.db.exists("Desktop Icon", label) and not frappe.db.get_value(
			"Desktop Icon", label, "hidden"
		):
			frappe.db.set_value("Desktop Icon", label, "hidden", 1, update_modified=False)
			changed = True
	for label in ADMINISTRATOR_ONLY:
		if not frappe.db.exists("Desktop Icon", label):
			continue
		roles = frappe.get_all(
			"Has Role", filters={"parenttype": "Desktop Icon", "parent": label}, pluck="role"
		)
		if roles == ["Administrator"]:
			continue
		frappe.db.delete("Has Role", {"parenttype": "Desktop Icon", "parent": label})
		frappe.get_doc(
			{
				"doctype": "Has Role",
				"parenttype": "Desktop Icon",
				"parentfield": "roles",
				"parent": label,
				"role": "Administrator",
				"idx": 1,
			}
		).db_insert()
		changed = True
	changed = owner_lands_on_dashboard() or changed
	# The "new versions of Frappe / ERPNext" pop-up is the developer's business, not the owner's.
	if not frappe.db.get_single_value("System Settings", "disable_system_update_notification"):
		frappe.db.set_single_value("System Settings", "disable_system_update_notification", 1)
		changed = True
	if changed:
		# Every user's tiles and boot are cached: drop them all, not only the current user's.
		frappe.cache.delete_key("desktop_icons")
		frappe.cache.delete_key("bootinfo")


DASHBOARD = "Owner Dashboard"
OWNER_ROLE = "Super Admin"


def owner_lands_on_dashboard():
	"""The owner logs in to the Owner Dashboard, with the ImedERP sidebar beside it (owner's request of 21 Oct
	2026: every screen on the side, the money in the middle).

	Frappe shows a workspace with the sidebar of its own name, which it made for the dashboard when it was created
	(its shortcuts, a few reports). Without it, Frappe shows the sidebar that links to the dashboard: ImedERP, where
	every screen is, and its Financial Reports group has those reports. The dashboard's tile goes with its sidebar;
	the dashboard is the owner's landing page and the ImedERP tile's first link. An owner who chose another landing
	page keeps it."""
	changed = False
	sidebar = frappe.db.get_value("Workspace Sidebar", DASHBOARD, ["name", "standard"], as_dict=True)
	if sidebar and not sidebar.standard:
		frappe.delete_doc("Workspace Sidebar", DASHBOARD, force=True, ignore_permissions=True)
		changed = True
	if frappe.db.exists("Desktop Icon", DASHBOARD) and not frappe.db.get_value(
		"Desktop Icon", DASHBOARD, "hidden"
	):
		frappe.db.set_value("Desktop Icon", DASHBOARD, "hidden", 1, update_modified=False)
		changed = True
	if frappe.db.exists("Workspace", DASHBOARD):
		owners = frappe.get_all(
			"Has Role", filters={"role": OWNER_ROLE, "parenttype": "User"}, pluck="parent"
		)
		for user in set(owners) - {"Administrator"}:
			if not frappe.db.get_value("User", user, "default_workspace"):
				frappe.db.set_value("User", user, "default_workspace", DASHBOARD, update_modified=False)
				frappe.cache.hdel("home_page", user)
				changed = True
	return changed
