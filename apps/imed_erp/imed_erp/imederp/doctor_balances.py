# What is owed between the group and each doctor, read for the reports RPT-08 (doctor receivables) and RPT-10
# (doctor debts). Read only: nothing here posts, settles or changes a balance.
#
# The doctor's ledger (Doctor Ledger Entry) is the record: an agreement's balance is its submitted entries, each
# with the sign of its kind (doctor_agreement.BALANCE_SIGN), the same sum the agreement screen shows. The
# balance runs the way the agreement's type says (DOC-30): Books, owed to the doctor; App, owed by the doctor.
# A books balance below zero is a debt of the doctor that stays until it is settled (DOC-20), not an error.
#
# Platform fees are not in the ledger: an App Subscription posts nothing to it (doctors' accounts). So an app
# agreement's fees are read from its submitted subscriptions, and the ledger adds what was collected or
# adjusted. If app fees are one day posted to the ledger as Accruals, those agreements are read from the ledger
# alone (app_fees_in_ledger), so no fee is counted twice.

from collections import deque

import frappe
from frappe.utils import cint, date_diff, flt, getdate

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
		fields=["name", "agreement", "entry_date", "entry_type", "amount", "edition", "invoice_item", "journal_entry", "creation"],
		order_by="entry_date, creation",
	)
	set_branches(entries)
	for entry in entries:
		entry.signed = BALANCE_SIGN.get(entry.entry_type, 0) * flt(entry.amount)
	return entries


def set_branches(entries):
	"""The library an entry belongs to: the invoice line that posted it, else its edition, else the one cost center
	of its journal entry. A payment made for the agreement as a whole has none."""
	lines = {e.invoice_item for e in entries if e.invoice_item}
	editions = {e.edition for e in entries if e.edition}
	journals = {e.journal_entry for e in entries if e.journal_entry}
	line_branch = dict(
		frappe.get_all("Sales Invoice Item", filters={"name": ["in", list(lines)]}, fields=["name", "cost_center"], as_list=True)
	) if lines else {}
	edition_branch = dict(
		frappe.get_all("Book Edition", filters={"name": ["in", list(editions)]}, fields=["name", "cost_center"], as_list=True)
	) if editions else {}
	journal_branch = {}
	if journals:
		for name, centers in frappe.db.sql(
			"""select parent, group_concat(distinct cost_center) from `tabJournal Entry Account`
			where parent in %(journals)s and ifnull(cost_center, '') != '' group by parent""",
			{"journals": tuple(journals)},
		):
			if centers and "," not in centers:
				journal_branch[name] = centers
	for entry in entries:
		entry.branch = (
			line_branch.get(entry.invoice_item)
			or edition_branch.get(entry.edition)
			or journal_branch.get(entry.journal_entry)
			or None
		)


def app_fees_in_ledger(agreements):
	"""App agreements whose fees are posted to the ledger as Accruals: read from the ledger alone."""
	if not agreements:
		return set()
	return set(
		frappe.get_all(
			LEDGER,
			filters={"agreement": ["in", agreements], "entry_type": "Accrual", "docstatus": 1},
			pluck="agreement",
			distinct=True,
		)
	)


def get_subscription_fees(agreements, to_date=None):
	"""{agreement: [(date, fee, branch, subscription)]} from submitted App Subscriptions."""
	if not agreements:
		return {}
	conditions = {"agreement": ["in", agreements], "docstatus": 1}
	if to_date:
		conditions["subscription_date"] = ["<=", to_date]
	fees = {}
	for row in frappe.get_all(
		"App Subscription",
		filters=conditions,
		fields=["name", "agreement", "subscription_date", "platform_fee", "cost_center"],
		order_by="subscription_date, creation",
	):
		if flt(row.platform_fee):
			fees.setdefault(row.agreement, []).append((row.subscription_date, flt(row.platform_fee), row.cost_center, row.name))
	return fees


def age_debt(movements):
	"""FIFO: movements are (date, amount), > 0 adds to the debt, < 0 pays it. What pays a debt settles its oldest
	part first; what is paid beyond the debt is held and set against the next one. Returns what is still owed,
	as [(date it arose, amount)]."""
	open_debts, credit = deque(), 0.0
	for date, amount in sorted(movements, key=lambda m: getdate(m[0])):
		amount = flt(amount)
		if amount > 0:
			used = min(credit, amount)
			credit -= used
			if amount - used > 0:
				open_debts.append([getdate(date), amount - used])
		elif amount < 0:
			paying = -amount
			while paying > 0 and open_debts:
				oldest = open_debts[0]
				used = min(oldest[1], paying)
				oldest[1] -= used
				paying -= used
				if oldest[1] <= 0.005:
					open_debts.popleft()
			credit += paying
	return [(date, flt(amount, 2)) for date, amount in open_debts if flt(amount, 2) > 0]


def ageing_buckets(debts, as_of, ranges):
	"""The open debts by age in days on `as_of`: [up to r1, r1+1 to r2, ..., above the last]."""
	buckets = [0.0] * (len(ranges) + 1)
	for date, amount in debts:
		age = date_diff(as_of, date)
		index = next((i for i, limit in enumerate(ranges) if age <= limit), len(ranges))
		buckets[index] += amount
	return buckets


def parse_ranges(value):
	ranges = sorted({cint(part) for part in str(value or "30, 60, 90").split(",") if cint(part) > 0})
	return ranges or [30, 60, 90]
