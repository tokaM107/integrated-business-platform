# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Outstanding Receivables (RPT-05): what customers still owe, on sales and on bookings, in three parts kept apart:
#
#   Invoiced           every submitted Sales Invoice with something still owed: ERPNext's own Outstanding Amount,
#                      which already takes off the payments, the deposits applied as advances (a booking's, ACC-04)
#                      and the credit notes made against it. A paid invoice owes nothing and is not listed; a
#                      cancelled one is not counted. A booking's invoice shows the booking beside it, once.
#   Credit             money the customer has with us, not yet set against an invoice: a payment or a deposit not
#                      applied (a cancelled booking's deposit not paid back), a credit note not applied. Shown as a
#                      negative balance, apart from what is owed.
#   Not invoiced       a booking not cancelled, not invoiced yet, with something left to pay: its price less the
#                      deposits taken. Not a receivable in the accounts until the booking is completed and invoiced;
#                      listed so the owner sees it, in its own subtotal. Its deposits are in Amount Paid here, not
#                      again under Credit.
#
# Each part has its subtotal row. Invoiced and Credit are what the ledger holds on the customers' account for these
# documents; Not invoiced is the bookings' own figures.
#
# The owner and the accountant only (the report's roles, and owner_figures.check_reader).

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today

from imed_erp.imederp.business_figures import company, subtree
from imed_erp.imederp.owner_figures import check_reader

INVOICED, CREDIT, NOT_INVOICED = "Invoiced", "Credit", "Not Invoiced"
KINDS = (INVOICED, CREDIT, NOT_INVOICED)
# What each part is called on screen: "Credit" alone is ERPNext's accounting credit (دائن).
KIND_LABELS = {INVOICED: "Invoiced", CREDIT: "Customer Credit", NOT_INVOICED: "Not Invoiced"}
STATUSES = ("Unpaid", "Partly Paid", "Overdue")


def execute(filters=None):
	check_reader()
	filters = frappe._dict(filters or {})
	if filters.payment_status and filters.payment_status not in STATUSES:
		frappe.throw(_("Choose Unpaid, Partly Paid or Overdue."))
	if filters.kind and filters.kind not in KINDS:
		frappe.throw(_("Choose what to show."))
	if filters.from_date and filters.to_date and getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date must be before To Date."))
	rows = get_rows(filters)
	return get_columns(), with_subtotals(rows), None, None, get_summary(rows)


def get_columns():
	return [
		{"label": _("Kind"), "fieldname": "kind", "fieldtype": "Data", "width": 110},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 170,
		},
		{
			"label": _("Business"),
			"fieldname": "cost_center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 160,
		},
		{"label": _("Document Type"), "fieldname": "voucher_type", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Reference"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 160,
		},
		{
			"label": _("Booking"),
			"fieldname": "booking",
			"fieldtype": "Link",
			"options": "Booking",
			"width": 120,
		},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 110},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Amount Paid"), "fieldname": "paid", "fieldtype": "Currency", "width": 120},
		{"label": _("Outstanding"), "fieldname": "outstanding", "fieldtype": "Currency", "width": 120},
		{"label": _("Payment Status"), "fieldname": "payment_status", "fieldtype": "Data", "width": 120},
		{"label": _("Days Overdue"), "fieldname": "age", "fieldtype": "Int", "width": 110},
	]


def get_rows(filters):
	values = {"company": company()}
	if filters.cost_center:
		values["cost_centers"] = tuple(row.name for row in subtree(filters.cost_center))
	if filters.customer:
		values["customer"] = filters.customer
	if filters.from_date:
		values["from_date"] = filters.from_date
	if filters.to_date:
		values["to_date"] = filters.to_date

	def where(date_field, cost_center_field, customer_field):
		parts = []
		if filters.cost_center:
			parts.append(f"{cost_center_field} in %(cost_centers)s")
		if filters.customer:
			parts.append(f"{customer_field} = %(customer)s")
		if filters.from_date:
			parts.append(f"{date_field} >= %(from_date)s")
		if filters.to_date:
			parts.append(f"{date_field} <= %(to_date)s")
		return "".join(f" and {part}" for part in parts)

	rows = []
	if filters.kind in (None, "", INVOICED, CREDIT):
		# A sale's business is its invoice's, or its first line's when the invoice names none.
		invoices = frappe.db.sql(
			f"""select * from (
				select si.name, si.customer, si.posting_date, si.due_date, si.is_return,
					if(si.rounded_total != 0 and si.disable_rounded_total = 0, si.rounded_total, si.grand_total) as amount,
					si.outstanding_amount,
					coalesce(si.cost_center, (select item.cost_center from `tabSales Invoice Item` item
						where item.parent = si.name order by item.idx limit 1)) as cost_center,
					si.custom_booking as booking
				from `tabSales Invoice` si
				where si.docstatus = 1 and si.company = %(company)s and si.outstanding_amount != 0
			) si
			where 1 = 1 {where("si.posting_date", "si.cost_center", "si.customer")}
			order by si.posting_date, si.name""",
			values,
			as_dict=True,
		)
		for invoice in invoices:
			if invoice.outstanding_amount > 0 and not invoice.is_return:
				rows.append(invoice_row(invoice))
			elif invoice.outstanding_amount < 0:
				rows.append(credit_row("Sales Invoice", invoice.name, invoice, -invoice.outstanding_amount))

	# Bookings not invoiced yet, whatever the filters: a deposit on one is in its Amount Paid, never a credit.
	open_bookings = set(
		frappe.db.sql_list(
			"""select name from `tabBooking`
			where status not in ('Cancelled', 'No Show') and coalesce(sales_invoice, '') = ''"""
		)
	)
	if filters.kind in (None, "", NOT_INVOICED):
		bookings = frappe.db.sql(
			f"""select name, customer, booking_date, cost_center, total_amount, paid_amount, outstanding_amount
			from `tabBooking`
			where status not in ('Cancelled', 'No Show') and coalesce(sales_invoice, '') = ''
				and outstanding_amount > 0
			{where("booking_date", "cost_center", "customer")}
			order by booking_date, name""",
			values,
			as_dict=True,
		)
		rows += [booking_row(booking) for booking in bookings]

	if filters.kind in (None, "", CREDIT):
		payments = frappe.db.sql(
			f"""select name, party as customer, posting_date, cost_center, paid_amount as amount, unallocated_amount,
				custom_booking as booking
			from `tabPayment Entry`
			where docstatus = 1 and company = %(company)s and payment_type = 'Receive' and party_type = 'Customer'
				and unallocated_amount > 0
			{where("posting_date", "cost_center", "party")}
			order by posting_date, name""",
			values,
			as_dict=True,
		)
		rows += [
			credit_row("Payment Entry", payment.name, payment, payment.unallocated_amount)
			for payment in payments
			if payment.booking not in open_bookings
		]

	if filters.payment_status:
		rows = [row for row in rows if row["kind"] != CREDIT and matches(row, filters.payment_status)]
	order = {kind: index for index, kind in enumerate(KINDS)}
	rows.sort(key=lambda row: order[row["kind_key"]])
	return rows


