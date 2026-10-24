# A branch manager works only for their own branch: the cost centers in their User Permissions
# (setup/setup_users.py). The checks that read those permissions use this.
#
# SEC-07: a branch manager with no branch at all (a new account, a permission removed by mistake) is refused,
# not let through everywhere. The owner, the accountant and the system's own work are not branch-bound.

import frappe
from frappe import _

BRANCH_ROLE = "Branch Manager"
UNBOUND_ROLES = ("Accounts Manager", "System Manager", "Super Admin")


def check_has_branch(allowed, user=None):
	"""Throw when `user` is a branch manager and `allowed` (their branches) is empty."""
	roles = frappe.get_roles(user)
	if not allowed and BRANCH_ROLE in roles and not set(UNBOUND_ROLES) & set(roles):
		frappe.throw(
			_("Your account is not given a branch yet. Ask the owner to give you your branch."),
			frappe.PermissionError,
			title=_("No Branch"),
		)
