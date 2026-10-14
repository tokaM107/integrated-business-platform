# A sale is cancelled only with its reason (requirements v1.2: ACC-06, with SEC-01, SEC-03 and ACC-07).
#
#   ACC-06  wrong sales are cancelled with their reason, by those allowed to (there are no returns in the
#           libraries: a sale made by mistake is cancelled, never returned).
#   SEC-03  only the owner and the accountant change or cancel a transaction. That is the cancel right on Sales
#           Invoice (setup_users.py): Super Admin, Accountant and Accounts Manager have it, branch managers do not.
#           Nothing here grants or widens it; ERPNext checks it on every cancel.
#   ACC-07  nothing is deleted: cancelling is ERPNext's own, which reverses the ledger and stock entries and keeps
#           the invoice as Cancelled (imederp/no_delete.py keeps it from being deleted).
#   SEC-01  the reason is saved on the cancelled invoice itself, in cancel_reason, and Sales Invoice
#           tracks changes, so its history shows who cancelled it, when, and the reason they gave.
#
# The Cancel button asks for the reason first (public/js/sales_invoice.js) and cancels through cancel_with_reason,
# so the reason and the cancellation are saved together or not at all. Any other way of cancelling (the API, a
# script) is refused by require_cancel_reason when the invoice carries no reason.

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cstr, escape_html, strip_html

# Frappe never copies a field of this name into an amendment or a duplicate (frappe.model.copy_doc), so the
# corrected invoice does not start with the old reason.
REASON_FIELD = "cancel_reason"
DOCTYPES = ("Sales Invoice",)
# A reason is a sentence or two; a longer text is refused rather than cut.
MAX_REASON_LENGTH = 1000

CUSTOM_FIELDS = {
	"Sales Invoice": [
		{
			"fieldname": REASON_FIELD,
			"fieldtype": "Small Text",
			"label": "Cancellation Reason",
			"insert_after": "amended_from",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"depends_on": f"eval:doc.docstatus == 2 || doc.{REASON_FIELD}",
		},
	],
}


def make_custom_fields():
	"""after_install / after_migrate hook."""
	create_custom_fields(CUSTOM_FIELDS, update=True)


def clean_reason(reason):
	"""The reason as plain text. Frappe does not clean a document's fields on cancel (Document._save skips
	_validate), so markup typed as a reason would be kept and shown as HTML on the invoice and in its history."""
	return strip_html(cstr(reason)).strip()


def require_cancel_reason(doc, method=None):
	"""before_cancel hook."""
	reason = clean_reason(doc.get(REASON_FIELD))
	if reason:
		if len(reason) > MAX_REASON_LENGTH:
			frappe.throw(_("The cancellation reason is too long: at most {0} characters.").format(MAX_REASON_LENGTH))
		doc.set(REASON_FIELD, reason)
		return
	if doc.flags.from_damaged_stock:
		# Cancelled with the Damaged Stock Sale that posted it (imederp/damaged_stock.py), which is the record.
		doc.set(REASON_FIELD, _("Cancelled with the Damaged Stock Sale that posted it."))
		return
	frappe.throw(
		_("Give the reason for cancelling {0}.").format(escape_html(doc.name)),
		title=_("Cancellation Reason Required"),
	)


@frappe.whitelist(methods=["POST"])
def cancel_with_reason(doctype, name, reason):
	"""Cancel the document with its reason, in one transaction: if ERPNext refuses the cancellation (a closed
	period, a payment still linked...), the reason is not saved either."""
	if doctype not in DOCTYPES:
		frappe.throw(_("{0} is not cancelled this way.").format(escape_html(cstr(doctype))))
	if not clean_reason(reason):
		frappe.throw(
			_("Give the reason for cancelling {0}.").format(escape_html(cstr(name))),
			title=_("Cancellation Reason Required"),
		)

	doc = frappe.get_doc(doctype, name)
	# The same right ERPNext checks on cancel, asked first so nothing else runs for someone without it.
	doc.check_permission("cancel")
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted {0} can be cancelled.").format(_(doctype)))
	# Cleaned and checked again by require_cancel_reason, which every cancel runs.
	doc.set(REASON_FIELD, reason)
	doc.cancel()
	return doc.name
