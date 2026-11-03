# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Prepaid studio hours (22 Oct 2026): a teacher buys a number of recording hours of a studio service and uses them
# over as many sessions, days and weeks as needed. 30 hours bought; sessions of 2, 3 and 1.5 hours; 23.5 left.
#
# A Booking names the package (Prepaid Hours); its exact length (90 minutes = 1.5 hours, never rounded) comes off the
# package while it holds its time (Tentative, Confirmed with Deposit, Completed). Rescheduled to another length, the
# difference is drawn or given back; Cancelled or No Show, it is all given back. Each change is a row of the package's
# history (who, when, why, the hours left after), and the package's Hours Used is the sum of them: a booking draws
# only the difference between what it should hold and what it already holds, so saving it again draws nothing.
#
# Never below zero: a session longer than the hours left is refused, unless the accountant or the owner decides the
# hours beyond are billed (the booking's Bill the Hours Beyond the Package); then the package is used up and only those
# hours are priced, at the hourly price. The hours the package covers are never billed again: its price is billed
# once, by its own invoice (Make Invoice).
#
# Two bookings of one package at once: each locks the package's row before it reads what is left (a locking read sees
# what the other committed), so the second waits and sees the first's hours, or is asked to save again.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from imed_erp.imederp.sales_cancellation import clean_reason

ACCOUNTS_ROLES = ("Accounts Manager", "System Manager")
ACTIVE, USED_UP, CANCELLED = "Active", "Used Up", "Cancelled"
STUDIO = "Studio Service"
PRECISION = 4


class StudioHourPackage(Document):
	def validate(self):
		from imed_erp.imederp.doctype.booking.booking import check_own_business

		resource = frappe.db.get_value("Booking Resource", self.resource, ["resource_type", "cost_center"], as_dict=True)
		if not resource or resource.resource_type != STUDIO:
			frappe.throw(_("{0} is not a studio service. Prepaid hours are for the studio.").format(self.resource))
		self.cost_center = resource.cost_center
		check_own_business(self.cost_center)
		if flt(self.hours_purchased) <= 0:
			frappe.throw(_("Hours Purchased must be greater than zero."))
		if flt(self.price) < 0:
			frappe.throw(_("The package price cannot be negative."))
		self.check_source()
		if self.docstatus == 0:
			self.status, self.hours_used, self.hours_remaining = "Draft", 0, flt(self.hours_purchased, PRECISION)

	def check_source(self):
		"""Only the sync makes an imported package (the XStudio sync: imederp/xstudio/sync.py), and only it changes
		one; a package entered here is Manual, whatever was typed."""
		if self.flags.from_import:
			self.source = "Imported"
			if not (self.source_system and self.external_id):
				frappe.throw(_("An imported package needs its source system and its id there."))
			self.import_key = f"{self.source_system}:{self.external_id}"
			return
		if self.is_new():
			self.source = "Manual"
			for field in ("source_system", "external_id", "import_key"):
				self.set(field, None)
			return
		before = self.get_doc_before_save()
		if before and before.source == "Imported":
			frappe.throw(
				_("{0} was imported from {1}. Change it there; the next sync brings the change.").format(self.name, before.source_system),
				title=_("Imported Package"),
			)

	def on_submit(self):
		self.db_set({"status": ACTIVE, "hours_used": 0, "hours_remaining": flt(self.hours_purchased, PRECISION)})

	def before_cancel(self):
		if self.source == "Imported" and not self.flags.from_import:
			frappe.throw(
				_("{0} was imported from {1}. Change it there; the next sync brings the change.").format(self.name, self.source_system),
				title=_("Imported Package"),
			)
		frappe.only_for(ACCOUNTS_ROLES)
		if not clean_reason(self.cancel_reason):
			frappe.throw(_("Cancelling a package needs a reason."), title=_("Reason Needed"))
		holding = held_by_bookings(self.name)
		if holding:
			frappe.throw(
				_("{0} hours of {1} are held by bookings ({2}). Cancel or move them first.").format(
					flt(sum(holding.values()), 2), self.name, ", ".join(sorted(holding))
				),
				title=_("Hours Still Used"),
			)
		if self.sales_invoice and frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus") == 1:
			frappe.throw(
				_("{0} is billed by {1}. Cancel the invoice first (with its reason).").format(self.name, self.sales_invoice),
				title=_("Billed"),
			)

	def on_cancel(self):
		self.db_set("status", CANCELLED)


