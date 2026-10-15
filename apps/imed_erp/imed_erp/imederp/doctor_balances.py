# What the group owes each doctor, read for the Doctor Receivables report (RPT-08). Read only: nothing here
# posts, settles or changes a balance. What doctors owe the group is the Doctor Debts report (RPT-10).
#
# The doctor's ledger (Doctor Ledger Entry) is the record: an agreement's balance is its submitted entries, each
# with the sign of its kind (doctor_agreement.BALANCE_SIGN), the same sum the agreement screen shows. The
# balance runs the way the agreement's type says (DOC-30): Books, owed to the doctor; App, owed by the doctor.
# A books balance below zero is a debt of the doctor that stays until it is settled (DOC-20), not an error.

import frappe
from frappe.utils import flt

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import BALANCE_SIGN

LEDGER = "Doctor Ledger Entry"


def check_permission():
	"""The reports read the ledger directly; only those who may open it see them."""
	if not frappe.has_permission(LEDGER, "read"):
		frappe.throw(frappe._("You are not allowed to see the doctors' accounts."), frappe.PermissionError)


def get_agreements(filters, agreement_type=None):
	conditions = {"docstatus": 1}
	if filters.get("doctor"):
		conditions["doctor"] = filters.get("doctor")
	# A report about one type keeps it whatever the filters say: another type's balance runs the other way.
	if agreement_type:
		conditions["agreement_type"] = agreement_type
	elif filters.get("agreement_type"):
		conditions["agreement_type"] = filters.get("agreement_type")
	if filters.get("agreement"):
		conditions["name"] = filters.get("agreement")
	return frappe.get_all(
		"Doctor Agreement",
		filters=conditions,
		fields=["name", "doctor", "agreement_type", "balance_direction", "status", "balance", "last_settlement_date"],
		order_by="doctor, name",
	)


def get_entries(agreements, to_date=None):
	"""Submitted ledger entries of the agreements, oldest first, each with its signed amount and its branch."""
	if not agreements:
		return []
	conditions = {"agreement": ["in", agreements], "docstatus": 1}
	if to_date:
		conditions["entry_date"] = ["<=", to_date]
	entries = frappe.get_all(
		LEDGER,
		filters=conditions,
		fields=["name", "agreement", "entry_date", "entry_type", "amount", "edition", "invoice_item", "creation"],
		order_by="entry_date, creation",
	)
	set_branches(entries)
	for entry in entries:
		entry.signed = BALANCE_SIGN.get(entry.entry_type, 0) * flt(entry.amount)
	return entries


def set_branches(entries):
	"""The library an entry belongs to: the invoice line that posted it, else its edition. A payout or an adjustment
	for the agreement as a whole has none. Its journal entry is not read for this: a payout's journal entry carries
	no library, and ERPNext fills in the company's default cost center, which is not one."""
	lines = {e.invoice_item for e in entries if e.invoice_item}
	editions = {e.edition for e in entries if e.edition}
	line_branch = dict(
		frappe.get_all("Sales Invoice Item", filters={"name": ["in", list(lines)]}, fields=["name", "cost_center"], as_list=True)
	) if lines else {}
	edition_branch = dict(
		frappe.get_all("Book Edition", filters={"name": ["in", list(editions)]}, fields=["name", "cost_center"], as_list=True)
	) if editions else {}
	for entry in entries:
		entry.branch = line_branch.get(entry.invoice_item) or edition_branch.get(entry.edition) or None

