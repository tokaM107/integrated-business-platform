# The doctor's amount on every copy sold (DOC-07, LIB-05; owner, 10 Oct 2026: on copies sold only).
#
# A sales invoice row that names a Book Edition (imederp/edition_sales.py) sold copies of a doctor's book. When the
# invoice is submitted, each such row adds one Accrual to the doctor's ledger: the row's quantity (in the item's
# stock unit) x the edition's Doctor's Amount per Copy, which the edition kept when it was approved. The point of
# sale makes Sales Invoices too (POS Settings), so its sales are counted the same way.
#
# The row is the key: an entry names its invoice and its invoice line (Doctor Ledger Entry sales_invoice,
# invoice_item), and a line already in the ledger is skipped, so counting an invoice again adds nothing.
# A credit note gives the copies back: its rows add an Adjustment of minus their amount, keyed the same way.
#
# hooks.py runs on Sales Invoice:
#   on_submit   accrue            one entry per edition row
#   on_cancel   cancel_accruals   its entries are cancelled with it, so the balance goes back. They are cancelled
#                                 before ERPNext checks for documents still linked to the invoice.

import frappe
from frappe import _
from frappe.utils import flt

from imed_erp.imederp.edition_sales import FIELD

LEDGER = "Doctor Ledger Entry"


def accrue(doc, method=None):
	"""Sales Invoice on_submit hook."""
	for row in doc.items:
		if row.get(FIELD):
			accrue_row(doc, row)


def accrue_row(doc, row):
	if frappe.db.exists(LEDGER, {"invoice_item": row.name, "docstatus": ["<", 2]}):
		return
	edition = frappe.db.get_value("Book Edition", row.get(FIELD), ["agreement", "period", "doctor_share"], as_dict=True)
	qty = flt(row.stock_qty or row.qty)
	amount = flt(qty * flt(edition.doctor_share), frappe.get_precision(LEDGER, "amount"))
	if not amount:
		return
	entry = frappe.get_doc(
		{
			"doctype": LEDGER,
			"agreement": edition.agreement,
			"period": edition.period,
			"entry_date": doc.posting_date,
			# A credit note takes the copies back: an adjustment carries its own sign.
			"entry_type": "Adjustment" if amount < 0 else "Accrual",
			"edition": row.get(FIELD),
			"qty": qty,
			"amount": amount,
			"sales_invoice": doc.name,
			"invoice_item": row.name,
			"remarks": _("{0} row #{1}: {2} x {3}").format(doc.name, row.idx, qty, flt(edition.doctor_share)),
		}
	)
	# The seller (a branch manager) cannot open the doctors' accounts; the sale posts the entry for them.
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()


def cancel_accruals(doc, method=None):
	"""Sales Invoice on_cancel hook: the copies are no longer sold, so the doctor's amount on them goes."""
	for name in frappe.get_all(LEDGER, filters={"sales_invoice": doc.name, "docstatus": 1}, pluck="name"):
		entry = frappe.get_doc(LEDGER, name)
		entry.flags.ignore_permissions = True
		entry.cancel()