def held_by_bookings(package):
	"""{booking: net hours it holds of the package}, from the history."""
	held = {}
	for row in frappe.get_all("Studio Hour Package Usage", filters={"parent": package, "parenttype": "Studio Hour Package"}, fields=["booking", "hours"]):
		held[row.booking] = flt(held.get(row.booking, 0) + flt(row.hours), PRECISION)
	return {booking: hours for booking, hours in held.items() if hours}


def lock(package):
	"""The package's row, locked: its figures as last committed."""
	try:
		return frappe.db.get_value(
			"Studio Hour Package",
			package,
			["name", "docstatus", "status", "customer", "resource", "hours_purchased", "hours_used", "source", "source_system"],
			as_dict=True,
			for_update=True,
		)
	except frappe.QueryDeadlockError:
		frappe.throw(_("Another session used {0} at the same moment. Save again.").format(package), title=_("Save Again"))


def held_by(package, booking):
	return flt(
		frappe.db.sql(
			"""select sum(hours) from `tabStudio Hour Package Usage`
			where parent = %s and parenttype = 'Studio Hour Package' and booking = %s for update""",
			(package, booking),
		)[0][0],
		PRECISION,
	)


def plan(booking, hours, holding):
	"""For a booking about to be saved: (hours from the package, hours beyond it). Refuses a session longer than the
	hours left unless billing the rest was decided."""
	package = lock(booking.hour_package)
	if package and package.source == "Imported":
		frappe.throw(
			_("{0} is kept in {1}, where its balance is drawn. Book the session there.").format(booking.hour_package, package.source_system or _("its source")),
			title=_("Imported Package"),
		)
	if not package or package.docstatus != 1 or package.status not in (ACTIVE, USED_UP):
		frappe.throw(_("{0} is not an active package.").format(booking.hour_package), title=_("Package Not Active"))
	if package.customer != booking.customer or package.resource != booking.resource:
		frappe.throw(
			_("{0} is {1}'s package for {2}.").format(booking.hour_package, package.customer, package.resource), title=_("Wrong Package")
		)
	if not holding:
		return 0, 0
	already = held_by(booking.hour_package, booking.name) if booking.name and not booking.is_new() else 0
	left = flt(flt(package.hours_purchased) - flt(package.hours_used) + already, PRECISION)
	hours = flt(hours, PRECISION)
	if hours <= left:
		return hours, 0
	if not booking.bill_extra_hours:
		frappe.throw(
			_("{0} has {1} hours left; this session is {2} hours. Shorten it, or the accountant decides to bill the {3} hours beyond the package.").format(
				booking.hour_package, flt(left, 2), flt(hours, 2), flt(hours - left, 2)
			),
			title=_("Not Enough Hours"),
		)
	return max(left, 0), flt(hours - max(left, 0), PRECISION)


def draw(booking):
	"""After the booking is saved: bring what it holds of its package (and of any package it held before) to what it
	should hold, as rows of the history."""
	target = flt(booking.package_hours, PRECISION) if booking.hour_package else 0
	before = booking.get_doc_before_save()
	packages = {booking.hour_package} | ({before.hour_package} if before and before.hour_package else set())
	for package in sorted(p for p in packages if p):
		lock(package)
		want = target if package == booking.hour_package else 0
		difference = flt(want - held_by(package, booking.name), PRECISION)
		if difference:
			record(package, booking, difference, reason_for(booking, difference))


def reason_for(booking, difference):
	if booking.status in ("Cancelled", "No Show"):
		return _("{0}: {1}").format(_(booking.status), booking.cancellation_reason or "-")[:140]
	return _("Session drawn") if difference > 0 else _("Session shortened or moved")


