# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The halls' bookings (HAL-06): by day and hall, the attendees, the admission price, the rent, what was collected,
# the cancellations and what is still unpaid. One row a booking, a total at the end.
#
#   Rent         the booking's total: the hall's hours and extras (a revenue-share booking pays no rent, HAL-12).
#   Collected    a fixed-rent booking: what the customer paid; a revenue share: what was collected at the door.
#   Unpaid       what is still owed (owner_dashboard.unpaid: a completed booking is paid on its invoice); nothing on a
#                cancelled booking or a no-show, which keep their deposit.
# A branch manager sees her own halls (User Permissions on the booking's cost center).

import frappe
from frappe import _
from frappe.utils import flt

CANCELLED = ("Cancelled", "No Show")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "booking_date", "fieldtype": "Date", "width": 100},
		{"label": _("Hall"), "fieldname": "resource", "fieldtype": "Link", "options": "Booking Resource", "width": 160},
		{"label": _("Booking"), "fieldname": "name", "fieldtype": "Link", "options": "Booking", "width": 140},
		{"label": _("Activity"), "fieldname": "activity", "fieldtype": "Data", "width": 160},
		{"label": _("Rental Model"), "fieldname": "rental_model", "fieldtype": "Data", "width": 110},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Attendees"), "fieldname": "attendees", "fieldtype": "Int", "width": 90},
		{"label": _("Admission Price"), "fieldname": "admission_price", "fieldtype": "Currency", "width": 110},
		{"label": _("Rent"), "fieldname": "rent", "fieldtype": "Currency", "width": 110},
		{"label": _("Collected"), "fieldname": "collected", "fieldtype": "Currency", "width": 110},
		{"label": _("Unpaid"), "fieldname": "unpaid", "fieldtype": "Currency", "width": 110},
		{"label": _("Cancelled"), "fieldname": "cancelled", "fieldtype": "Int", "width": 90},
	]


def get_data(filters):
	conditions = {"resource_type": "Hall"}
	if filters.from_date and filters.to_date:
		conditions["booking_date"] = ("between", (filters.from_date, filters.to_date))
	if filters.hall:
		conditions["resource"] = filters.hall
	rows = []
	for b in frappe.get_list(
		"Booking",
		filters=conditions,
		fields=[
			"name", "booking_date", "resource", "activity", "rental_model", "status", "attendees", "admission_price",
			"total_amount", "paid_amount", "collected_amount", "outstanding_amount", "sales_invoice",
		],
		order_by="booking_date, from_time",
	):
		cancelled = b.status in CANCELLED
		share = b.rental_model == "Revenue Share"
		rows.append(
			{
				**{k: b[k] for k in ("booking_date", "resource", "name", "activity", "status", "attendees", "admission_price")},
				"rental_model": _(b.rental_model) if b.rental_model else "",
				"status": _(b.status),
				"rent": 0 if cancelled else flt(b.total_amount),
				"collected": flt(b.collected_amount) if share else flt(b.paid_amount),
				"unpaid": 0 if cancelled else unpaid(b),
				"cancelled": 1 if cancelled else 0,
			}
		)
	return rows


def unpaid(booking):
	if booking.status == "Completed" and booking.sales_invoice:
		invoice = frappe.db.get_value("Sales Invoice", booking.sales_invoice, ["docstatus", "outstanding_amount"], as_dict=True)
		if invoice and invoice.docstatus == 1:
			return flt(invoice.outstanding_amount)
	return flt(booking.outstanding_amount)
