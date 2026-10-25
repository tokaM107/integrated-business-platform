# Yesterday on the Owner Dashboard (requirements 5.1): the owner opens one screen and sees how every business did the
# day before, its printing, its bookings, the app's fees and whether the integrations ran. One call
# (get_yesterday), drawn by public/js/imed_owner_dashboard.js; each part is a few grouped queries, whatever the
# number of documents.
#
# Yesterday is the calendar day before today in the site's time zone (System Settings: Africa/Cairo): from 00:00
# yesterday to 00:00 today, excluded. Documents are taken by their business date, never their creation date: the
# ledger's posting date, a counter reading's date, a booking's date (the day of the service; the bookings made
# yesterday are counted apart), a doctor's ledger entry's date. Only the times of the imports and jobs are times.
#
#   money       each business's revenue, expenses and net in the ledger (business_figures.ledger: submitted, not
#               cancelled, accrual basis; a payment is not revenue). Expenses of the shared premises are on the
#               businesses once split; what is left on مصروفات المقر المشتركة was not split.
#   printing    each library's submitted Daily Counter Reading: every machine's opening, closing and sheets, the
#               sheets sold and the difference. A missing reading, one left in draft, a breakdown, a difference or a
#               machine without a library is a warning, never a zero.
#   bookings    the bookings of yesterday's date, halls and studio, by status; the studio's hours booked (not
#               cancelled, not a no-show) and delivered (Completed); those still open after their day.
#   app         the platform fees charged yesterday (Accrual and Adjustment entries of the app agreements), collected
#               (Collection entries) and owed at the end of the day (the receivable account's balance).
#   systems     the booking import, file imports (Data Import), the app's daily jobs, the assistant and e-mail, each
#               from its own record; one that keeps none says Not configured or Unknown, never OK.
#
# The owner's alone (Super Admin; Administrator): the money of every business at once.

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, nowdate
from frappe.utils.scheduler import is_scheduler_disabled

from imed_erp.imederp.business_figures import (
	NO_COST_CENTER,
	activities,
	business_tree,
	company,
	ledger,
	shared_cost_centers,
)
from imed_erp.imederp.owner_figures import balance

OWNER_ROLE = "Super Admin"
STUDIO, HALL = "Studio Service", "Hall"
OPEN_STATUSES = ("Tentative", "Confirmed with Deposit")
NOT_HELD = ("Cancelled", "No Show")
PLATFORM_RECEIVABLE = "مستحقات على الأطباء — رسوم المنصة"
# A daily job that has not run for this long is a warning.
JOB_LATE_HOURS = 36
# The app's daily jobs (hooks.py scheduler_events) by what they do; another one shows its module's name.
JOB_NAMES = {
	"imed_erp.imederp.doctor_accrual.run_daily": "Doctors' share of sales",
	"imed_erp.imederp.doctype.recurring_expense.recurring_expense.run_daily": "Monthly bills reminder",
}


def check_owner():
	if frappe.session.user != "Administrator" and OWNER_ROLE not in frappe.get_roles():
		frappe.throw(_("Only the owner sees yesterday's figures."), frappe.PermissionError)


def report_day(today=None):
	"""Yesterday: the calendar day before `today` (the site's today by default), and its bounds as times."""
	today = getdate(today or nowdate())
	day = add_days(today, -1)
	return frappe._dict(day=day, start=get_datetime(day), end=get_datetime(today))


@frappe.whitelist()
def get_yesterday():
	check_owner()
	period = report_day()
	return {
		"day": period.day,
		"currency": frappe.get_cached_value("Company", company(), "default_currency"),
		"money": money(period.day),
		"printing": printing(period.day),
		"bookings": bookings(period),
		"app": app_fees(period.day),
		"systems": systems(),
	}


def money(day):
	totals = ledger(day, day)
	shared = shared_cost_centers()
	rows = []
	for business in activities(business_tree()):
		rows.append(money_row(business.label, business.name, totals, business.name in shared))
	if totals.get((NO_COST_CENTER, "Income")) or totals.get((NO_COST_CENTER, "Expense")):
		rows.append(money_row(_("No business on the entry"), NO_COST_CENTER, totals))
	total = {key: flt(sum(row[key] for row in rows), 2) for key in ("revenue", "expenses", "net")}
	return {"rows": rows, "total": total}


