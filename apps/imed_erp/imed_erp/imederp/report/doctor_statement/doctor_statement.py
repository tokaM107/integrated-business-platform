# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The doctor's statement (DOC-08, DOC-13): one agreement and one academic period on their own, from the doctor's
# ledger. It starts from the balance brought forward (a negative one stays a debt and is taken from what comes
# next, DOC-20), then one row per edition sold in the period (copies sold, selling price, cost of a copy, the
# doctor's amount per copy and what he earned on them), or for an app agreement one row per course (APP-11: its
# students, tier, fee per student and the platform fee), then the period's other entries (payouts, charges for
# unsold copies, adjustments, collections) by date, and the balance at the end. A fee not collected stays a debt
# and is the next term's balance brought forward (APP-12).
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
	return get_columns(filters.agreement), data, None, None, get_summary(filters.agreement, totals)


def get_columns(agreement=None):
	if agreement and frappe.db.get_value("Doctor Agreement", agreement, "agreement_type") == "App":
		# APP-11: the app statement, one row per course: its students, tier and fee.
		return [
			{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 220},
			{"label": _("Course Name"), "fieldname": "course_name", "fieldtype": "Data", "width": 180},
			{"label": _("Students"), "fieldname": "students", "fieldtype": "Int", "width": 90},
			{"label": _("Tier"), "fieldname": "tier", "fieldtype": "Data", "width": 100},
			{"label": _("Fee per Student"), "fieldname": "fee_per_student", "fieldtype": "Currency", "width": 120},
			{"label": _("Owed"), "fieldname": "owed", "fieldtype": "Currency", "width": 120},
			{"label": _("Collected"), "fieldname": "paid", "fieldtype": "Currency", "width": 120},
			{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 120},
		]
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
		fields=["name", "period", "entry_date", "entry_type", "edition", "qty", "amount", "sales_invoice", "app_course", "remarks"],
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

	# QA-01: an entry belongs before this period by the period it names, not by its date. A payout, a charge or a
	# collection for a closed term is often recorded after the next term has started; it is still that term's,
	# so it is part of what is brought forward. A period that overlaps this one (the term above a module) falls
	# back to the date.
	ends = dict(frappe.get_all("Academic Period", fields=["name", "end_date"], as_list=True))
	starts = dict(frappe.get_all("Academic Period", fields=["name", "start_date"], as_list=True))

	def before_period(entry):
		if entry.period and entry.period in ends:
			if getdate(ends[entry.period]) < start:
				return True
			if getdate(starts[entry.period]) >= start:
				return False
		return getdate(entry.entry_date) < start

	entries = get_entries(filters.agreement)
	movements = [e for e in entries if in_period(e)]
	opening = sum(signed(e) for e in entries if not in_period(e) and before_period(e))

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

	# APP-11: the platform fees, one row per course: what its entries add up to in the period (every student,
	# and the tier changes, platform_fee_posting.py), with the course as it was last counted.
	from imed_erp.imederp.report.platform_fees.platform_fees import course_tier

	fees = {}
	for entry in movements:
		if entry.app_course:
			fees[entry.app_course] = fees.get(entry.app_course, 0) + signed(entry)
	for name, amount in fees.items():
		course = frappe.db.get_value(
			"App Course", name, ["course_name", "period", "subscriptions", "fee_per_student", "tier"], as_dict=True
		)
		balance += amount
		owed_total += amount
		rows.append(
			{
				"description": _("Platform Fee"),
				"course_name": course.course_name,
				"students": course.subscriptions,
				"tier": course_tier(course),
				"fee_per_student": course.fee_per_student,
				"owed": amount,
				"balance": balance,
			}
		)

	# Everything else in the period, by date: payouts, charges for unsold copies, adjustments, collections.
	for entry in movements:
		if (entry.sales_invoice and entry.edition) or entry.app_course:
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


def statement_period(entry):
	"""The period an entry's statement covers: the one it names, or else the term its date falls in."""
	if entry.period:
		return entry.period
	return frappe.db.get_value(
		"Academic Period",
		{"period_type": "Term", "start_date": ["<=", entry.entry_date], "end_date": [">=", entry.entry_date]},
		"name",
	)


def send_statement(agreement, period, reason):
	"""DOC-23: after a settlement or a cancellation the doctor gets his statement for the period, so he knows his
	balance; by email to the address on his file. With none on file, the accountant is told instead. Returns the
	address it went to, or None."""
	from imed_erp.imederp.doctype.expense.expense import get_approvers
	from imed_erp.imederp.expense_reminders import notify

	doctor = frappe.db.get_value("Doctor Agreement", agreement, "doctor")
	email = frappe.db.get_value("Customer", doctor, "email_id")

	def tell_accountant(message):
		notify(get_approvers(), message, "Doctor Agreement", agreement, event="expense_approval")

	if not email:
		tell_accountant(
			_("{0} has no email on file, so the statement of {1} for {2} was not sent. Add his email and send it again.").format(
				doctor, agreement, period
			)
		)
		return None
	columns, data, _message, _chart, summary = execute({"agreement": agreement, "period": period})
	try:
		frappe.sendmail(
			recipients=[email],
			subject=_("Your statement for {0}: {1}").format(period, agreement),
			message=statement_html(doctor, agreement, period, columns, data, summary, reason),
			reference_doctype="Doctor Agreement",
			reference_name=agreement,
		)
	except frappe.OutgoingEmailError:
		# No email account to send from yet: the settlement stands; the accountant is told instead.
		tell_accountant(
			_("The statement of {0} for {1} was not emailed: no outgoing email account is set up (Email Account).").format(
				agreement, period
			)
		)
		return None
	return email


def statement_html(doctor, agreement, period, columns, data, summary, reason):
	esc = frappe.utils.escape_html
	head = "".join(f"<th>{esc(column['label'])}</th>" for column in columns)
	body = ""
	for row in data:
		cells = []
		for column in columns:
			value = row.get(column["fieldname"])
			if value is None or value == "":
				cells.append("<td></td>")
				continue
			formatted = frappe.format_value(value, {"fieldtype": column["fieldtype"]})
			cells.append(f"<td>{'<b>' if row.get('is_total') else ''}{esc(str(formatted))}</td>")
		body += f"<tr>{''.join(cells)}</tr>"
	totals = "".join(
		f"<p>{esc(item['label'])}: <b>{esc(frappe.format_value(item['value'], {'fieldtype': 'Currency'}))}</b></p>" for item in summary
	)
	return f"""<div dir="rtl">
		<p>{esc(_("Dear Dr. {0},").format(frappe.db.get_value("Customer", doctor, "customer_name")))}</p>
		<p>{esc(_("Your statement for {0} under {1}, sent after: {2}.").format(period, agreement, reason))}</p>
		<table border="1" cellpadding="4" style="border-collapse: collapse"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
		{totals}
	</div>"""

