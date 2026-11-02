# The booking domain's vocabulary and rules, defined once (audit of 2 Nov 2026: the "held" rule and these names
# were written in about ten places, as "in HOLDING" here and "not in (Cancelled, No Show)" there). A leaf module:
# it imports nothing of the app, so the Booking controller, its accounting, its pricing, the XStudio sync, the
# reports and the dashboards can all read it without import cycles.
#
# The statuses are the Booking DocType's own options; a test (tests/test_booking.py) fails if a status is added
# to the DocType without being placed in HOLDING or NOT_HELD here.

from datetime import datetime, timedelta

from frappe.utils import cint, get_time, getdate

from imed_erp.imederp.import_source import IMPORTED, MANUAL  # noqa: F401  (re-exported: the booking's sources)

# Statuses
TENTATIVE = "Tentative"
CONFIRMED_NO_DEPOSIT = "Confirmed"  # IMED's halls take no deposit: confirmed by the halls' staff (26 Oct 2026)
CONFIRMED_WITH_DEPOSIT = "Confirmed with Deposit"
COMPLETED = "Completed"
CANCELLED = "Cancelled"
NO_SHOW = "No Show"

# A booking holds its time unless it was cancelled or its customer did not come (its time has passed).
HOLDING = (TENTATIVE, CONFIRMED_NO_DEPOSIT, CONFIRMED_WITH_DEPOSIT, COMPLETED)
NOT_HELD = (CANCELLED, NO_SHOW)
# Still to happen or to be closed: neither completed nor cancelled.
OPEN = (TENTATIVE, CONFIRMED_NO_DEPOSIT, CONFIRMED_WITH_DEPOSIT)
# Business done: a deposit taken, or the session delivered (the money figures of the dashboard).
BUSINESS_DONE = (CONFIRMED_WITH_DEPOSIT, COMPLETED)

# Resource types
HALL = "Hall"
STUDIO_SERVICE = "Studio Service"

# Rental models of a hall booking
FIXED_RENT = "Fixed Rent"
REVENUE_SHARE = "Revenue Share"
NOT_BILLABLE = "Not Billable"


def is_held(status) -> bool:
	return status in HOLDING


def span(booking_date, from_time, to_time, ends_next_day=0) -> tuple[datetime, datetime]:
	"""(starts_at, ends_at) of a booking: the end on the next day when the booking crosses midnight."""
	day = getdate(booking_date)
	starts_at = datetime.combine(day, get_time(from_time))
	ends_at = datetime.combine(day + timedelta(days=cint(ends_next_day)), get_time(to_time))
	return starts_at, ends_at
