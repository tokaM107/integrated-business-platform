# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The halls' bookings and their money, read from Sparkle, the halls' booking site (owner, 5 Nov 2026: most hall
# bookings are made there; Sparkle stays the only place a hall is booked, the ERP shows them and keeps the money's
# accounts). It runs every few minutes from the scheduler (Sparkle Settings: Every), or by hand (Sync Now).
#
#   1. the bookings on or after Bookings From, with their price, their customers and the halls they hold
#   2. a Booking here per hall a booking holds: one for most, both halls for a combined one (5 + 6), so neither
#      can be taken twice; the price and what was paid sit on the first, the other says it is part of it. A hall
#      not mapped (the call center, never rented) is skipped and noted.
#   3. the renter: the customer with the same phone, else a new one (Customer Group of the settings)
#   4. each payment entry once, as a Journal Entry: hall revenue on the day it was paid, into the box of its
#      method (cash, InstaPay and bank transfers, the wallet); paid on or before Custody Until, into the owner's
#      custody, the money having been handed over already. A reversal, a refund or a voided duplicate takes its
#      amount back the same way; the undoing of a reversal brings it in again.
#
# What is stored on a booking or an entry (a note, a reason, a remark) is written in Arabic, whatever language
# the run happens in: it is data, read by the staff. Nothing in Sparkle is changed (client.py reads only). A booking or a payment that cannot be taken is listed on
# the run's Integration Import Log with its reason, and tried again on the next run; the others go on.

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, get_datetime, getdate, now_datetime, time_diff_in_seconds

from imed_erp.imederp.booking_rules import CANCELLED, COMPLETED, CONFIRMED_NO_DEPOSIT, TENTATIVE
from imed_erp.imederp.customers import customer_with_phone, phone_key_or_none
from imed_erp.imederp.doctype.integration_import_log.integration_import_log import ImportRun
from imed_erp.imederp.sparkle.client import SparkleClient, SparkleError

SOURCE = "sparkle"
SETTINGS = "Sparkle Settings"
LOCK = "imed_erp_sparkle_sync"
SAVEPOINT = "sparkle_record"
RUN_SAVEPOINT = "sparkle_run"
MANAGERS = ("System Manager", "Accounts Manager")
STATUS = {"pending": TENTATIVE, "confirmed": CONFIRMED_NO_DEPOSIT, "completed": COMPLETED, "cancelled": CANCELLED}
ACTIVITY = {
	"lecture": "محاضرة",
	"course": "كورس",
	"meeting": "اجتماع",
	"workshop": "ورشة",
	"seminar": "سيمينار",
	"content_creation": "تصوير محتوى",
	"other": "أخرى",
}
# What each entry does to the money (Sparkle's own rule, src/lib/finance-model.ts entrySign): + in, - out.
SIGN = {"payment": 1, "reversal_undo": 1, "reversal": -1, "refund": -1, "duplicate_void": -1}
KIND_NAME = {"payment": "دفعة", "reversal_undo": "إلغاء استرجاع", "reversal": "استرجاع", "refund": "رد فلوس", "duplicate_void": "إلغاء دفعة مكررة"}


class SyncStopped(Exception):
	"""The whole run is over (the database rolled it back)."""


def is_enabled():
	"""While the sync is on, the halls are booked on Sparkle only (Booking.validate refuses one made here)."""
	return cint(frappe.db.get_single_value(SETTINGS, "enabled"))


# ---------- entry points ----------


@frappe.whitelist()
def sync_now():
	"""Sync Now on Sparkle Settings: one run, by the owner or the accountant."""
	frappe.only_for(MANAGERS)
	log = run(trigger="manual")
	return {field: log.get(field) for field in ("name", "status", "rows_read", "inserted", "updated", "skipped", "changed", "failed", "message")}


def run_scheduled():
	"""The scheduler's entry (every 10 minutes): a run when the settings say it is time."""
	settings = frappe.get_single(SETTINGS)
	if not settings.enabled:
		return None
	if settings.last_attempt_at and time_diff_in_seconds(now_datetime(), settings.last_attempt_at) < cint(settings.poll_minutes or 10) * 60 - 30:
		return None
	return run(trigger="scheduler")


@frappe.whitelist()
def dry_run():
	"""What a run would do, without keeping anything (the first look before the first import):
	  bench --site frontend execute imed_erp.imederp.sparkle.sync.dry_run"""
	frappe.only_for(MANAGERS)
	return run(trigger="dry run", dry_run=True)


