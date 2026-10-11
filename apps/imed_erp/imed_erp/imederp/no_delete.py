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
	"Doctor Ledger Entry",
	"App Subscription",
	"Book Edition",
	"Printer Reading",
	"Allocation Rule",
]


def block_delete_of_posted(doc, method=None):
	if doc.docstatus != 0:
		frappe.throw(
			_("{0} {1} was submitted, so it cannot be deleted. Cancel it instead: it stays on record.").format(
				_(doc.doctype), doc.name
			),
			title=_("Cannot Delete"),
		)
