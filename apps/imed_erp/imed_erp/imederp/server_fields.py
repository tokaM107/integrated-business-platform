# Fields only the server sets, and documents only their own branch saves (security audit, 10 Nov 2026).
#
# A field shown read-only on the screen is not protected by that: Frappe takes whatever a request sends (REST insert
# or save, or a document method called with the caller's copy of the document). The links to what a document posted
# (its journal entry, its invoice), who approved or received it and its status are written by the document's own
# actions, with db_set or under a flag. keep() makes that the only way: on every save the fields are put back to
# what is stored, and on a new document they are empty.
#
# check_write_on_stored() closes the matching gap in permissions: Frappe checks the right to write against the
# values being saved, not the stored ones, so a user could take over another branch's draft by sending it with her
# own branch on it.

import frappe
from frappe import _


def keep(doc, fields, flag=None):
	"""Put `fields` back to what is stored (empty on a new document), unless the document's own action set
	`doc.flags[flag]`."""
	if flag and doc.flags.get(flag):
		return
	before = doc.get_doc_before_save()
	for field in fields:
		doc.set(field, before.get(field) if before else None)


ACTION_RIGHT = {"save": "write", "submit": "submit", "cancel": "cancel", "update_after_submit": "submit"}


def check_write_on_stored(doc, method=None):
	"""validate hook of every document: whoever changes a stored document may change it as it is stored."""
	if (
		doc.flags.ignore_permissions
		or frappe.flags.in_install
		or frappe.flags.in_migrate
		or frappe.flags.in_patch
		or frappe.session.user == "Administrator"
		or doc.meta.istable
	):
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	right = ACTION_RIGHT.get(getattr(doc, "_action", None) or "save", "write")
	if not frappe.has_permission(doc.doctype, right, doc=before):
		frappe.throw(
			_("You are not allowed to change {0} {1}.").format(_(doc.doctype), doc.name),
			frappe.PermissionError,
			title=_("Not Permitted"),
		)
