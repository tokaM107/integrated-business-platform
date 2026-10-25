# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Reading XStudio into this system (STU-06, STU-09, STU-10, STU-14, INT-01, INT-06, INT-07): XStudio stays the
# source of the studio's bookings; here they are watched and accounted for. The sync reads XStudio's existing API
# (xstudio/client.py), changes nothing there, and posts nothing here: no Payment Entry, invoice or journal entry
# is made from what it reads (booking_accounts.py skips imported bookings). It runs every few minutes from the
# scheduler (run_scheduled), or by hand (Sync Now on XStudio Settings).
#
# One run, in order:
#   1. the bookings that start in the window [today - Days Back, today + Days Ahead] (Cairo), read in halves until
#      no answer hits XStudio's fixed 500-row limit; a span under an hour that still does is listed as incomplete
#   2. their customers: found by XStudio's id, else linked by phone, else made (group عملاء الاستوديو)
#   3. those customers' prepaid packages (GET /api/customers/:id/packages), as Studio Hour Packages
#   4. the bookings, inserted or updated; an unchanged one (same payload hash) is skipped
#   5. the packages' usage ledgers, each XStudio row once, by its id
#   6. bookings imported earlier that the window no longer returns: looked for by their customer (rescheduled out of
#      the window), else listed for review. Nothing is deleted or cancelled here because XStudio did not return it.
# Each record is its own savepoint: one that fails is listed with its reason and the rest go on. The run writes an
# Integration Import Log (source_system xstudio); XStudio unreachable, or a deadlock, aborts the run with a Failed
# log, and what was imported before stays as it was.
#
# What the existing API cannot tell (kept honest in the log and docs/XSTUDIO_SYNC.md):
#   - a change is seen only when the booking is read again: bookings are read by their start, so one moved out of
#     the window is found only through its customer's list (itself capped at 500);
#   - payments carry no ids (routes.js:912): a booking shows what XStudio says was paid, a package a summary;
#   - a package deleted in XStudio (DELETE /customer-packages/:id) simply stops being returned: it stays here as
#     it was, and its balance is no longer updated;
#   - the balance XStudio reports is the balance (XStudio Hours Remaining); when its usage rows do not add up to it
#     (a package migrated from the sheet, or a balance set by hand there) the package is marked and the log carries
#     an informational note, nothing more. Nothing here recalculates a balance.

import hashlib
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, now_datetime, time_diff_in_seconds

from imed_erp.imederp.customers import customer_with_phone, phone_key_or_none
from imed_erp.imederp.doctype.integration_import_log.integration_import_log import ImportRun
from imed_erp.imederp.xstudio import mappers
from imed_erp.imederp.xstudio import client as xclient
from imed_erp.imederp.xstudio.client import XStudioClient, XStudioError, stable_json
from imed_erp.imederp.xstudio.mappers import CAIRO, SOURCE, import_key

LOCK = "imed_erp_xstudio_sync"
SAVEPOINT = "xstudio_record"
RUN_SAVEPOINT = "xstudio_run"
PRECISION = 4
MANAGERS = ("System Manager", "Accounts Manager")


class SyncStopped(Exception):
	"""The whole run is over (the database rolled it back, or XStudio could not be read)."""


class Context:
	def __init__(self, settings, client, run):
		self.settings = settings
		self.client = client
		self.run = run
		self.hall_map = {cint(row.hall_id): row.resource for row in settings.hall_map}
		self.customers = {}  # XStudio customer id -> Customer name
		self.packages = {}  # XStudio package id -> Studio Hour Package name
		self.package_rows = {}  # XStudio package id -> its row (with usage), for the ledger step
		self.row_no = 0

	def next_row(self):
		self.row_no += 1
		self.run.read()
		return self.row_no


# ---------- entry points ----------


@frappe.whitelist()
def sync_now():
	"""Sync Now on XStudio Settings: one run, by the owner or the accountant."""
	frappe.only_for(MANAGERS)
	log = run(trigger="manual")
	return {field: log.get(field) for field in ("name", "status", "rows_read", "inserted", "updated", "skipped", "changed", "failed", "message")}