def run(trigger="scheduler", dry_run=False, client=None):
	"""One run. Returns its Integration Import Log (a dict of what it would do, for a dry run). `client` is the
	tests' stand-in for Sparkle."""
	settings = frappe.get_single(SETTINGS)
	if not settings.enabled and not dry_run:
		frappe.throw(_("The Sparkle sync is not enabled (Sparkle Settings)."), title=_("Sync Disabled"))
	if cint(frappe.db.sql("select get_lock(%s, 0)", LOCK)[0][0]) != 1:
		frappe.throw(_("A Sparkle sync is already running. Wait for it to finish."), title=_("Already Running"))
	try:
		return _run(settings, trigger, dry_run, client or SparkleClient(settings))
	finally:
		frappe.db.sql("select release_lock(%s)", LOCK)


def _run(settings, trigger, dry_run, client):
	label = f"Sparkle bookings from {settings.start_date} ({trigger})"
	run = ImportRun(SOURCE, file_name=label)
	if not dry_run:
		set_state(last_attempt_at=now_datetime())
	frappe.db.savepoint(RUN_SAVEPOINT)
	try:
		context = Context(settings, run)
		read(context, client)
		each(context, context.bookings, lambda b: import_booking(context, b), lambda b: f"booking {b['id']}")
		each(context, context.payments, lambda p: post_payment(context, p), lambda p: f"payment {p['id']}")
		log = run.finish()
		if dry_run:
			rows = [dict(row) for row in run.rows]
			frappe.db.rollback(save_point=RUN_SAVEPOINT)
			return {"dry_run": True, "window": label, "status": log.status, "counts": {k: log.get(k) for k in ("rows_read", "inserted", "updated", "skipped", "changed", "failed")}, "rows": rows}
		set_state(last_success_at=now_datetime(), consecutive_failures=0, last_message=summary(log), health="Healthy" if log.status == "Completed" else "Degraded")
		return log
	except Exception as e:
		try:
			frappe.db.rollback(save_point=RUN_SAVEPOINT)
		except Exception:
			frappe.db.rollback()
		message = cstr(getattr(e, "message", None) or e)
		if dry_run:
			return {"dry_run": True, "window": label, "status": "Failed", "message": message}
		failures = cint(frappe.db.get_single_value(SETTINGS, "consecutive_failures")) + 1
		if frappe.flags.in_test:
			run.counts.update(inserted=0, records_created=0, updated=0)
			log = run.write("Failed", message=message)
		else:
			log = run.abort(e)
		set_state(consecutive_failures=failures, last_message=message[:500], health="Down" if failures >= 3 else "Degraded")
		if not frappe.flags.in_test:
			frappe.db.commit()
		if not isinstance(e, (SparkleError, SyncStopped)):
			frappe.log_error(title="Sparkle sync failed", message=frappe.get_traceback())
		return log
	finally:
		client.close()


def set_state(**values):
	frappe.db.set_single_value(SETTINGS, values, update_modified=False)


def summary(log):
	return _("{0} read, {1} inserted, {2} updated, {3} unchanged, {4} to look at, {5} failed.").format(
		log.rows_read, log.inserted, log.updated, log.skipped, log.changed, log.failed
	)


class Context:
	def __init__(self, settings, run):
		self.settings = settings
		self.run = run
		self.hall_map = {cstr(row.sparkle_hall).strip(): row.resource for row in settings.hall_map}
		self.company = frappe.db.get_value("Cost Center", settings.cost_center, "company") if settings.cost_center else None
		self.customers = {}  # Sparkle customer id -> its row
		self.resources = {}  # booking id -> [halls it holds]
		self.net_paid = {}  # booking id -> what was paid, net
		self.bookings, self.payments = [], []
		self.renters = {}  # phone key -> Customer, this run
		self.row_no = 0

	def next_row(self):
		self.row_no += 1
		self.run.read()
		return self.row_no


def read(context, client):
	if not context.settings.start_date:
		raise SparkleError(_("Sparkle Settings has no Bookings From."))
	context.bookings = client.bookings(str(context.settings.start_date))
	ids = [b["id"] for b in context.bookings]
	for row in client.resources(ids):
		context.resources.setdefault(row["booking_id"], []).append(row)
	context.customers = {c["id"]: c for c in client.customers({b["customer_id"] for b in context.bookings if b.get("customer_id")})}
	context.payments = client.payments(ids)
	for p in context.payments:
		context.net_paid[p["booking_id"]] = flt(context.net_paid.get(p["booking_id"])) + SIGN.get(p["kind"], 0) * flt(p["amount"])


