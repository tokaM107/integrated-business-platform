# Bookings made before starts_at / ends_at existed (26 Oct 2026): both from the day and the two times. None of them
# crossed midnight (the old check refused an end before its start), so the end is on the same day.
import frappe


def execute():
	frappe.reload_doc("imederp", "doctype", "booking")
	frappe.db.sql(
		"""update `tabBooking` set starts_at = timestamp(booking_date, from_time), ends_at = timestamp(booking_date, to_time),
		ends_next_day = 0 where starts_at is null and booking_date is not null and from_time is not null and to_time is not null"""
	)