@frappe.whitelist()
def test_connection():
	frappe.only_for(MANAGERS)
	settings = frappe.get_single("XStudio Settings")
	client = XStudioClient(settings)
	try:
		client.health()
		halls = client.halls()
		client.login()
	except XStudioError as e:
		frappe.throw(cstr(e), title=_("XStudio Not Reachable"))
	mapped = {cint(row.hall_id) for row in settings.hall_map}
	unmapped = [f"{h.get('id')} ({h.get('name')})" for h in halls if cint(h.get("id")) not in mapped]
	message = _("XStudio answered and the login worked. {0} active halls.").format(len(halls))
	if unmapped:
		message += " " + _("Not mapped to a resource yet: {0}.").format(", ".join(unmapped))
	return message


def run_scheduled():
	"""The scheduler's entry (every 10 minutes): a run when the settings say it is time."""
	settings = frappe.get_single("XStudio Settings")
	if not settings.enabled:
		return None
	if settings.last_attempt_at and time_diff_in_seconds(now_datetime(), settings.last_attempt_at) < cint(settings.poll_minutes) * 60 - 30:
		return None
	return run(trigger="scheduler")


def run(trigger="scheduler", lookback_days=None, lookahead_days=None, dry_run=False):
	"""One run of the sync. Returns its Integration Import Log. Two runs at once: the second is refused.
	dry_run: the whole run, then rolled back: nothing is kept, not even the log; what it would have done is returned."""
	settings = frappe.get_single("XStudio Settings")
	if not settings.enabled and not dry_run:
		frappe.throw(_("The XStudio sync is not enabled (XStudio Settings)."), title=_("Sync Disabled"))
	if not acquire_lock():
		frappe.throw(_("An XStudio sync is already running. Wait for it to finish."), title=_("Already Running"))
	try:
		return _run(settings, trigger, lookback_days, lookahead_days, dry_run)
	finally:
		release_lock()


@frappe.whitelist()
def dry_run(lookback_days=None, lookahead_days=None):
	"""What a run would do, without keeping anything (the first look at a real XStudio before any import):
	  bench --site frontend execute imed_erp.imederp.xstudio.sync.dry_run"""
	frappe.only_for(MANAGERS)
	return run(trigger="dry run", lookback_days=lookback_days, lookahead_days=lookahead_days, dry_run=True)


def _snapshot():
	"""The XStudio records on the site now, so a dry run can say which ones it would add."""
	return {
		"customers": set(frappe.get_all("Customer", filters={"xstudio_customer_id": ("is", "set")}, pluck="xstudio_customer_id")),
		"customer_names": set(frappe.get_all("Customer", pluck="name")),
		"packages": set(frappe.get_all("Studio Hour Package", filters={"source_system": SOURCE}, pluck="import_key")),
		"bookings": set(frappe.get_all("Booking", filters={"source_system": SOURCE}, pluck="import_key")),
		"usage": frappe.db.count("Studio Hour Package Usage", {"external_id": ("is", "set")}),
	}


def _would_add(before):
	after = _snapshot()
	new_bookings = frappe.get_all(
		"Booking",
		filters={"source_system": SOURCE, "import_key": ("in", list(after["bookings"] - before["bookings"]))},
		fields=["booking_date", "from_time", "to_time", "resource", "customer", "status", "total_amount", "paid_amount"],
		order_by="booking_date, from_time",
	) if after["bookings"] - before["bookings"] else []
	touched = frappe.get_all(
		"Customer",
		filters={"xstudio_customer_id": ("in", list(after["customers"] - before["customers"]))},
		fields=["name", "customer_name", "mobile_no", "xstudio_needs_review"],
	) if after["customers"] - before["customers"] else []
	# A customer that was on the site before the run and now carries an XStudio id was linked (by phone), not made.
	new_customers = [c for c in touched if c.name not in before["customer_names"]]
	linked_customers = [c for c in touched if c.name in before["customer_names"]]
	new_packages = frappe.get_all(
		"Studio Hour Package",
		filters={"source_system": SOURCE, "import_key": ("in", list(after["packages"] - before["packages"]))},
		fields=["customer", "unit", "hours_purchased", "hours_remaining", "xstudio_hours_remaining", "xstudio_balance_matches", "xstudio_payment_status", "xstudio_paid_total", "xstudio_payments_summary"],
	) if after["packages"] - before["packages"] else []
	by_status = {}
	for row in new_bookings:
		by_status[row.status] = by_status.get(row.status, 0) + 1
	return {
		"customers": new_customers,
		"customers_linked": linked_customers,
		"packages": new_packages,
		"usage_rows": after["usage"] - before["usage"],
		"bookings": new_bookings,
		"bookings_by_status": by_status,
	}