def record(package, booking, hours, reason):
	used = flt(
		flt(frappe.db.sql("select sum(hours) from `tabStudio Hour Package Usage` where parent = %s and parenttype = 'Studio Hour Package' for update", package)[0][0])
		+ hours,
		PRECISION,
	)
	purchased = flt(frappe.db.get_value("Studio Hour Package", package, "hours_purchased"), PRECISION)
	if used > purchased + 0.00005 or used < -0.00005:
		frappe.throw(_("{0} cannot go below zero hours.").format(package), title=_("Not Enough Hours"))
	idx = frappe.db.count("Studio Hour Package Usage", {"parent": package, "parenttype": "Studio Hour Package"}) + 1
	frappe.get_doc(
		{
			"doctype": "Studio Hour Package Usage",
			"parent": package,
			"parenttype": "Studio Hour Package",
			"parentfield": "usage",
			"idx": idx,
			"booking": booking.name,
			"booking_date": booking.booking_date,
			"hours": hours,
			"balance": flt(purchased - used, PRECISION),
			"reason": reason,
			"changed_by": frappe.session.user,
			"changed_on": now_datetime(),
		}
	).db_insert()
	remaining = flt(purchased - used, PRECISION)
	frappe.db.set_value(
		"Studio Hour Package",
		package,
		{"hours_used": used, "hours_remaining": remaining, "status": USED_UP if remaining <= 0 else ACTIVE},
		update_modified=False,
	)


@frappe.whitelist(methods=["POST"])
def make_invoice(name):
	"""The package's one invoice: its price, for the hours bought, to the teacher. Its sessions are not billed again."""
	from imed_erp.imederp.booking_accounts import company_of, income_account_of, rate_for

	package = frappe.get_doc("Studio Hour Package", name)
	package.check_permission("write")
	frappe.db.get_value("Studio Hour Package", name, "name", for_update=True)
	billed = frappe.db.get_value("Studio Hour Package", name, "sales_invoice")
	if billed and frappe.db.get_value("Sales Invoice", billed, "docstatus") == 1:
		frappe.throw(_("{0} is already billed: {1}.").format(name, billed), title=_("Already Billed"))
	if package.docstatus != 1:
		frappe.throw(_("Submit the package first."))
	item = frappe.db.get_value("Booking Resource", package.resource, "item")
	if not item:
		frappe.throw(_("{0} has no service item to bill.").format(package.resource))
	hours = flt(package.hours_purchased, 2)
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company_of(package.cost_center),
			"customer": package.customer,
			"posting_date": package.purchase_date,
			"set_posting_time": 1,
			"due_date": package.purchase_date,
			"cost_center": package.cost_center,
			"ignore_pricing_rule": 1,
			"update_stock": 0,
			"remarks": _("Prepaid studio hours {0}: {1} hours").format(name, hours),
			"items": [
				{
					"item_code": item,
					"qty": hours,
					"rate": rate_for(flt(package.price), hours),
					"uom": frappe.get_cached_value("Item", item, "stock_uom"),
					"conversion_factor": 1,
					"income_account": income_account_of(package.cost_center),
					"cost_center": package.cost_center,
				}
			],
		}
	)
	invoice.insert()
	if flt(invoice.grand_total, 2) != flt(package.price, 2):
		frappe.throw(_("The invoice total {0} differs from the package price {1}.").format(invoice.grand_total, package.price))
	invoice.submit()
	frappe.db.set_value("Studio Hour Package", name, "sales_invoice", invoice.name)
	return invoice.name


@frappe.whitelist(methods=["POST"])
def cancel_package(name, reason):
	frappe.only_for(ACCOUNTS_ROLES)
	reason = clean_reason(reason)
	if not reason:
		frappe.throw(_("Cancelling a package needs a reason."), title=_("Reason Needed"))
	doc = frappe.get_doc("Studio Hour Package", name)
	doc.cancel_reason = reason
	doc.cancel()
	return doc.name
