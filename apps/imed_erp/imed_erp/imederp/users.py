# Users are disabled, never deleted (CORE-07: "تعطيل الحساب بدل حذفه"). A user's history (who recorded a sale,
# approved an expense, counted the cash) names the account; deleting it would leave those records pointing at nobody.
# The developers' own account (Administrator) may still remove an account made by mistake.

import frappe
from frappe import _


def block_user_delete(doc, method=None):
	"""User on_trash hook."""
	if frappe.session.user == "Administrator" or frappe.flags.in_install or frappe.flags.in_uninstall:
		return
	frappe.throw(
		_("A user is not deleted: disable the account instead (untick Enabled). Their history stays on record."),
		frappe.PermissionError,
		title=_("Disable Instead"),
	)