def acquire_lock():
	"""A database-wide named lock: the scheduler's workers and a Sync Now never read XStudio at the same time."""
	return cint(frappe.db.sql("select get_lock(%s, 0)", LOCK)[0][0]) == 1


def release_lock():
	frappe.db.sql("select release_lock(%s)", LOCK)


def _run(settings, trigger, lookback_days, lookahead_days, dry_run=False):
	today = datetime.now(CAIRO).date()
	start, end = mappers.window_edges(
		today,
		settings.lookback_days if lookback_days is None else lookback_days,
		settings.lookahead_days if lookahead_days is None else lookahead_days,
	)
	label = f"XStudio bookings starting {start.date()} to {(end - timedelta(days=1)).date()} ({trigger})"
	run = ImportRun(SOURCE, file_name=label)
	if not dry_run:
		set_state(last_attempt_at=now_datetime())
	before = _snapshot() if dry_run else None
	# The run's own savepoint: a run that stops is rolled back to it, and what earlier runs committed stays.
	frappe.db.savepoint(RUN_SAVEPOINT)
	try:
		client = XStudioClient(settings)
		context = Context(settings, client, run)
		bookings, incomplete = fetch_bookings(client, start, end)
		for window_start, window_end in incomplete:
			run.failed(
				0,
				f"{window_start.isoformat()}..{window_end.isoformat()}",
				_("XStudio returned its maximum of {0} bookings for this span, which cannot be split further: some of its bookings may be missing from this run.").format(xclient.BOOKINGS_LIMIT),
			)
		import_customers(context, bookings)
		import_packages(context)
		import_bookings(context, bookings)
		import_usage(context)
		if not incomplete:
			find_missing(context, bookings, start, end)
		log = run.finish()
		if dry_run:
			would = _would_add(before)
			rows = [dict(row) for row in run.rows]
			frappe.db.rollback(save_point=RUN_SAVEPOINT)
			return {
				"dry_run": True,
				"window": label,
				"status": log.status,
				"counts": {k: log.get(k) for k in ("rows_read", "inserted", "updated", "skipped", "changed", "failed")},
				"would_add": would,
				"incomplete_spans": [f"{a.isoformat()}..{b.isoformat()}" for a, b in incomplete],
				"to_look_at": [r for r in rows if r.get("kind") != "Failed"],
				"would_fail": [r for r in rows if r.get("kind") == "Failed"],
			}
		set_state(last_success_at=now_datetime(), consecutive_failures=0, last_message=summary(log), health=health_of(log, 0))
		return log
	except Exception as e:
		try:
			frappe.db.rollback(save_point=RUN_SAVEPOINT)
		except Exception:
			# A deadlock made the database roll the whole transaction back, savepoint and all.
			frappe.db.rollback()
		message = cstr(getattr(e, "message", None) or e)
		if dry_run:
			return {"dry_run": True, "window": label, "status": "Failed", "message": message}
		failures = cint(frappe.db.get_single_value("XStudio Settings", "consecutive_failures")) + 1
		if frappe.flags.in_test:
			# The tests roll everything back at their end; a commit here would leave their records on the site.
			run.counts.update(inserted=0, records_created=0, updated=0)
			log = run.write("Failed", message=message)
		else:
			log = run.abort(e)
		set_state(consecutive_failures=failures, last_message=message[:500], health=health_of(log, failures))
		if not frappe.flags.in_test:
			frappe.db.commit()
		if not isinstance(e, (XStudioError, SyncStopped)):
			frappe.log_error(title="XStudio sync failed", message=frappe.get_traceback())
		return log