def each(context, items, work, label):
	"""`work(item)` for each item, in its own savepoint: one that fails is listed, the others go on."""
	for item in items:
		row_no = context.next_row()
		frappe.db.savepoint(SAVEPOINT)
		try:
			work(item)
		except Exception as e:
			try:
				frappe.db.rollback(save_point=SAVEPOINT)
			except Exception:
				raise SyncStopped(_("The run stopped at {0}: the database rolled it back. Nothing of this run was kept; the next run is safe.").format(label(item)))
			frappe.clear_messages()
			context.run.failed(row_no, label(item), cstr(getattr(e, "message", None) or e)[:500])


# ---------- 2. bookings ----------


def halls_of(context, booking):
	"""The halls a booking holds, each with its resource here; those not mapped (the call center) are left out."""
	rows = context.resources.get(booking["id"]) or [
		{"physical_slug": booking["hall_slug"], "booking_date": booking["booking_date"], "start_time": booking["start_time"], "end_time": booking["end_time"]}
	]
	mapped = [(row, context.hall_map.get(cstr(row["physical_slug"]).strip())) for row in rows]
	return [(row, resource) for row, resource in mapped if resource], [row["physical_slug"] for row, resource in mapped if not resource]


def import_booking(context, booking):
	halls, unmapped = halls_of(context, booking)
	if unmapped:
		context.run.note(context.row_no, booking["id"], _("Sparkle hall {0} is not mapped to a hall here (Sparkle Settings): not imported.").format(", ".join(unmapped)))
	if not halls:
		context.run.skipped()
		return
	customer = renter(context, booking)
	combined = len(halls) > 1
	keys = []
	outcome = "skipped"
	for i, (row, resource) in enumerate(halls):
		external_id = f"{booking['id']}:{row['physical_slug']}" if combined else booking["id"]
		keys.append(f"{SOURCE}:{external_id}")
		values = booking_values(context, booking, row, resource, customer, first=(i == 0), combined=combined)
		done = upsert(external_id, values)
		if done != "skipped":
			outcome = done
	cancel_left_behind(booking["id"], keys)
	getattr(context.run, outcome)()


def booking_values(context, booking, row, resource, customer, first, combined):
	status = STATUS.get(booking["status"], TENTATIVE)
	starts = get_datetime(f"{row['booking_date']} {row['start_time']}")
	if status == COMPLETED and starts > now_datetime():
		status = CONFIRMED_NO_DEPOSIT  # marked done in Sparkle before it started: still to come here
	total = flt(booking.get("final_total"), 2) if first else 0
	paid = max(flt(context.net_paid.get(booking["id"]), 2), 0) if first else 0
	notes = [cstr(booking.get("notes")).strip()]
	if paid > total:
		notes.append("Sparkle: اتدفع {0}، أكتر من سعره {1}.".format(paid, total))
		total = paid
	if combined:
		notes.append("جزء من حجز واحد في Sparkle لـ {0}: سعره ومدفوعاته على حجز القاعة الأولى.".format(booking["hall_slug"]))
	payload = {**booking, "hall": row, "net_paid": context.net_paid.get(booking["id"], 0)}
	stable = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
	phone = phone_key_or_none(booking.get("whatsapp"))
	return {
		"resource": resource,
		"customer": customer,
		"booking_date": row["booking_date"],
		"from_time": row["start_time"],
		"to_time": row["end_time"],
		"status": status,
		"cancellation_reason": (cstr(booking.get("settlement_note")).strip() or "اتلغى في Sparkle.") if status == CANCELLED else None,
		"hall_booking_type": "Fixed-fee Rental",
		"rental_model": "Fixed Rent",
		"activity": ACTIVITY.get(booking.get("type"), cstr(booking.get("type")) or "أخرى"),
		"responsible_name": cstr(booking.get("full_name")).strip() or frappe.db.get_value("Customer", customer, "customer_name"),
		"responsible_phone": phone or frappe.db.get_value("Customer", customer, "mobile_no"),
		"notes": "\n".join(n for n in notes if n) or None,
		"total_amount": total,
		"paid_amount": paid,
		"source_payload": stable,
		"source_payload_hash": hashlib.sha256(stable.encode()).hexdigest(),
		"last_synced_at": now_datetime(),
	}


def upsert(external_id, values):
	key = f"{SOURCE}:{external_id}"
	existing = frappe.db.get_value("Booking", {"import_key": key}, ["name", "source_payload_hash"], as_dict=True)
	if existing and existing.source_payload_hash == values["source_payload_hash"]:
		frappe.db.set_value("Booking", existing.name, "last_synced_at", now_datetime(), update_modified=False)
		return "skipped"
	doc = frappe.get_doc("Booking", existing.name) if existing else frappe.get_doc({"doctype": "Booking", "source_system": SOURCE, "external_id": external_id})
	doc.update(values)
	doc.flags.from_import = True
	doc.flags.ignore_permissions = True
	doc.save() if existing else doc.insert()
	return "updated" if existing else "inserted"


