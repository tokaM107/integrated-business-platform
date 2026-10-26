# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A booking of a hall or a studio service by the hour (HAL-02, STU-01), with its status (STU-08) and where it came
# from (STU-14): entered here (WhatsApp, walk-in) or imported from the booking system, which stays the source of the
# studio's appointments (requirements v1.2 §4.8).
#
#   HAL-02  a hall booking records the activity and the responsible person's name and phone.
#   STU-08  Tentative, Confirmed with Deposit, Completed, Cancelled (with its reason), No Show.
#   HAL-04, STU-14  two bookings of the same resource never overlap, whatever their source.
#
# HAL-10, STU-02: the Booking calendar (Bookings > Calendar, booking_calendar.js) shows a day or a week of them:
# get_events below.
#
# A booking entered here is priced when it is saved (HAL-03, STU-04, STU-05, HAL-11, HAL-12: booking_pricing.py);
# a hall booking names its rental model, and a revenue-share one its attendees, admission price, what was collected
# and the lecturer's share (HAL-08, HAL-12). Its deposits and payments are Payment Entries into its business's cash
# box, and Completed makes its invoice (STU-03, ACC-04: booking_accounts.py). An imported booking keeps the
# booking system's amounts and posts nothing.

from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, get_datetime, get_time, getdate, now_datetime

from imed_erp.imederp.branches import check_has_branch
from imed_erp.imederp.booking_accounts import complete, payments_total, posted, treasury_of
from imed_erp.imederp.booking_pricing import REVENUE_SHARE, price_booking, pricing_key, revenue_share
from imed_erp.imederp.customers import normalize_phone

TENTATIVE, CONFIRMED, COMPLETED, CANCELLED, NO_SHOW = "Tentative", "Confirmed with Deposit", "Completed", "Cancelled", "No Show"
# IMED's halls take no deposit: a hall booking is confirmed by the halls' staff, which is not a payment (26 Oct 2026).
CONFIRMED_NO_DEPOSIT = "Confirmed"
# The bookings that hold their time: a cancelled booking frees it, and so does a no-show, whose time has passed.
HOLDING = (TENTATIVE, CONFIRMED_NO_DEPOSIT, CONFIRMED, COMPLETED)
HALL = "Hall"
NOT_BILLABLE = "Not Billable"
DOCTOR_GROUP = "طبيب"
# IMED's own halls (never XStudio's rooms): what a hall is used for, and what that fixes about its money.
#   Fixed-fee Rental -> Fixed Rent; Revenue Share -> Revenue Share; Internal Meeting and Maintenance Block -> Not
#   Billable; an Internal Course or Lecture is Not Billable unless chosen otherwise (its fees are the app's or the
#   course's, never counted twice); an External Lecturer is rented the hall or shares the revenue, never free.
HALL_TYPES = ("Internal Course or Lecture", "External Lecturer", "Fixed-fee Rental", "Revenue Share", "Internal Meeting", "Maintenance Block")
FORCED_MODEL = {"Fixed-fee Rental": "Fixed Rent", "Revenue Share": "Revenue Share", "Internal Meeting": NOT_BILLABLE, "Maintenance Block": NOT_BILLABLE}
MAINTENANCE = "Maintenance Block"
MANUAL, IMPORTED = "Manual", "Imported"
SOURCE_FIELDS = ("source", "source_system", "external_id", "import_key")


def on_doctype_update():
	"""The overlap check reads a resource's bookings around an instant, the reports a day's: an index on each."""
	frappe.db.add_index("Booking", ["resource", "starts_at"])
	frappe.db.add_index("Booking", ["resource", "booking_date"])


def check_own_business(cost_center):
	"""A booking belongs to its resource's business (cost center), set here from the resource. Frappe checks a
	user's restrictions on the fields as they were sent, before this, when the cost center is still empty, so it is
	checked again: a branch manager books only their own business's resources."""
	from frappe.permissions import get_user_permissions

	# The same restrictions Frappe applies to a booking: those for every screen, or for bookings.
	allowed = [
		p.get("doc")
		for p in get_user_permissions(frappe.session.user).get("Cost Center", [])
		if not p.get("applicable_for") or p.get("applicable_for") == "Booking"
	]
	check_has_branch(allowed)
	if allowed and cost_center not in allowed:
		frappe.throw(
			_("{0} is not your business. You can book for: {1}.").format(cost_center, ", ".join(sorted(allowed))),
			frappe.PermissionError,
			title=_("Not Your Business"),
		)