def set_state(**values):
	frappe.db.set_single_value("XStudio Settings", values, update_modified=False)


def summary(log):
	return _("{0} read, {1} inserted, {2} updated, {3} unchanged, {4} to look at, {5} failed.").format(
		log.rows_read, log.inserted, log.updated, log.skipped, log.changed, log.failed
	)


def health_of(log, failures):
	if failures >= 3:
		return "Down"
	if failures or log.status != "Completed":
		return "Degraded"
	return "Healthy"


# ---------- 1. the bookings of the window ----------


def fetch_bookings(client, start, end):
	"""Every booking starting in [start, end). XStudio answers at most 500 rows and offers no paging, so a full
	answer means the span is halved and read again, down to one hour. Returns (rows, [incomplete spans])."""
	rows = client.bookings(starts_from=mappers.iso_utc(start), starts_before=mappers.iso_utc(end))
	if len(rows) < xclient.BOOKINGS_LIMIT:
		return rows, []
	if end - start <= timedelta(hours=1):
		return rows, [(start, end)]
	middle = start + (end - start) / 2
	first, incomplete_first = fetch_bookings(client, start, middle)
	second, incomplete_second = fetch_bookings(client, middle, end)
	seen, merged = set(), []
	for row in first + second:
		if row.get("id") not in seen:
			seen.add(row.get("id"))
			merged.append(row)
	return merged, incomplete_first + incomplete_second


# ---------- each record its own savepoint ----------


def each(context, items, work, label):
	"""`work(item)` for each item, in its own savepoint: one that fails is listed, the others go on. A deadlock has
	rolled the whole run back: it is stopped and said so."""
	for item in items:
		row_no = context.next_row()
		frappe.db.savepoint(SAVEPOINT)
		try:
			work(item)
		except Exception as e:
			try:
				frappe.db.rollback(save_point=SAVEPOINT)
			except Exception:
				raise SyncStopped(
					_("The run stopped at {0}: the database rolled it back (another save at the same moment). Nothing of this run was kept; the next run is safe.").format(label(item))
				)
			frappe.clear_messages()
			context.run.failed(row_no, label(item), cstr(getattr(e, "message", None) or e)[:500])


# ---------- 2. customers ----------


def import_customers(context, bookings):
	customers = {}
	for booking in bookings:
		customer = mappers.customer_from_booking(booking)
		if customer["id"] and customer["id"] not in customers:
			customers[customer["id"]] = customer
	each(context, customers.values(), lambda c: upsert_customer(context, c), lambda c: f"customer {c['id']}")


def upsert_customer(context, customer):
	"""The Customer for an XStudio customer: by XStudio's id; else the one with the same phone, which is then linked;
	else a new one. One without a usable phone is made without a number and marked for review (never a made-up
	number)."""
	xid = cstr(customer["id"])
	name = frappe.db.get_value("Customer", {"xstudio_customer_id": xid}, "name")
	phone = mappers.real_phone(customer["phone"])
	key = phone_key_or_none(phone) if phone else None
	if not name and key:
		other = customer_with_phone(key)
		if other:
			taken = frappe.db.get_value("Customer", other.name, "xstudio_customer_id")
			if taken and taken != xid:
				frappe.throw(_("The phone {0} belongs to customer {1}, who is another XStudio customer ({2}).").format(phone, other.name, taken))
			name = other.name
			frappe.db.set_value("Customer", name, {"xstudio_customer_id": xid, "xstudio_last_synced_at": now_datetime()}, update_modified=False)
	if not name:
		doc = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": customer["name"] or _("XStudio customer {0}").format(xid[:8]),
				"customer_type": "Individual",
				"customer_group": context.settings.customer_group,
				"territory": default_territory(),
				"mobile_no": phone if key else None,
				"xstudio_customer_id": xid,
				"xstudio_needs_review": 0 if key else 1,
				"xstudio_last_synced_at": now_datetime(),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		name = doc.name
		context.run.created()
	else:
		changes = {"xstudio_last_synced_at": now_datetime()}
		current = frappe.db.get_value("Customer", name, ["customer_name", "mobile_no", "custom_phone_key", "xstudio_needs_review"], as_dict=True)
		if customer["name"] and customer["name"] != current.customer_name:
			changes["customer_name"] = customer["name"]
		if key and key != current.custom_phone_key and not customer_with_phone(key, exclude=name):
			doc = frappe.get_doc("Customer", name)
			doc.mobile_no = phone
			doc.flags.ignore_permissions = True
			doc.save()
			changes["xstudio_needs_review"] = 0
		elif not key and current.mobile_no is None and not current.xstudio_needs_review:
			changes["xstudio_needs_review"] = 1
		frappe.db.set_value("Customer", name, changes, update_modified=False)
	context.customers[xid] = name
	return name


