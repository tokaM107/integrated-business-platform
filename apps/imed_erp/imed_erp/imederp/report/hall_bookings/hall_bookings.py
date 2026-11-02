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

from imed_erp.imederp.booking_rules import COMPLETED, HALL, REVENUE_SHARE
from imed_erp.imederp.booking_rules import NOT_HELD as CANCELLED



def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "booking_date", "fieldtype": "Date", "width": 100},
		{"label": _("Hall"), "fieldname": "resource", "fieldtype": "Link", "options": "Booking Resource", "width": 160},
		{"label": _("Booking"), "fieldname": "name", "fieldtype": "Link", "options": "Booking", "width": 140},
		{"label": _("Activity"), "fieldname": "activity", "fieldtype": "Data", "width": 160},
		{"label": _("Hall Booking Type"), "fieldname": "hall_booking_type", "fieldtype": "Data", "width": 140},
		{"label": _("Doctor / Lecturer"), "fieldname": "doctor", "fieldtype": "Link", "options": "Customer", "width": 140},
		{"label": _("Hours"), "fieldname": "hours", "fieldtype": "Float", "width": 70},
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
	conditions = {"resource_type": HALL}
	if filters.from_date and filters.to_date:
		conditions["booking_date"] = ("between", (filters.from_date, filters.to_date))
	if filters.hall:
		conditions["resource"] = filters.hall
	bookings = frappe.get_list(
		"Booking",
		filters=conditions,
		fields=[
			"name", "booking_date", "resource", "activity", "rental_model", "status", "attendees", "admission_price",
			"total_amount", "paid_amount", "collected_amount", "outstanding_amount", "sales_invoice", "hall_booking_type", "doctor", "hours",
		],
		order_by="booking_date, from_time",
	)
	invoices = invoices_of(bookings)
	rows = []
	for b in bookings:
		cancelled = b.status in CANCELLED
		share = b.rental_model == REVENUE_SHARE
		rows.append(
			{
				**{k: b[k] for k in ("booking_date", "resource", "name", "activity", "status", "attendees", "admission_price", "doctor", "hours")},
				"hall_booking_type": _(b.hall_booking_type) if b.hall_booking_type else "",
				"rental_model": _(b.rental_model) if b.rental_model else "",
				"status": _(b.status),
				"rent": 0 if cancelled else flt(b.total_amount),
				"collected": flt(b.collected_amount) if share else flt(b.paid_amount),
				"unpaid": 0 if cancelled else unpaid(b, invoices),
				"cancelled": 1 if cancelled else 0,
			}
		)
	return rows


def invoices_of(bookings):
	"""The submitted invoices of the completed bookings, read once for the whole report (was one query a row)."""
	names = list({b.sales_invoice for b in bookings if b.status == COMPLETED and b.sales_invoice})
	if not names:
		return {}
	return {
		row.name: flt(row.outstanding_amount)
		for row in frappe.get_all("Sales Invoice", filters={"name": ("in", names), "docstatus": 1}, fields=["name", "outstanding_amount"])
	}


def unpaid(booking, invoices):
	if booking.status == COMPLETED and booking.sales_invoice in invoices:
		return invoices[booking.sales_invoice]
	return flt(booking.outstanding_amount)