class Booking(Document):
	def validate(self):
		self.check_source()
		self.check_times()
		self.check_resource()
		self.check_hall_type()
		self.check_hall_details()
		self.check_hour_package()
		if self.source == MANUAL:
			self.check_rental_model()
			self.check_posted()
			if self.not_billable():
				self.price_nothing()
			else:
				price_booking(self)
			self.set_paid()
		else:
			self.check_amounts()
		self.check_status()
		self.check_overlap()

	def on_update(self):
		# Prepaid hours: what the booking holds of its package follows it (studio_hour_package.py).
		if self.source == MANUAL and (self.hour_package or (self.get_doc_before_save() and self.get_doc_before_save().hour_package)):
			from imed_erp.imederp.doctype.studio_hour_package.studio_hour_package import draw

			draw(self)
		# Completed: the invoice (or the revenue-share entry), once (booking_accounts.py).
		complete(self)

	def check_hour_package(self):
		"""A session on a teacher's prepaid hours (22 Oct 2026): its exact length comes off the package while it holds
		its time; hours beyond what is left only once the accountant or the owner decides they are billed."""
		if not self.hour_package:
			self.package_hours = self.extra_hours = 0
			self.bill_extra_hours, self.extra_hours_approved_by = 0, None
			return
		from imed_erp.imederp.booking_pricing import exact_hours
		from imed_erp.imederp.doctype.studio_hour_package.studio_hour_package import ACCOUNTS_ROLES, plan

		if self.source != MANUAL:
			if self.flags.from_import:
				# The source keeps the package's ledger (the XStudio sync brings its rows): the booking only shows
				# what the source deducted; nothing is planned or drawn here.
				self.package_hours, self.extra_hours = flt(self.package_hours, 4), 0
				self.bill_extra_hours, self.extra_hours_approved_by = 0, None
				return
			frappe.throw(_("An imported booking is priced by the booking system; it draws on no prepaid hours."))
		if self.package:
			frappe.throw(_("A session on prepaid hours takes no price package."), title=_("Two Packages"))
		before = self.get_doc_before_save()
		authorised = bool(set(ACCOUNTS_ROLES) & set(frappe.get_roles()))
		decided_before = bool(before and before.bill_extra_hours)
		if before and decided_before and not authorised and (
			flt(before.hours) != flt(self.hours) or before.hour_package != self.hour_package
		):
			# The decision was for the session as it was; a longer or moved one is decided again.
			self.bill_extra_hours = 0
		if self.bill_extra_hours and not (decided_before and before.bill_extra_hours == self.bill_extra_hours and self.extra_hours_approved_by):
			if not authorised:
				frappe.throw(
					_("Only the accountant or the owner decides to bill hours beyond the package."), frappe.PermissionError, title=_("Decision Needed")
				)
			self.extra_hours_approved_by = frappe.session.user
		if not self.bill_extra_hours:
			self.extra_hours_approved_by = None
		self.package_hours, self.extra_hours = plan(self, exact_hours(self), self.status in HOLDING)

	def check_source(self):
		"""Only the import makes an imported booking, and only the import changes it (INT-01: what comes from the
		booking system is changed there)."""
		if self.flags.from_import:
			self.source = IMPORTED
			if not (self.source_system and self.external_id):
				frappe.throw(_("An imported booking needs its source system and its id there."))
			self.import_key = f"{self.source_system}:{self.external_id}"
			return
		if self.is_new():
			self.source = MANUAL
			for field in SOURCE_FIELDS[1:]:
				self.set(field, None)
			return
		before = self.get_doc_before_save()
		if before and before.source == IMPORTED:
			frappe.throw(
				_("{0} was imported from {1}. Change it there; the next import brings the change.").format(self.name, before.source_system),
				title=_("Imported Booking"),
			)
		for field in SOURCE_FIELDS:
			self.set(field, before.get(field) if before else None)

	def check_resource(self):
		resource = frappe.db.get_value("Booking Resource", self.resource, ["disabled", "resource_type", "cost_center"], as_dict=True)
		if not resource:
			frappe.throw(_("Resource {0} not found.").format(self.resource))
		self.resource_type, self.cost_center = resource.resource_type, resource.cost_center
		check_own_business(self.cost_center)
		if self.source == MANUAL:
			# ACC-04: the business's cash box takes its payments; a business without one is told now, not at payment.
			self.treasury = treasury_of(self.cost_center)
		if resource.disabled and self.status in HOLDING and self.takes_new_time():
			frappe.throw(_("{0} is disabled and takes no new bookings.").format(self.resource), title=_("Resource Disabled"))

	def takes_new_time(self):
		"""New, moved to another resource, day or time, or taken back from Cancelled or No Show: it holds time it did
		not hold before. A booking that only changes its status to Cancelled, its amounts or its notes does not."""
		before = self.get_doc_before_save()
		if self.is_new() or not before:
			return True
		if before.status not in HOLDING:
			return True
		same_time = (
			before.resource == self.resource
			and get_datetime(before.starts_at) == get_datetime(self.starts_at)
			and get_datetime(before.ends_at) == get_datetime(self.ends_at)
		)
		return not same_time

	def check_times(self):
		# This runs before Frappe's own check of required values: a booking sent without its day or times (through
		# the API) is told so here, not failed on reading them.
		missing = [_(self.meta.get_label(f)) for f in ("booking_date", "from_time", "to_time") if not self.get(f)]
		if missing:
			frappe.throw(_("Enter the booking's {0}.").format(", ".join(missing)), frappe.MandatoryError, title=_("Missing Value"))
		starts, ends = get_time(self.from_time), get_time(self.to_time)
		if ends == starts:
			frappe.throw(_("The booking ends at {0}, the moment it starts: it has no length.").format(self.to_time), title=_("Wrong Times"))
		# An end earlier than the start is the next day: a booking across midnight (at most 24 hours by construction).
		self.ends_next_day = 1 if ends < starts else 0
		self.starts_at = datetime.combine(getdate(self.booking_date), starts)
		self.ends_at = datetime.combine(getdate(self.booking_date) + timedelta(days=self.ends_next_day), ends)
		self.hours = flt((self.ends_at - self.starts_at).total_seconds() / 3600, 2)

	def not_billable(self):
		return self.resource_type == HALL and self.rental_model == NOT_BILLABLE

	def check_hall_type(self):
		"""IMED's halls: the booking's type, the money it fixes, the doctor and course links, the capacity."""
		if self.resource_type != HALL:
			self.hall_booking_type, self.doctor, self.course, self.expected_attendees, self.capacity = None, None, None, 0, 0
			self.financial_review, self.financial_note = 0, None
			return
		if not self.hall_booking_type:
			# Bookings sent without a type (the API, the import, the older screens): the rental model says enough.
			self.hall_booking_type = {"Fixed Rent": "Fixed-fee Rental", "Revenue Share": "Revenue Share", NOT_BILLABLE: "Internal Meeting"}.get(self.rental_model)
		if not self.hall_booking_type:
			frappe.throw(_("Choose what the hall is used for (Hall Booking Type), and its rental model: Fixed Rent or Revenue Share (HAL-12)."), title=_("Missing Value"))
		if self.hall_booking_type not in HALL_TYPES:
			frappe.throw(_("Unknown hall booking type {0}.").format(self.hall_booking_type))
		forced = FORCED_MODEL.get(self.hall_booking_type)
		if forced:
			self.rental_model = forced
		elif self.hall_booking_type == "Internal Course or Lecture" and not self.rental_model:
			self.rental_model = NOT_BILLABLE
		elif self.hall_booking_type == "External Lecturer" and self.rental_model not in ("Fixed Rent", "Revenue Share"):
			frappe.throw(_("An external lecturer is rented the hall (Fixed Rent) or shares the revenue (Revenue Share): choose one."), title=_("Missing Value"))
		if self.hall_booking_type == MAINTENANCE:
			self.activity = (self.activity or "").strip() or _("Maintenance")
			self.customer, self.doctor, self.course = None, None, None
		if self.source == MANUAL and not self.customer and not self.not_billable():
			frappe.throw(_("A billed hall booking names its customer: the renter, or the lecturer's customer record."), frappe.MandatoryError, title=_("Missing Value"))
		if self.doctor:
			group = frappe.db.get_value("Customer", self.doctor, "customer_group")
			if group != DOCTOR_GROUP:
				frappe.throw(_("{0} is not a doctor (customer group {1}).").format(self.doctor, DOCTOR_GROUP), title=_("Not a Doctor"))
		if self.course:
			course_doctor = frappe.db.get_value("App Course", self.course, "doctor")
			if course_doctor and not self.doctor:
				self.doctor = course_doctor
		self.capacity = cint(frappe.db.get_value("Booking Resource", self.resource, "capacity"))
		if self.capacity:
			for field in ("expected_attendees", "attendees"):
				if cint(self.get(field)) > self.capacity:
					frappe.throw(
						_("{0}: {1} is more than {2}'s capacity of {3}.").format(_(self.meta.get_label(field)), cint(self.get(field)), self.resource, self.capacity),
						title=_("Over Capacity"),
					)
		for field in ("expected_attendees", "attendees"):
			if cint(self.get(field)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(field))))

	def price_nothing(self):
		"""A not-billable hall booking: nothing is priced, no invoice is made (booking_accounts.complete)."""
		if self.package or self.extras:
			frappe.throw(_("A not-billable hall booking takes no package and no extras."), title=_("Not Billable"))
		self.rate, self.base_amount, self.extras_amount, self.total_amount = 0, 0, 0, 0
		self.price_list, self.pricing_key = None, pricing_key(self)
		self.pricing_note = _("Not billable: an internal use of the hall; nothing is priced or invoiced here.")

	def check_hall_details(self):
		if self.resource_type != "Hall":
			return
		needed = ("activity",) if self.hall_booking_type == MAINTENANCE else ("activity", "responsible_name", "responsible_phone")
		for field in needed:
			if not (self.get(field) or "").strip():
				frappe.throw(_("A hall booking needs {0} (HAL-02).").format(_(self.meta.get_label(field))), title=_("Missing Value"))
		# The same check as a customer's number: a number that cannot be called is refused.
		if (self.responsible_phone or "").strip():
			normalize_phone(self.responsible_phone)

	def check_rental_model(self):
		"""HAL-12: each hall booking names its model; a revenue-share one records its attendees and admission price
		(HAL-08), what was collected, and the lecturer's share, which the owner has not fixed (question 33): it is
		agreed per booking and is required, never assumed, before the booking is completed."""
		if self.resource_type != "Hall":
			self.rental_model = None
		elif not self.rental_model:
			frappe.throw(_("Choose the hall booking's rental model: Fixed Rent or Revenue Share (HAL-12)."), title=_("Missing Value"))
		share = self.rental_model == REVENUE_SHARE
		if not share:
			for field in ("attendees", "admission_price", "expected_revenue", "collected_amount", "lecturer_share_percent", "lecturer_share", "center_share"):
				self.set(field, 0)
			self.lecturer = None
			self.financial_review, self.financial_note = 0, None
			return
		# No Doctor Agreement defines a hall share (the agreements are for books and the app): the share is agreed on
		# each booking (known issue 11). Until it is, the booking is flagged for the accountant; nothing is assumed.
		if flt(self.lecturer_share_percent) or self.lecturer:
			self.financial_review = 0
			self.financial_note = _("Share agreed on this booking: {0}% to the lecturer. No Doctor Agreement defines a hall share.").format(flt(self.lecturer_share_percent))
		else:
			self.financial_review = 1
			self.financial_note = _("Revenue share with no lecturer's share agreed yet, and no Doctor Agreement defines one: to be agreed before the booking is completed.")
		for field in ("attendees", "admission_price", "collected_amount", "lecturer_share_percent"):
			if flt(self.get(field)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(field))))
		if flt(self.lecturer_share_percent) > 100:
			frappe.throw(_("The lecturer's share cannot be more than 100%."))
		self.expected_revenue = flt(cint(self.attendees) * flt(self.admission_price), 2)
		self.lecturer_share, self.center_share = revenue_share(self.collected_amount, self.lecturer_share_percent)
		if self.status == COMPLETED:
			# QA-14: 0 is an answer: no attendees, free admission, or a lecturer who takes no share. A share is never
			# assumed (HAL-12), and the database keeps an empty share as 0, so naming the lecturer is what confirms
			# it: without a lecturer, a 0% share is still missing.
			missing = []
			if not self.lecturer:
				if not flt(self.lecturer_share_percent):
					missing.append(_(self.meta.get_label("lecturer_share_percent")))
				missing.append(_(self.meta.get_label("lecturer")))
			if missing:
				frappe.throw(
					_("A revenue-share booking is completed with its {0}. The lecturer's share is agreed per booking: the owner has not set one rate.").format(
						", ".join(missing)
					),
					title=_("Missing Value"),
				)

	def check_posted(self):
		"""Once the invoice or the revenue-share entry is posted, what it was made from stays as it is: the posted
		document is cancelled first (ACC-07), then the booking can change and be completed again."""
		before = self.get_doc_before_save()
		if self.is_new() or not before:
			return
		documents = [d for d in (posted("Sales Invoice", self.name), posted("Journal Entry", self.name)) if d]
		if not documents:
			return
		shared = ("collected_amount", "lecturer_share_percent", "lecturer", "attendees", "admission_price")
		# QA-15: the day and times too, or the calendar would no longer match the invoice.
		moved = (
			getdate(before.booking_date) != getdate(self.booking_date)
			or get_time(before.from_time) != get_time(self.from_time)
			or get_time(before.to_time) != get_time(self.to_time)
		)
		changed = moved or self.status != before.status or pricing_key(self) != before.pricing_key or any(
			flt(self.get(f)) != flt(before.get(f)) if f != "lecturer" else self.get(f) != before.get(f) for f in shared
		)
		if changed:
			frappe.throw(
				_("{0} is posted ({1}). Cancel it first to change the booking.").format(self.name, ", ".join(documents)),
				title=_("Already Posted"),
			)

	def set_paid(self):
		"""Amount Paid is what the booking's Payment Entries brought in, never typed."""
		self.paid_amount = 0 if self.is_new() else payments_total(self.name)
		self.outstanding_amount = flt(flt(self.total_amount) - flt(self.paid_amount), 2)
		if self.outstanding_amount < 0:
			frappe.throw(
				_("{0} has been paid {1}, more than its new total {2}. The difference is paid back first (by the accountant).").format(
					self.name, self.paid_amount, self.total_amount
				),
				title=_("Paid More Than the Total"),
			)

	def check_amounts(self):
		"""An imported booking: the booking system's amounts, checked."""
		self.total_amount, self.paid_amount = flt(self.total_amount, 2), flt(self.paid_amount, 2)
		if self.total_amount < 0 or self.paid_amount < 0:
			frappe.throw(_("Amounts cannot be negative."))
		if self.paid_amount > self.total_amount:
			frappe.throw(
				_("Amount Paid {0} is more than the Total Amount {1}.").format(self.paid_amount, self.total_amount),
				title=_("Paid More Than the Total"),
			)
		self.outstanding_amount = flt(self.total_amount - self.paid_amount, 2)

	def check_status(self):
		self.cancellation_reason = (self.cancellation_reason or "").strip() or None
		if self.status == CANCELLED and not self.cancellation_reason:
			frappe.throw(_("Give the reason for cancelling the booking."), title=_("Cancellation Reason Required"))
		if self.status != CANCELLED:
			self.cancellation_reason = None
		if self.status == CONFIRMED_NO_DEPOSIT and self.resource_type != HALL:
			frappe.throw(_("The studio confirms a booking with a deposit (Confirmed with Deposit); 'Confirmed' is for IMED's halls."), title=_("Wrong Status"))
		if self.status == CONFIRMED and not self.paid_amount:
			# STU-08: "confirmed with a deposit".
			frappe.throw(
				_("A booking is confirmed with a deposit: record the deposit (Record Payment) first.") if self.source == MANUAL else _("A booking is confirmed with a deposit: enter the amount paid."),
				title=_("No Deposit"),
			)
		if self.status in (COMPLETED, NO_SHOW) and self.starts() > now_datetime():
			frappe.throw(_("The booking has not started yet; it cannot be {0}.").format(_(self.status)))

	def starts(self):
		return get_datetime(self.starts_at)

	def check_overlap(self):
		"""No two bookings of the resource that hold their time overlap. One that ends when the next starts does
		not.

		Two people booking the same resource at the same moment: every booking that holds time first writes its
		resource's row (bookings_saved). The second waits for the first, and MariaDB (11.8, innodb_snapshot_isolation,
		its default) then refuses its write, since the row changed after its transaction began: it is asked to save
		again, and its next try sees the first booking. A booking that gets the write saw every booking of the
		resource, so the plain read below is complete. Bookings of other resources write other rows and never wait
		for each other."""
		if self.status not in HOLDING:
			return
		try:
			frappe.db.sql(
				"update `tabBooking Resource` set bookings_saved = ifnull(bookings_saved, 0) + 1 where name = %s",
				self.resource,
			)
		except frappe.QueryDeadlockError:
			frappe.throw(_("Another booking of {0} was saved at the same moment. Save again.").format(self.resource), title=_("Save Again"))
		# Exact instants (a booking may cross midnight), and the resource's buffer on both sides: with a buffer of
		# 15 minutes a booking ending at 12:00 and one starting at 12:10 clash; with none, back to back is free.
		buffer = timedelta(minutes=cint(frappe.db.get_value("Booking Resource", self.resource, "buffer_minutes")))
		clash = frappe.db.sql(
			"""select name, starts_at, ends_at, status from `tabBooking`
			where resource = %(resource)s and name != %(name)s and status in %(holding)s
			and starts_at < %(ends)s and ends_at > %(starts)s
			order by starts_at limit 1""",
			{
				"resource": self.resource,
				"name": self.name or "",
				"holding": HOLDING,
				"starts": get_datetime(self.starts_at) - buffer,
				"ends": get_datetime(self.ends_at) + buffer,
			},
			as_dict=True,
		)
		if clash:
			other = clash[0]
			frappe.throw(
				_("{0} is already booked from {1} to {2} ({3}, {4}){5}.").format(
					self.resource,
					frappe.format_value(other.starts_at, {"fieldtype": "Datetime"}),
					frappe.format_value(other.ends_at, {"fieldtype": "Datetime"}),
					other.name,
					_(other.status),
					_(" with {0} minutes kept free around each booking").format(buffer.seconds // 60) if buffer else "",
				),
				title=_("Already Booked"),
			)


@frappe.whitelist()
def get_events(start, end, filters=None, **kwargs):
	"""The bookings for the Booking calendar (booking_calendar.js), a day or a week of them, between `start` and `end`
	(the calendar's own range: `end` is the first moment after it).

	Read through frappe.get_list, as the Bookings list is: only what the user may read, so a branch manager sees
	their own business's bookings, and someone with no access to bookings is refused. `filters` are the list's
	filters (a resource, a status...).

	Each booking that holds its time and overlaps another of its resource is marked `conflict`. The overlap check
	refuses such a pair, so none is expected; one made around it (a direct database change) is shown in red."""
	start, end = get_datetime(start), get_datetime(end)
	filters = frappe.parse_json(filters) or []
	if isinstance(filters, dict):
		filters = [[field, *value] if isinstance(value, list) else [field, "=", value] for field, value in filters.items()]
	rows = frappe.get_list(
		"Booking",
		fields=["name", "resource", "resource_type", "customer", "booking_date", "from_time", "to_time", "status", "starts_at", "ends_at", "hall_booking_type", "activity", "doctor"],
		filters=[*filters, ["booking_date", ">=", add_days(getdate(start), -1)], ["booking_date", "<=", getdate(end)]],
		order_by="booking_date asc, from_time asc",
		limit_page_length=0,
	)
	events = []
	for row in rows:
		starts = get_datetime(row.starts_at) if row.starts_at else datetime.combine(getdate(row.booking_date), get_time(row.from_time))
		ends = get_datetime(row.ends_at) if row.ends_at else datetime.combine(getdate(row.booking_date), get_time(row.to_time))
		if starts >= end or ends <= start:
			continue
		events.append(
			frappe._dict(
				name=row.name,
				resource=row.resource,
				resource_type=row.resource_type,
				customer=row.customer,
				status=row.status,
				holding=int(row.status in HOLDING),
				start=starts.strftime("%Y-%m-%d %H:%M:%S"),
				end=ends.strftime("%Y-%m-%d %H:%M:%S"),
				title=f"{row.resource} · {row.customer or row.activity or ''} ({_(row.status)})" + (f" · {_(row.hall_booking_type)}" if row.hall_booking_type else ""),
				hall_booking_type=row.hall_booking_type,
				doctor=row.doctor,
				all_day=0,
				# A booking's times are the hall's or the studio's clock, whatever the user's time zone.
				convert_to_user_tz=0,
				conflict=0,
			)
		)
	holding = [e for e in events if e.holding]
	for i, event in enumerate(holding):
		for other in holding[i + 1 :]:
			if event.resource == other.resource and event.start < other.end and other.start < event.end:
				event.conflict = other.conflict = 1
	return events
