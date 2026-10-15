# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The doctor's statement (DOC-08, DOC-13): one agreement and one academic period on their own, from the doctor's
# ledger. It starts from the balance brought forward (a negative one stays a debt and is taken from what comes
# next, DOC-20), then one row per edition sold in the period (copies sold, selling price, cost of a copy, the
# doctor's amount per copy and what he earned on them), then the period's other entries (payouts, charges for
# unsold copies, adjustments) by date, and the balance at the end.
#
# What the doctor is shown leaves out the library's side (owner, DOC-13): its profit per sheet, its marketing and
# any difference between the calculated price and the price set by hand. The cost of a copy is what it costs to
# make (book_edition.get_copy_cost).
#
# An entry belongs to the period it names, or to the term above it; an entry with no period (a payout entered
# without one) belongs to the period its date falls in.

import frappe
from frappe import _
from frappe.utils import flt, getdate

from imed_erp.imederp.doctype.book_edition.book_edition import get_copy_cost
from imed_erp.imederp.doctype.doctor_ledger_entry.doctor_ledger_entry import descendants
from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import BALANCE_SIGN, DIRECTION, OWED_BY_DOCTOR, OWED_TO_DOCTOR


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.agreement and filters.period):
		return get_columns(), []
	data, totals = get_data(filters)
	return get_columns(), data, None, None, get_summary(filters.agreement, totals)


def get_columns():
	return [
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 220},
		{"label": _("Edition"), "fieldname": "edition", "fieldtype": "Link", "options": "Book Edition", "width": 180},
		{"label": _("Copies Sold"), "fieldname": "sold_qty", "fieldtype": "Float", "precision": 0, "width": 100},
		{"label": _("Selling Price"), "fieldname": "selling_price", "fieldtype": "Currency", "width": 110},
		{"label": _("Cost per Copy"), "fieldname": "copy_cost", "fieldtype": "Currency", "width": 110},
		{"label": _("Doctor's Amount per Copy"), "fieldname": "doctor_share", "fieldtype": "Currency", "width": 130},
		{"label": _("Owed"), "fieldname": "owed", "fieldtype": "Currency", "width": 120},
		{"label": _("Paid / Deducted"), "fieldname": "paid", "fieldtype": "Currency", "width": 120},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 120},
	]


def get_entries(agreement):
	return frappe.get_all(
		"Doctor Ledger Entry",
		filters={"agreement": agreement, "docstatus": 1},
		fields=["name", "period", "entry_date", "entry_type", "edition", "qty", "amount", "sales_invoice", "remarks"],
		order_by="entry_date, creation",
	)


def get_data(filters):
	period = frappe.db.get_value("Academic Period", filters.period, ["start_date", "end_date"], as_dict=True)
	start, end = getdate(period.start_date), getdate(period.end_date)

	# A term's statement takes in its rounds and modules (books settle by module, DOC-05).
	periods = {filters.period, *descendants(filters.period)}

	def in_period(entry):
		if entry.period:
			return entry.period in periods
		return start <= getdate(entry.entry_date) <= end

	def signed(entry):
		return BALANCE_SIGN.get(entry.entry_type, 0) * flt(entry.amount)

	entries = get_entries(filters.agreement)
	movements = [e for e in entries if in_period(e)]
	opening = sum(signed(e) for e in entries if not in_period(e) and getdate(e.entry_date) < start)

	rows = [{"description": _("Balance Brought Forward"), "balance": opening, "is_total": 1}]
	balance, owed_total, paid_total = opening, 0, 0

	# Copies sold, one row per edition: its sales and returns in the period.
	sold = {}
	for entry in movements:
		if entry.sales_invoice and entry.edition:
			edition = sold.setdefault(entry.edition, frappe._dict(qty=0, amount=0))
			edition.qty += flt(entry.qty)
			edition.amount += signed(entry)
	for name, edition in sold.items():
		values = frappe.db.get_value(
			"Book Edition",
			name,
			["selling_price", "doctor_share", "paper_cost", "ink_cost", "overhead_cost", "pages", "binding_cost"],
			as_dict=True,
		)
		balance += edition.amount
		owed_total += edition.amount
		rows.append(
			{
				"description": _("Copies Sold"),
				"edition": name,
				"sold_qty": edition.qty,
				"selling_price": values.selling_price,
				"copy_cost": get_copy_cost(values),
				"doctor_share": values.doctor_share,
				"owed": edition.amount,
				"balance": balance,
			}
		)

	# Everything else in the period, by date: payouts, charges for unsold copies, adjustments, collections.
	for entry in movements:
		if entry.sales_invoice and entry.edition:
			continue
		amount = signed(entry)
		balance += amount
		row = {
			"description": " — ".join(
				filter(None, [_(entry.entry_type), frappe.format_value(entry.entry_date, {"fieldtype": "Date"}), entry.remarks])
			),
			"edition": entry.edition,
			"sold_qty": entry.qty if entry.edition else None,
			"balance": balance,
		}
		if amount >= 0:
			row["owed"] = amount
			owed_total += amount
		else:
			row["paid"] = -amount
			paid_total += -amount
		rows.append(row)

	rows.append({"description": _("Balance at the End of the Period"), "balance": balance, "is_total": 1})
	return rows, frappe._dict(opening=opening, owed=owed_total, paid=paid_total, closing=balance)


def get_summary(agreement, totals):
	# DOC-20: a balance below zero runs the other way (a books doctor charged more than he earned owes the group).
	direction = DIRECTION.get(frappe.db.get_value("Doctor Agreement", agreement, "agreement_type"))
	if totals.closing < 0:
		direction = OWED_BY_DOCTOR if direction == OWED_TO_DOCTOR else OWED_TO_DOCTOR
	return [
		{"label": _("Balance Brought Forward"), "value": totals.opening, "datatype": "Currency"},
		{"label": _("Owed"), "value": totals.owed, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Paid / Deducted"), "value": totals.paid, "datatype": "Currency", "indicator": "Green"},
		{
			"label": _("Balance") + " — " + _(direction),
			"value": abs(totals.closing),
			"datatype": "Currency",
			"indicator": "Orange" if direction == OWED_TO_DOCTOR else "Blue",
		},
	]