def money_row(label, cost_center, totals, is_shared=False):
	revenue = -flt(totals.get((cost_center, "Income")))
	expenses = flt(totals.get((cost_center, "Expense")))
	return {
		"business": label,
		"cost_center": cost_center,
		"revenue": flt(revenue, 2),
		"expenses": flt(expenses, 2),
		"net": flt(revenue - expenses, 2),
		# The shared premises' expenses left on their own cost center: no rule split them.
		"not_split": is_shared and bool(expenses),
	}


def printing(day):
	machines = frappe.get_all("Printing Machine", filters={"disabled": 0}, fields=["name", "cost_center"])
	if not machines:
		return {"state": "not_configured", "libraries": [], "warnings": []}
	warnings = []
	without = [machine.name for machine in machines if not machine.cost_center]
	if without:
		warnings.append(
			_("{0} machine(s) have no library, so their counters are not read: {1}.").format(
				len(without), ", ".join(without)
			)
		)
	libraries = sorted({machine.cost_center for machine in machines if machine.cost_center})
	readings = frappe.get_all(
		"Daily Counter Reading",
		filters={"reading_date": day, "branch": ["in", libraries or [""]], "docstatus": ["<", 2]},
		fields=["name", "branch", "docstatus", "total_consumed", "sold_sheets", "variance"],
	)
	submitted = {reading.branch: reading for reading in readings if reading.docstatus == 1}
	drafts = {reading.branch for reading in readings if reading.docstatus == 0}
	lines = frappe.get_all(
		"Daily Counter Reading Item",
		filters={
			"parenttype": "Daily Counter Reading",
			"parent": ["in", [r.name for r in submitted.values()] or [""]],
		},
		fields=["parent", "machine", "opening_reading", "closing_reading", "consumed", "fault", "fault_note"],
		order_by="idx",
	)
	result = []
	for library in libraries:
		label = frappe.get_cached_value("Cost Center", library, "cost_center_name")
		reading = submitted.get(library)
		if not reading:
			warnings.append(
				_("{0}: the counter reading was saved but not submitted.").format(label)
				if library in drafts
				else _("{0}: no counter reading for the day.").format(label)
			)
			result.append({"library": label, "reading": None, "machines": []})
			continue
		rows = [line for line in lines if line.parent == reading.name]
		for line in rows:
			if line.fault:
				warnings.append(
					_("{0}: {1} broke down ({2}).").format(label, line.machine, line.fault_note or "")
				)
		if cint(reading.variance):
			warnings.append(
				_("{0}: the counters went up by {1} sheets, {2} were sold: a difference of {3}.").format(
					label, reading.total_consumed, reading.sold_sheets, reading.variance
				)
			)
		result.append(
			{
				"library": label,
				"reading": reading.name,
				"consumed": cint(reading.total_consumed),
				"sold": cint(reading.sold_sheets),
				"variance": cint(reading.variance),
				"machines": [
					{
						"machine": line.machine,
						"opening": cint(line.opening_reading),
						"closing": cint(line.closing_reading),
						"consumed": cint(line.consumed),
						"fault": bool(line.fault),
					}
					for line in rows
				],
			}
		)
	return {"state": "ok", "unit": _("sheets"), "libraries": result, "warnings": warnings}


