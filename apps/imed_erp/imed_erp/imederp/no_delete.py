# No financial transaction is ever deleted (ACC-07, owner's decision of 7 Oct 2026). A mistake is corrected
# by cancelling the document, which reverses its entries and keeps it on record. Only a draft, never posted,
# can be deleted, and only by the owner (the permission is his alone; see setup_users.py).
#
# hooks.py runs this on_trash for every financial doctype, ERPNext's and the app's.

import frappe
from frappe import _

FINANCIAL_DOCTYPES = [
	# ERPNext
	"Sales Invoice",
	"POS Invoice",
	"Purchase Invoice",
	"Payment Entry",
	"Journal Entry",
	"Stock Entry",
	"Delivery Note",
	"Purchase Receipt",
	"Stock Reconciliation",
	"Cost Center Allocation",
	# The app
	"Expense",
	"Inter Business Transfer",
	"Doctor Agreement",
	"Doctor Ledger Entry",
	"App Subscription",
	"Book Edition",
	"Printer Reading",
	"Daily Counter Reading",
	"Allocation Rule",
	"Stock Count",
	"Damaged Stock Entry",
	"Damaged Stock Sale",
	# SEC-12
	"Material Request",
	"Platform Fee Schedule",
	"Treasury Close",
]

# Never submitted, so kept by what they carry instead (SEC-12, INT-01): a booking imported from the booking system
# or with money or a posting on it, and a course with students or fees.
KEPT_DOCTYPES = ["Booking", "App Course"]


def block_delete_of_posted(doc, method=None):
	if doc.docstatus != 0:
		frappe.throw(
			_("{0} {1} was submitted, so it cannot be deleted. Cancel it instead: it stays on record.").format(
				_(doc.doctype), doc.name
			),
			title=_("Cannot Delete"),
		)


def block_delete_of_kept(doc, method=None):
	"""on_trash of a record that is never submitted: refused once it carries something the books or another system
	rely on. A mistake is cancelled (a booking) or closed (a course), and stays on record."""
	reason = None
	if doc.doctype == "Booking":
		if doc.get("source") == "Imported":
			reason = _("it was imported from the booking system")
		elif doc.get("sales_invoice") or doc.get("journal_entry") or frappe.db.exists(
			"Payment Entry", {"custom_booking": doc.name, "docstatus": ("<", 2)}
		):
			reason = _("it has money or a posting on it")
	elif doc.doctype == "App Course":
		if frappe.db.exists("App Subscription", {"course": doc.name}) or frappe.db.exists(
			"Doctor Ledger Entry", {"app_course": doc.name}
		):
			reason = _("it has subscriptions or fees")
	if reason:
		frappe.throw(
			_("{0} {1} cannot be deleted: {2}. Cancel or close it instead: it stays on record.").format(
				_(doc.doctype), doc.name, reason
			),
			title=_("Cannot Delete"),
		)