def default_territory():
	territory = frappe.db.get_single_value("Selling Settings", "territory")
	if territory:
		return territory
	return frappe.db.get_value("Territory", {"is_group": 0}, "name") or frappe.db.get_value("Territory", {}, "name")


# ---------- 3. prepaid packages ----------


def import_packages(context):
	"""GET /api/customers/:id/packages for each customer of the run: the packages first (a booking links to its
	package), their ledgers after the bookings (a ledger row links to its booking)."""
	for xid, customer in list(context.customers.items()):
		try:
			rows = context.client.customer_packages(xid)
		except XStudioError as e:
			context.run.failed(context.next_row(), f"customer {xid} packages", cstr(e)[:500])
			continue
		for row in rows:
			context.package_rows[cstr(row.get("id"))] = (customer, row)
		each(context, rows, lambda p, c=customer: upsert_package(context, c, p), lambda p: f"package {p.get('id')}")


def package_source_time(package):
	"""When the package last changed, as far as the API tells: bought, paid or used. XStudio keeps no updated_at on
	a package (schema.sql), so a hand edit of its balance shows only through the balance itself."""
	moments = [package.get("purchased_at")]
	moments += [p.get("created_at") for p in package.get("payments") or []]
	moments += [u.get("created_at") for u in package.get("usage") or []]
	instants = [mappers.parse_instant(m) for m in moments if m]
	return mappers.naive_cairo(max(instants).isoformat()) if instants else None


def package_values(context, customer, package):
	unit = mappers.package_unit(package)
	purchased = mappers.to_cairo(package.get("purchased_at"))
	expires = mappers.to_cairo(package.get("expires_at"))
	payload = {k: v for k, v in package.items() if k != "usage"}
	return {
		"customer": customer,
		"resource": context.settings.packages_resource,
		"purchase_date": purchased.date() if purchased else datetime.now(CAIRO).date(),
		"hours_purchased": flt(package.get("hours_total"), 2),
		"price": flt(package.get("price"), 2),
		"notes": cstr(package.get("name")),
		"package_name": cstr(package.get("name")),
		"unit": unit,
		"xstudio_category": cstr(package.get("category")),
		"expires_on": expires.date() if expires else None,
		"xstudio_hours_remaining": flt(package.get("hours_remaining"), PRECISION),
		"xstudio_payment_status": cstr(package.get("payment_status")),
		"xstudio_paid_total": flt(package.get("paid_total"), 2),
		"xstudio_payments_summary": mappers.payments_summary(package),
		"source_updated_at": package_source_time(package),
		"source_payload": stable_json(payload),
		"source_payload_hash": hashlib.sha256(stable_json(payload).encode()).hexdigest(),
	}