def bookings(period):
	rows = frappe.get_all(
		"Booking",
		filters={"booking_date": period.day},
		fields=["resource_type", "status", "hours", "source_system", "xstudio_amount_due", "xstudio_amount_paid"],
	)
	by_status = {}
	for row in rows:
		kind = by_status.setdefault(row.resource_type or "", {})
		kind[row.status] = kind.get(row.status, 0) + 1
	studio = [row for row in rows if row.resource_type == STUDIO]
	made = frappe.db.count("Booking", [["creation", ">=", period.start], ["creation", "<", period.end]])
	return {
		"halls": summary(by_status.get(HALL, {})),
		"studio": summary(by_status.get(STUDIO, {})),
		"studio_hours_booked": flt(sum(flt(row.hours) for row in studio if row.status not in NOT_HELD), 2),
		"studio_hours_delivered": flt(sum(flt(row.hours) for row in studio if row.status == "Completed"), 2),
		# What XStudio says is due and paid on the studio's held bookings of the day: shown for monitoring, never
		# posted here (no invoice, no payment entry; owner's rule). The studio's money is in XStudio.
		"xstudio_due": flt(sum(flt(row.xstudio_amount_due) for row in studio if row.source_system == "xstudio" and row.status not in NOT_HELD), 2),
		"xstudio_paid": flt(sum(flt(row.xstudio_amount_paid) for row in studio if row.source_system == "xstudio" and row.status not in NOT_HELD), 2),
		# A day gone by and the booking neither completed nor cancelled: someone has to close it, here. An imported
		# one (XStudio) is closed there, and stays "pending" there as a rule: not counted.
		"still_open": len([row for row in rows if row.status in OPEN_STATUSES and not row.source_system]),
		"made_yesterday": made,
	}


def summary(statuses):
	held = sum(count for status, count in statuses.items() if status not in NOT_HELD)
	return {
		"held": held,
		"completed": statuses.get("Completed", 0),
		"cancelled": statuses.get("Cancelled", 0),
		"no_show": statuses.get("No Show", 0),
		"total": sum(statuses.values()),
	}


def app_fees(day):
	agreements = frappe.get_all("Doctor Agreement", filters={"agreement_type": "App"}, pluck="name")
	if not agreements:
		return {"state": "not_configured"}
	entries = frappe.db.sql(
		"""select entry_type, coalesce(sum(amount), 0) from `tabDoctor Ledger Entry`
		where docstatus = 1 and entry_date = %(day)s and agreement in %(agreements)s
		group by entry_type""",
		{"day": day, "agreements": tuple(agreements)},
	)
	amounts = {entry_type: flt(amount) for entry_type, amount in entries}
	abbr = frappe.get_cached_value("Company", company(), "abbr")
	account = f"{PLATFORM_RECEIVABLE} - {abbr}"
	return {
		"state": "ok",
		# Charged: what the students counted yesterday added to the doctors' accounts (a cancellation takes it off).
		"charged": flt(amounts.get("Accrual", 0) + amounts.get("Adjustment", 0), 2),
		# Collected: money actually received from the doctors (a Collection into a cash box), not the fee itself.
		"collected": flt(amounts.get("Collection", 0), 2),
		"outstanding": balance([account], 1, None, day) if frappe.db.exists("Account", account) else None,
		"subscriptions": frappe.db.count("App Subscription", {"docstatus": 1, "subscription_date": day}),
	}


def systems():
	return [booking_import(), file_imports(), *daily_jobs(), assistant(), email()]


def system(name, state, detail="", last_success=None, last_status=None):
	"""state: ok, warning, error, unknown or not_configured."""
	return {
		"name": name,
		"state": state,
		"detail": detail,
		"last_success": last_success,
		"last_status": last_status,
	}


def booking_import():
	"""The XStudio sync (imederp/xstudio/sync.py): its health from XStudio Settings and its last log."""
	settings = frappe.get_cached_doc("XStudio Settings")
	last = frappe.get_all(
		"Integration Import Log", filters={"source_system": "xstudio"}, fields=["name", "status", "finished_at"], order_by="finished_at desc", limit=1
	)
	last_status = last[0].status if last else None
	if not settings.enabled:
		return system(_("XStudio bookings"), "not_configured", _("The sync is off (XStudio Settings)."), last_success=settings.last_success_at, last_status=last_status)
	health = settings.health or "Never Run"
	state = {"Healthy": "ok", "Degraded": "warning", "Down": "error"}.get(health, "unknown")
	detail = settings.last_message or _("No run yet.")
	if last and last[0].status != "Failed":
		# Said in the reader's language, from the log's counts (the stored message is in the scheduler's).
		log = frappe.db.get_value("Integration Import Log", last[0].name, ["rows_read", "inserted", "updated", "skipped", "changed", "failed"], as_dict=True)
		detail = _("{0} read, {1} inserted, {2} updated, {3} unchanged, {4} to look at, {5} failed.").format(
			log.rows_read, log.inserted, log.updated, log.skipped, log.changed, log.failed
		)
	if health == "Down":
		detail = _("XStudio could not be read {0} times in a row: {1}").format(settings.consecutive_failures, detail)
	return system(_("XStudio bookings"), state, detail, last_success=settings.last_success_at, last_status=last_status)