def invoice_row(invoice):
	paid = flt(invoice.amount - invoice.outstanding_amount, 2)
	overdue = invoice.due_date and getdate(invoice.due_date) < getdate(today())
	return {
		"kind_key": INVOICED,
		"kind": kind_label(INVOICED),
		"customer": invoice.customer,
		"cost_center": invoice.cost_center,
		"voucher_type": "Sales Invoice",
		"voucher_no": invoice.name,
		"booking": invoice.booking,
		"posting_date": invoice.posting_date,
		"due_date": invoice.due_date,
		"amount": invoice.amount,
		"paid": paid,
		"outstanding": flt(invoice.outstanding_amount, 2),
		"status_key": "Partly Paid" if paid > 0 else "Unpaid",
		"payment_status": _("Partly Paid") if paid > 0 else _("Unpaid"),
		"overdue": bool(overdue),
		"age": date_diff(today(), invoice.due_date) if overdue else 0,
	}


def booking_row(booking):
	paid = flt(booking.paid_amount, 2)
	return {
		"kind_key": NOT_INVOICED,
		"kind": kind_label(NOT_INVOICED),
		"customer": booking.customer,
		"cost_center": booking.cost_center,
		"voucher_type": "Booking",
		"voucher_no": booking.name,
		"booking": booking.name,
		"posting_date": booking.booking_date,
		"due_date": None,
		"amount": booking.total_amount,
		"paid": paid,
		"outstanding": flt(booking.outstanding_amount, 2),
		"status_key": "Partly Paid" if paid > 0 else "Unpaid",
		"payment_status": _("Deposit Paid") if paid > 0 else _("Unpaid"),
		"overdue": False,
		"age": 0,
	}


def credit_row(voucher_type, name, doc, credit):
	return {
		"kind_key": CREDIT,
		"kind": kind_label(CREDIT),
		"customer": doc.customer,
		"cost_center": doc.cost_center,
		"voucher_type": voucher_type,
		"voucher_no": name,
		"booking": doc.get("booking"),
		"posting_date": doc.posting_date,
		"due_date": None,
		"amount": abs(flt(doc.amount)),
		"paid": None,
		"outstanding": -flt(credit, 2),
		"status_key": None,
		"payment_status": _("Not Applied Yet"),
		"overdue": False,
		"age": 0,
	}


def kind_label(kind):
	return _(KIND_LABELS[kind])


def matches(row, status):
	if status == "Overdue":
		return row["overdue"]
	return row["status_key"] == status


def subtotal(rows, kind):
	return flt(sum(row["outstanding"] for row in rows if row["kind_key"] == kind), 2)


def with_subtotals(rows):
	data = []
	for kind in KINDS:
		part = [row for row in rows if row["kind_key"] == kind]
		if not part:
			continue
		data += part
		data.append(
			{
				"kind": _("Total: {0}").format(kind_label(kind)),
				"amount": flt(sum(flt(row["amount"]) for row in part), 2),
				"paid": flt(sum(flt(row["paid"]) for row in part), 2) if kind != CREDIT else None,
				"outstanding": subtotal(part, kind),
				"is_subtotal": 1,
			}
		)
	return data


def get_summary(rows):
	invoiced = subtotal(rows, INVOICED)
	credit = subtotal(rows, CREDIT)
	overdue = flt(sum(row["outstanding"] for row in rows if row["overdue"]), 2)
	return [
		{
			"label": _("Owed on Invoices"),
			"value": invoiced,
			"datatype": "Currency",
			"indicator": "Red" if invoiced else "Green",
		},
		{
			"label": _("Of Which Overdue"),
			"value": overdue,
			"datatype": "Currency",
			"indicator": "Red" if overdue else "Green",
		},
		{"label": _("Customers' Credit"), "value": abs(credit), "datatype": "Currency", "indicator": "Blue"},
		{
			"label": _("Bookings Not Invoiced Yet"),
			"value": subtotal(rows, NOT_INVOICED),
			"datatype": "Currency",
			"indicator": "Orange",
		},
	]
