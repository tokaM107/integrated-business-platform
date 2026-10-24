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

# QA-04: a return (credit note) reverses a sale as surely as cancelling it, and can pay cash out of the box, so it
# has the same rule: only the owner and the accountant (Accounts Manager), and only with its reason.
RETURN_REASON_FIELD = "return_reason"
RETURN_ROLE = "Accounts Manager"
RETURN_REASON = {
	"fieldname": RETURN_REASON_FIELD,
	"fieldtype": "Small Text",
	"label": "Return Reason",
	"insert_after": "is_return",
	"no_copy": 1,
	"print_hide": 1,
	"depends_on": "eval:doc.is_return",
	"mandatory_depends_on": "eval:doc.is_return",
}

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
		RETURN_REASON,
	],
	"POS Invoice": [RETURN_REASON],
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


def restrict_returns(doc, method=None):
	"""Sales Invoice and POS Invoice validate hook (QA-04). The libraries take no returns (§9); a sale made by
	mistake is cancelled with its reason, or returned by the owner or the accountant with its reason. A branch
	manager's return, from the desk or the POS Return button, is refused. The Sales Invoice ERPNext makes from a
	shift's POS invoices (is_consolidated) carries returns already checked one by one."""
	if not doc.get("is_return") or doc.get("is_consolidated") or doc.flags.from_damaged_stock:
		return
	if RETURN_ROLE not in frappe.get_roles():
		frappe.throw(
			_("Only the owner or the accountant may return a sale. Ask them, or cancel a sale made by mistake with its reason."),
			frappe.PermissionError,
			title=_("Not Allowed"),
		)
	reason = clean_reason(doc.get(RETURN_REASON_FIELD))
	if not reason:
		frappe.throw(_("Give the reason for this return."), title=_("Return Reason Required"))
	if len(reason) > MAX_REASON_LENGTH:
		frappe.throw(_("The return reason is too long: at most {0} characters.").format(MAX_REASON_LENGTH))
	doc.set(RETURN_REASON_FIELD, reason)