def file_imports():
	imports = frappe.get_all(
		"Data Import",
		fields=["name", "reference_doctype", "status", "modified"],
		order_by="modified desc",
		limit=20,
	)
	if not imports:
		return system(_("File imports"), "unknown", _("No file has been imported yet."))
	last_success = next((row.modified for row in imports if row.status == "Success"), None)
	failed = [row for row in imports if row.status in ("Error", "Partial Success", "Timed Out")]
	pending = [row for row in imports if row.status == "Pending"]
	detail = []
	if failed:
		detail.append(
			_("{0} import(s) failed or partly failed, the last: {1} ({2}).").format(
				len(failed), _(failed[0].reference_doctype), _(failed[0].status)
			)
		)
	if pending:
		detail.append(_("{0} import(s) not run yet.").format(len(pending)))
	state = (
		"error" if imports[0].status in ("Error", "Timed Out") else "warning" if failed or pending else "ok"
	)
	return system(_("File imports"), state, " ".join(detail), last_success, imports[0].status)


def daily_jobs():
	jobs = frappe.get_all(
		"Scheduled Job Type",
		filters={"method": ["like", "imed_erp.%"]},
		fields=["name", "method", "stopped", "last_execution"],
	)
	scheduler_off = is_scheduler_disabled()
	result = []
	for job in jobs:
		label = _("Daily job: {0}").format(
			_(JOB_NAMES.get(job.method) or job.method.rsplit(".", 2)[-2].replace("_", " "))
		)
		failure = frappe.get_all(
			"Scheduled Job Log",
			filters={"scheduled_job_type": job.name, "status": "Failed"},
			fields=["creation", "details"],
			order_by="creation desc",
			limit=1,
		)
		failure = failure[0] if failure else None
		failed_last = failure and (not job.last_execution or failure.creation >= job.last_execution)
		late = (
			not job.last_execution
			or (get_datetime() - get_datetime(job.last_execution)).total_seconds() > JOB_LATE_HOURS * 3600
		)
		if scheduler_off or job.stopped:
			state, detail = "error", _("The scheduler is off: the job does not run.")
		elif failed_last:
			state, detail = "error", _("The last run failed: {0}").format(last_line(failure.details))
		elif late:
			state, detail = "warning", _("Has not run in the last {0} hours.").format(JOB_LATE_HOURS)
		else:
			state, detail = "ok", ""
		result.append(
			system(
				label,
				state,
				detail,
				None if failed_last else job.last_execution,
				"Failed" if failed_last else "Complete",
			)
		)
	return result


def last_line(details):
	"""The error's last line, without the traceback above it."""
	lines = [line.strip() for line in (details or "").splitlines() if line.strip()]
	return (lines[-1] if lines else _("no details"))[:160]


def assistant():
	from imed_erp.assistant.providers import get_provider

	if get_provider().connected:
		return system(_("AI assistant"), "ok", _("Connected to its model."))
	return system(_("AI assistant"), "not_configured", _("Not connected to a model yet."))


def email():
	if frappe.db.exists("Email Account", {"enable_outgoing": 1}):
		return system(_("Outgoing e-mail"), "ok", _("Notifications are also sent by e-mail."))
	return system(
		_("Outgoing e-mail"),
		"not_configured",
		_("No outgoing e-mail account: notifications stay in the system."),
	)
