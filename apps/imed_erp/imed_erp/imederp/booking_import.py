# Bookings received from the booking system (STU-06, STU-14, INT-06), for the import to call once its access is
# decided (STU-11). Not exposed to the API: an integration job calls import_bookings with the rows it read.
#
# Each booking keeps the system's name and its id there (Booking source_system, external_id; import_key unique),
# so a booking sent again is recognised:
#   new key                 inserted as an Imported booking, with the same checks as one entered by hand
#                           (resource, times, amounts, status, no overlap with any booking, manual or imported)
#   key already in, same    skipped
#   key already in, changed listed as changed and NOT overwritten (INT-01 / STU-09: how changes are taken over is
#                           still to decide; nothing is replaced silently)
#   anything wrong          the row fails with its reason and the others go on; nothing of it is saved
# The customer is found by phone, one customer per number (CRM-04, STU-10). One not found fails the row: no
# customer is made from an import until that is decided.
#
# Row: external_id, resource, customer_phone, booking_date, from_time, to_time, total_amount, paid_amount,
# status (Tentative, Confirmed with Deposit, Completed, Cancelled, No Show), cancellation_reason, notes.

import frappe
from frappe import _
from frappe.utils import cstr, flt, get_time, getdate

from imed_erp.imederp.customers import customer_with_phone, normalize_phone

COMPARED = ("resource", "customer", "booking_date", "from_time", "to_time", "total_amount", "paid_amount", "status", "cancellation_reason")


def import_bookings(source_system, rows):
	"""{"inserted": [booking], "skipped": [external_id], "changed": [(external_id, booking, [fields])],
	"failed": [(external_id, reason)]}"""
	result = {"inserted": [], "skipped": [], "changed": [], "failed": []}
	if not cstr(source_system).strip():
		frappe.throw(_("Name the system the bookings come from."))
	for row in rows:
		row = frappe._dict(row)
		external_id = cstr(row.external_id).strip()
		frappe.db.savepoint("booking_import_row")
		try:
			if not external_id:
				frappe.throw(_("The row has no id from the booking system."))
			values = booking_values(row)
			existing = frappe.db.get_value("Booking", {"import_key": f"{source_system}:{external_id}"}, "name")
			if existing:
				changed = differences(existing, values)
				if changed:
					result["changed"].append((external_id, existing, changed))
				else:
					result["skipped"].append(external_id)
				continue
			doc = frappe.get_doc({"doctype": "Booking", **values, "source_system": source_system, "external_id": external_id})
			doc.flags.from_import = True
			doc.insert()
			result["inserted"].append(doc.name)
		except Exception as e:
			try:
				frappe.db.rollback(save_point="booking_import_row")
			except Exception:
				# A deadlock makes the database roll the whole transaction back, savepoint and all: the bookings counted
				# as inserted above are gone too. Say so rather than return a result that is no longer true; running
				# the import again is safe, since what is already in is skipped by its key.
				frappe.db.rollback()
				frappe.throw(
					_("The import stopped at {0}: another booking was saved at the same moment, and nothing of this run was kept. Run it again.").format(
						external_id or _("a row without an id")
					),
					title=_("Import Interrupted"),
				)
			frappe.clear_messages()
			result["failed"].append((external_id, cstr(getattr(e, "message", None) or e)))
	return result


def booking_values(row):
	key = normalize_phone(row.customer_phone)
	if not key:
		frappe.throw(_("The row has no customer phone."))
	customer = customer_with_phone(key)
	if not customer:
		frappe.throw(_("No customer has the phone number {0}. Add the customer first.").format(row.customer_phone))
	return {
		"resource": row.resource,
		"customer": customer.name,
		"booking_date": row.booking_date,
		"from_time": row.from_time,
		"to_time": row.to_time,
		"total_amount": flt(row.total_amount),
		"paid_amount": flt(row.paid_amount),
		"status": row.status or "Tentative",
		"cancellation_reason": row.cancellation_reason,
		"notes": row.notes,
	}


def differences(name, values):
	current = frappe.db.get_value("Booking", name, list(COMPARED), as_dict=True)
	normal = {
		"booking_date": lambda v: getdate(v) if v else None,
		"from_time": lambda v: get_time(v) if v else None,
		"to_time": lambda v: get_time(v) if v else None,
		"total_amount": lambda v: flt(v, 2),
		"paid_amount": lambda v: flt(v, 2),
	}
	same = lambda field, v: normal.get(field, lambda x: cstr(x).strip() or None)(v)
	return [field for field in COMPARED if same(field, current.get(field)) != same(field, values.get(field))]
