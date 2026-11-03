# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# XStudio's rows as this system's values. Pure functions: nothing here reads or writes the database, so each rule
# is tested on its own (test_xstudio_sync.py).
#
# Times. XStudio keeps starts_at/ends_at as instants (Postgres timestamptz, sent as ISO in UTC) and works in
# Africa/Cairo (db.js TZ). A booking here is a day with two times on the studio's clock, so the instants are turned
# into Cairo time, whatever this site's own time zone is. XStudio lets a booking run to midnight (a hall's
# close_minute may be 1440): such a booking ends at 00:00 of the next day, which the day-and-times model cannot
# hold. It is kept to 23:59:59 on its day, marked Crosses Midnight, with its exact instants and XStudio's own hours
# on the booking: nothing is lost or silently rounded, and the calendar shows it on the right day.
#
# Statuses. XStudio: pending, confirmed, completed, cancelled; confirmed says nothing about money. Here, Confirmed
# with Deposit means a deposit was paid (STU-08). So a confirmed booking with nothing paid is Tentative here, and
# XStudio's own status is kept on the booking (XStudio Status). No Show does not exist in XStudio.
#
# Money. price_total is XStudio's full price, amount_due what the customer owes after package hours and discounts,
# amount_paid what was recorded as paid. Total Amount here is what is owed (amount_due); the full price, the
# payment status and what was paid are kept in their own fields, for reading only: no accounting entry is made.

import hashlib
import json
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from frappe.utils import cint, cstr, flt

SOURCE = "xstudio"
CAIRO = ZoneInfo("Africa/Cairo")
STATUS = {"pending": "Tentative", "confirmed": "Tentative", "completed": "Completed", "cancelled": "Cancelled"}
CONFIRMED_WITH_DEPOSIT = "Confirmed with Deposit"
LAST_SECOND = time(23, 59, 59)
NO_PHONE = "no-phone-"
REELS = "reels"


def import_key(external_id):
	return f"{SOURCE}:{external_id}"


def parse_instant(value):
	"""An ISO instant from XStudio ('2026-10-20T12:00:00.000Z' or with an offset) as an aware datetime."""
	text = cstr(value).strip()
	if not text:
		return None
	if text.endswith("Z"):
		text = text[:-1] + "+00:00"
	parsed = datetime.fromisoformat(text)
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	return parsed


def to_cairo(value):
	instant = parse_instant(value)
	return instant.astimezone(CAIRO) if instant else None


def naive_cairo(value):
	"""The instant as Cairo wall-clock time without a zone, as a Datetime field holds it."""
	local = to_cairo(value)
	return local.replace(tzinfo=None) if local else None


def cairo_day_start(day):
	"""Midnight at the start of `day` (a date) in Cairo, as an aware instant."""
	return datetime.combine(day, time.min, tzinfo=CAIRO)


def iso_utc(instant):
	return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def booking_times(booking):
	"""(booking_date, from_time, to_time, crosses_midnight) in Cairo. A booking ending at 00:00 of the next day,
	or later, is kept to the last second of its day and marked."""
	starts, ends = to_cairo(booking.get("starts_at")), to_cairo(booking.get("ends_at"))
	if not starts or not ends:
		raise ValueError("the booking has no starts_at or ends_at")
	if ends <= starts:
		raise ValueError("the booking ends before it starts")
	crosses = ends.date() > starts.date()
	to_time = LAST_SECOND if crosses else ends.time().replace(microsecond=0)
	return starts.date(), starts.time().replace(microsecond=0), to_time, crosses


def booking_status(booking):
	"""XStudio's status and what was paid, as the status here."""
	status = STATUS.get(cstr(booking.get("status")).lower())
	if not status:
		raise ValueError(f"unknown XStudio status {booking.get('status')!r}")
	if status == "Tentative" and cstr(booking.get("status")).lower() == "confirmed" and flt(booking.get("amount_paid")) > 0:
		return CONFIRMED_WITH_DEPOSIT
	return status


def cancellation_reason(booking):
	by = {"staff": "the studio", "customer": "the customer"}.get(cstr(booking.get("cancelled_by")), "XStudio")
	note = cstr(booking.get("cancel_note")).strip()
	return f"Cancelled in XStudio by {by}" + (f": {note}" if note else "")


def booking_amounts(booking):
	"""(total_amount, paid_amount): what is owed and what was paid. XStudio lets amount_paid exceed amount_due (an
	overpayment, or a price still to be agreed); the total is then raised to it so the booking can be kept, and the
	source figures stay in their own fields."""
	due, paid = flt(booking.get("amount_due"), 2), flt(booking.get("amount_paid"), 2)
	return max(due, paid), paid


def service_key(booking):
	"""The service as one text: smartboard:86, podcast:2, svc:<id>#<n>, session, reels..."""
	kind = cstr(booking.get("booking_type")) or "session"
	if kind == "smartboard" and booking.get("screen_size"):
		return f"smartboard:{cint(booking.get('screen_size'))}"
	if kind == "podcast" and booking.get("cameras"):
		return f"podcast:{cint(booking.get('cameras'))}"
	return kind


def booking_payload_hash(booking):
	"""What change detection compares: XStudio's whole row, less the fields of the join that say nothing new."""
	kept = {k: v for k, v in booking.items() if k not in ("hall_name", "package_name")}
	return hashlib.sha256(json.dumps(kept, sort_keys=True, default=str).encode()).hexdigest()


def customer_from_booking(booking):
	"""The customer as the booking denormalises it: XStudio's id, name and phone."""
	return {"id": booking.get("customer_id"), "name": cstr(booking.get("customer_name")).strip(), "phone": cstr(booking.get("customer_phone")).strip()}


def real_phone(phone):
	"""XStudio gives imported customers a placeholder phone (no-phone-xxxx): that is no number."""
	phone = cstr(phone).strip()
	return None if not phone or phone.startswith(NO_PHONE) else phone


def package_unit(package):
	"""A reels bundle counts reels in hours_total/hours_remaining (bookingService.js pkgCatFor): its unit is Reel."""
	category = cstr(package.get("category")).lower()
	name = cstr(package.get("name")).lower()
	if category == REELS or (not category and ("reel" in name or "ريلز" in name)):
		return "Reel"
	return "Hour"


def package_status(package):
	"""Active, Used Up or Cancelled, from XStudio's remaining balance and expiry."""
	if flt(package.get("hours_remaining")) <= 0:
		return "Used Up"
	expires = parse_instant(package.get("expires_at"))
	if expires and expires <= datetime.now(timezone.utc):
		return "Used Up"
	return "Active"


def payments_summary(package):
	"""XStudio's payments on a package carry no id (routes.js:912-914): a readable summary, nothing more."""
	rows = package.get("payments") or []
	parts = []
	for row in rows:
		when = naive_cairo(row.get("created_at"))
		parts.append(f"{flt(row.get('amount'), 2):g} ({cstr(row.get('method')) or 'cash'}, {when.strftime('%Y-%m-%d') if when else '?'})")
	return "; ".join(parts) if parts else ""


def window_edges(today_cairo, lookback_days, lookahead_days):
	"""[from, to) as aware instants: midnight Cairo `lookback_days` back, to midnight after `lookahead_days`."""
	start = cairo_day_start(today_cairo - timedelta(days=cint(lookback_days)))
	end = cairo_day_start(today_cairo + timedelta(days=cint(lookahead_days) + 1))
	return start, end