def upsert_package(context, customer, package):
	xid = cstr(package.get("id"))
	if not xid:
		frappe.throw(_("The package has no id."))
	if flt(package.get("hours_total")) <= 0:
		frappe.throw(_("The package has no hours."))
	key = import_key(xid)
	values = package_values(context, customer, package)
	existing = frappe.db.get_value("Studio Hour Package", {"import_key": key}, ["name", "source_payload_hash", "docstatus"], as_dict=True)
	if existing:
		context.packages[xid] = existing.name
		if existing.source_payload_hash == values["source_payload_hash"]:
			frappe.db.set_value("Studio Hour Package", existing.name, "last_synced_at", now_datetime(), update_modified=False)
			context.run.skipped()
			return existing.name
		# A submitted package: its mirror fields follow the source without a new version of the document.
		mirrored = {k: v for k, v in values.items() if k not in ("customer", "resource", "purchase_date")}
		mirrored["last_synced_at"] = now_datetime()
		frappe.db.set_value("Studio Hour Package", existing.name, mirrored, update_modified=False)
		context.run.updated()
		return existing.name
	doc = frappe.get_doc(
		{
			"doctype": "Studio Hour Package",
			**values,
			"source": "Imported",
			"source_system": SOURCE,
			"external_id": xid,
			"import_key": key,
			"last_synced_at": now_datetime(),
		}
	)
	doc.flags.from_import = True
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	context.packages[xid] = doc.name
	context.run.inserted()
	return doc.name


# ---------- 4. bookings ----------


def import_bookings(context, bookings):
	bookings = sorted(bookings, key=lambda b: cstr(b.get("created_at")))
	each(context, bookings, lambda b: upsert_booking(context, b), lambda b: f"booking {b.get('id')}")


def booking_values(context, booking):
	xid = cstr(booking.get("id"))
	hall = cint(booking.get("hall_id"))
	resource = context.hall_map.get(hall)
	if not resource:
		frappe.throw(_("XStudio hall {0} is not mapped to a booking resource (XStudio Settings).").format(hall))
	customer = context.customers.get(cstr(booking.get("customer_id")))
	if not customer:
		if booking.get("customer_id"):
			frappe.throw(_("The booking's customer {0} could not be made here (see its own row).").format(booking.get("customer_id")))
		frappe.throw(_("The booking has no customer account in XStudio (a walk-in without a phone); a booking here needs its customer."))
	booking_date, from_time, to_time, crosses = mappers.booking_times(booking)
	status = mappers.booking_status(booking)
	total, paid = mappers.booking_amounts(booking)
	package = context.packages.get(cstr(booking.get("package_id"))) if booking.get("package_id") else None
	if booking.get("package_id") and not package:
		package = frappe.db.get_value("Studio Hour Package", {"import_key": import_key(cstr(booking.get("package_id")))}, "name")
	return {
		"resource": resource,
		"customer": customer,
		"booking_date": booking_date,
		"from_time": from_time.strftime("%H:%M:%S"),
		"to_time": to_time.strftime("%H:%M:%S"),
		"status": status,
		"cancellation_reason": mappers.cancellation_reason(booking) if status == "Cancelled" else None,
		"notes": cstr(booking.get("notes")) or None,
		"total_amount": total,
		"paid_amount": paid,
		"hour_package": package,
		"package_hours": flt(booking.get("hours_deducted"), PRECISION) if package else 0,
		"xstudio_status": cstr(booking.get("status")),
		"xstudio_payment_status": cstr(booking.get("payment_status")),
		"xstudio_booking_type": mappers.service_key(booking),
		"xstudio_screen_size": cint(booking.get("screen_size")) or None,
		"xstudio_cameras": cint(booking.get("cameras")) or None,
		"xstudio_price_total": flt(booking.get("price_total"), 2),
		"xstudio_amount_due": flt(booking.get("amount_due"), 2),
		"xstudio_amount_paid": flt(booking.get("amount_paid"), 2),
		"xstudio_price_pending": 1 if booking.get("price_pending") else 0,
		"xstudio_deposit_due": flt(booking.get("deposit_due"), 2),
		"xstudio_hours": flt(booking.get("hours"), 2),
		"xstudio_starts_at": mappers.naive_cairo(booking.get("starts_at")),
		"xstudio_ends_at": mappers.naive_cairo(booking.get("ends_at")),
		"xstudio_crosses_midnight": 1 if crosses else 0,
		"xstudio_customer_name": cstr(booking.get("customer_name")),
		"xstudio_customer_phone": cstr(booking.get("customer_phone")),
		"xstudio_package_id": cstr(booking.get("package_id")) or None,
		"xstudio_hours_deducted": flt(booking.get("hours_deducted"), PRECISION),
		"xstudio_photographer": cstr(booking.get("photographer_id")) or None,
		"xstudio_cancelled_by": cstr(booking.get("cancelled_by")) or None,
		"source_updated_at": mappers.naive_cairo(booking.get("updated_at")),
		"source_payload": stable_json(booking),
		"source_payload_hash": mappers.booking_payload_hash(booking),
		"last_synced_at": now_datetime(),
		"xstudio_not_in_last_fetch": 0,
	}