def cancel_left_behind(booking_id, keys):
	"""A booking moved in Sparkle to another hall (or from one hall to a combined one): the hall it left is freed."""
	for name, key in frappe.get_all(
		"Booking",
		filters={"source_system": SOURCE, "external_id": ["like", f"{booking_id}%"], "status": ["!=", CANCELLED]},
		fields=["name", "import_key"],
		as_list=True,
	):
		if key not in keys:
			doc = frappe.get_doc("Booking", name)
			doc.status, doc.cancellation_reason = CANCELLED, "اتنقل لقاعة تانية في Sparkle."
			doc.total_amount = doc.paid_amount = 0
			doc.flags.from_import = True
			doc.flags.ignore_permissions = True
			doc.save()


def renter(context, booking):
	"""The booking's customer: the one with the same phone, else a new one."""
	known = context.customers.get(booking.get("customer_id")) or {}
	name = cstr(known.get("full_name") or booking.get("full_name")).strip()
	phone = known.get("phone_normalized") or booking.get("whatsapp")
	key = phone_key_or_none(phone)
	if key and key in context.renters:
		return context.renters[key]
	found = customer_with_phone(key) if key else None
	if found:
		customer = found.name
	else:
		if not key and name and frappe.db.exists("Customer", {"customer_name": name}):
			return frappe.db.get_value("Customer", {"customer_name": name}, "name")
		from imed_erp.imederp.xstudio.sync import default_territory

		doc = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name or "زبون Sparkle {0}".format(cstr(booking["id"])[:8]),
				"customer_type": "Company" if known.get("company") else "Individual",
				"customer_group": context.settings.customer_group or frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups",
				"territory": default_territory(),
				"mobile_no": phone if key else None,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		context.run.created()
		customer = doc.name
	if key:
		context.renters[key] = customer
	return customer


# ---------- 4. payments ----------


def box_of(context, payment):
	s = context.settings
	if s.custody_until and getdate(payment["paid_on"]) <= getdate(s.custody_until):
		return s.custody_account
	return {
		"cash": s.cash_account,
		"instapay": s.instapay_account,
		"bank_transfer": s.instapay_account,  # owner, 5 Nov 2026: a bank transfer is counted as InstaPay
		"wallet": s.wallet_account,
	}.get(payment["method"]) or s.other_account or s.cash_account


def post_payment(context, payment):
	"""One payment entry of Sparkle, once: a Journal Entry between its box and the halls' revenue."""
	if frappe.db.exists("Journal Entry", {"sparkle_payment_id": payment["id"], "docstatus": 1}):
		context.run.skipped()
		return
	sign = SIGN.get(payment["kind"])
	if sign is None:
		frappe.throw(_("Unknown kind of payment in Sparkle: {0}.").format(payment["kind"]))
	s = context.settings
	box = box_of(context, payment)
	if not (box and s.income_account and s.cost_center):
		frappe.throw(_("Sparkle Settings needs its revenue account, cost center and the box for {0}.").format(payment["method"]))
	booking = frappe.db.get_value("Booking", {"source_system": SOURCE, "external_id": ["like", f"{payment['booking_id']}%"]}, "name", order_by="external_id")
	amount = flt(payment["amount"], 2)
	money_in = {"account": box, "debit_in_account_currency": amount, "cost_center": s.cost_center}
	money_out = {"account": s.income_account, "credit_in_account_currency": amount, "cost_center": s.cost_center}
	if sign < 0:
		money_in = {"account": s.income_account, "debit_in_account_currency": amount, "cost_center": s.cost_center}
		money_out = {"account": box, "credit_in_account_currency": amount, "cost_center": s.cost_center}
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Cash Entry",
			"company": context.company,
			"posting_date": payment["paid_on"],
			"sparkle_payment_id": payment["id"],
			"user_remark": "Sparkle: {0} بـ {1} لحجز {2} ({3}){4}".format(
				KIND_NAME.get(payment["kind"], payment["kind"]),
				amount,
				booking or payment["booking_id"],
				payment["method"],
				f" — {cstr(payment.get('note')).strip()}" if cstr(payment.get("note")).strip() else "",
			)[:1000],
			"accounts": [money_in, money_out],
		}
	)
	from imed_erp.imederp.system_user import as_administrator

	with as_administrator():
		entry.flags.ignore_permissions = True
		entry.insert()
		entry.submit()
	context.run.inserted()