def upsert_booking(context, booking):
	xid = cstr(booking.get("id"))
	if not xid:
		frappe.throw(_("The booking has no id."))
	key = import_key(xid)
	existing = frappe.db.get_value(
		"Booking", {"import_key": key}, ["name", "source_payload_hash", "sales_invoice", "journal_entry", "source_updated_at"], as_dict=True
	)
	values = booking_values(context, booking)
	if existing and existing.source_payload_hash == values["source_payload_hash"]:
		frappe.db.set_value("Booking", existing.name, {"last_synced_at": now_datetime(), "xstudio_not_in_last_fetch": 0}, update_modified=False)
		context.run.skipped()
		return existing.name
	if existing:
		posted = [
			name
			for doctype, name in (("Sales Invoice", existing.sales_invoice), ("Journal Entry", existing.journal_entry))
			if name and frappe.db.get_value(doctype, name, "docstatus") == 1
		]
		if posted:
			context.run.review(
				context.row_no, xid, _("Changed in XStudio after {0} was posted here; not changed. The accountant decides.").format(", ".join(posted))
			)
			return existing.name
		if existing.source_updated_at and values["source_updated_at"] and values["source_updated_at"] < existing.source_updated_at:
			context.run.skipped()
			return existing.name
		doc = frappe.get_doc("Booking", existing.name)
		doc.update(values)
		doc.flags.from_import = True
		doc.flags.ignore_permissions = True
		doc.save()
		context.run.updated()
		return doc.name
	doc = frappe.get_doc({"doctype": "Booking", **values, "source_system": SOURCE, "external_id": xid})
	doc.flags.from_import = True
	doc.flags.ignore_permissions = True
	doc.insert()
	context.run.inserted()
	return doc.name


# ---------- 5. the packages' ledgers ----------


def import_usage(context):
	items = [(xid, customer, row) for xid, (customer, row) in context.package_rows.items() if xid in context.packages]
	each(context, items, lambda item: append_usage(context, item[0], item[2]), lambda item: f"package {item[0]} usage")


def append_usage(context, xid, package):
	"""XStudio's package_usage rows (hours drawn above zero, given back below) as the package's history, each once
	by its id. Then the balance: Hours Used is the ledger's sum; Hours Remaining is what XStudio reports, which the
	ledger explains unless the package was edited by hand there."""
	name = context.packages[xid]
	rows = sorted(package.get("usage") or [], key=lambda u: cstr(u.get("created_at")))
	known = set(frappe.get_all("Studio Hour Package Usage", filters={"parent": name, "parenttype": "Studio Hour Package"}, pluck="external_id"))
	purchased = flt(frappe.db.get_value("Studio Hour Package", name, "hours_purchased"), PRECISION)
	used = flt(frappe.db.sql("select sum(hours) from `tabStudio Hour Package Usage` where parent = %s and parenttype = 'Studio Hour Package' for update", name)[0][0], PRECISION)
	idx = frappe.db.count("Studio Hour Package Usage", {"parent": name, "parenttype": "Studio Hour Package"})
	added = 0
	for row in rows:
		row_id = cstr(row.get("id"))
		if not row_id or row_id in known:
			continue
		hours = flt(row.get("hours"), PRECISION)
		booking = frappe.db.get_value("Booking", {"import_key": import_key(cstr(row.get("booking_id")))}, ["name", "booking_date"], as_dict=True) if row.get("booking_id") else None
		used = flt(used + hours, PRECISION)
		idx += 1
		frappe.get_doc(
			{
				"doctype": "Studio Hour Package Usage",
				"parent": name,
				"parenttype": "Studio Hour Package",
				"parentfield": "usage",
				"idx": idx,
				"booking": booking.name if booking else None,
				"booking_date": booking.booking_date if booking else None,
				"hours": hours,
				"balance": flt(purchased - used, PRECISION),
				"reason": (f"XStudio: {cstr(row.get('reason')) or 'usage'}" + ("" if booking else f" (booking {cstr(row.get('booking_id'))[:8]} not imported)"))[:140],
				"changed_by": frappe.session.user,
				"changed_on": mappers.naive_cairo(row.get("created_at")) or now_datetime(),
				"external_id": row_id,
			}
		).db_insert()
		added += 1
	remaining = flt(package.get("hours_remaining"), PRECISION)
	explained = abs(flt(purchased - used, PRECISION) - remaining) < 0.00005
	frappe.db.set_value(
		"Studio Hour Package",
		name,
		{
			"hours_used": used,
			"hours_remaining": remaining,
			"xstudio_hours_remaining": remaining,
			"xstudio_balance_matches": 1 if explained else 0,
			"status": mappers.package_status(package),
		},
		update_modified=False,
	)
	if added:
		context.run.created(added)
	if not explained:
		# XStudio's balance is the balance. Its usage rows not adding up to it is history: a package migrated from
		# the sheet (XStudio's import sets the remaining hours and writes no usage row for the hours already used) or
		# a balance set by hand there. Information only: nothing is recalculated and nothing needs doing.
		context.run.note(
			context.row_no,
			xid,
			_("Incomplete historical usage: XStudio's balance is {0}, its usage rows account for {1}. XStudio's balance is kept as is.").format(
				remaining, flt(purchased - used, PRECISION)
			),
		)


# ---------- 6. bookings the window no longer returns ----------


def find_missing(context, bookings, start, end):
	"""Bookings imported earlier whose start lies in the window but which XStudio did not return: XStudio never
	deletes a booking, so one was moved out of the window. It is looked for in its customer's list (GET
	/api/bookings?customerId=, itself capped at 500); found, it is brought up to date; not found, it is listed for
	review and marked, never cancelled or deleted here."""
	seen = {cstr(b.get("id")) for b in bookings}
	rows = frappe.get_all(
		"Booking",
		filters={
			"source_system": SOURCE,
			"xstudio_starts_at": ("between", [start.replace(tzinfo=None), (end - timedelta(seconds=1)).replace(tzinfo=None)]),
		},
		fields=["name", "external_id", "customer"],
	)
	missing = [row for row in rows if row.external_id not in seen]
	by_customer = {}
	for row in missing:
		xid = frappe.db.get_value("Customer", row.customer, "xstudio_customer_id")
		by_customer.setdefault(xid, []).append(row)
	for xid, group in by_customer.items():
		found = {}
		if xid:
			try:
				found = {cstr(b.get("id")): b for b in context.client.bookings(customer_id=xid)}
			except XStudioError as e:
				context.run.failed(context.next_row(), f"customer {xid} bookings", cstr(e)[:500])
				continue
		for row in group:
			row_no = context.next_row()
			booking = found.get(row.external_id)
			if booking:
				frappe.db.savepoint(SAVEPOINT)
				try:
					if cstr(booking.get("customer_id")) not in context.customers:
						upsert_customer(context, mappers.customer_from_booking(booking))
					upsert_booking(context, booking)
				except Exception as e:
					frappe.db.rollback(save_point=SAVEPOINT)
					frappe.clear_messages()
					context.run.failed(row_no, row.external_id, cstr(getattr(e, "message", None) or e)[:500])
			else:
				frappe.db.set_value("Booking", row.name, "xstudio_not_in_last_fetch", 1, update_modified=False)
				context.run.review(row_no, row.external_id, _("Not returned by XStudio for its day, nor in its customer's list: kept here as it was. Check it in XStudio."))
