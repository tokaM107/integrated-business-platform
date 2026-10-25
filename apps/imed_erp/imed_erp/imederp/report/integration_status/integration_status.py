# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The integrations at a glance (INT-09): one row per system (the libraries' point of sale, the studio's booking
# system, BA Plus), from their Integration Import Logs: the last import that went through (Completed, or
# Completed with Errors), what it imported and what failed, and the last run if it came after and failed. A
# system none of whose imports has run says so.
#
# "Import a Period Again" (the button on the report, reimport_period below) runs again the files that came in
# the days chosen, oldest first, each once: known records are skipped (INT-06), so only what failed or is new
# goes in, and each run writes its own log. Only a system whose import reads files has the button working: BA
# Plus today.

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate

from imed_erp.imederp.doctype.integration_import_log.integration_import_log import SOURCE_SYSTEMS

SYSTEM_LABELS = {"library_pos": "Libraries (point of sale)", "booking": "Studio (bookings, file)", "ba_plus": "BA Plus app", "xstudio": "XStudio (studio bookings, API)"}
DONE = ("Completed", "Completed with Errors")


def importers():
	"""The import that reads each system's file, for running a period again; a system missing here has none yet."""
	from imed_erp.imederp import app_import

	return {"ba_plus": app_import.import_content}


def execute(filters=None):
	return get_columns(), get_data()


def get_columns():
	return [
		{"label": _("System"), "fieldname": "system_label", "fieldtype": "Data", "width": 180},
		{"label": _("Last Successful Import"), "fieldname": "last_success", "fieldtype": "Datetime", "width": 160},
		{"label": _("Import Log"), "fieldname": "log", "fieldtype": "Link", "options": "Integration Import Log", "width": 150},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 150},
		{"label": _("Imported"), "fieldname": "inserted", "fieldtype": "Int", "width": 90},
		{"label": _("Skipped"), "fieldname": "skipped", "fieldtype": "Int", "width": 90},
		{"label": _("Changed in Source"), "fieldname": "changed", "fieldtype": "Int", "width": 120},
		{"label": _("Failed"), "fieldname": "failed", "fieldtype": "Int", "width": 80},
		{"label": _("Last Run"), "fieldname": "last_run", "fieldtype": "Datetime", "width": 160},
		{"label": _("Last Run Status"), "fieldname": "last_run_status", "fieldtype": "Data", "width": 150},
		{"label": _("Note"), "fieldname": "note", "fieldtype": "Data", "width": 260},
	]


def get_data():
	can_reimport = importers()
	rows = []
	for system in SOURCE_SYSTEMS:
		fields = ["name", "status", "finished_at", "inserted", "skipped", "changed", "failed", "message"]
		success = frappe.get_list(
			"Integration Import Log",
			filters={"source_system": system, "status": ("in", DONE)},
			fields=fields,
			order_by="finished_at desc, creation desc",
			limit=1,
		)
		last = frappe.get_list(
			"Integration Import Log", filters={"source_system": system}, fields=fields, order_by="finished_at desc, creation desc", limit=1
		)
		row = {"system": system, "system_label": _(SYSTEM_LABELS[system])}
		if success:
			s = success[0]
			row.update(
				last_success=s.finished_at, log=s.name, status=_(s.status), inserted=s.inserted, skipped=s.skipped, changed=s.changed, failed=s.failed
			)
		if last:
			row.update(last_run=last[0].finished_at, last_run_status=_(last[0].status))
		if not last:
			if system == "xstudio":
				row["note"] = _("No sync has run yet: enable it on XStudio Settings.")
			else:
				row["note"] = _("No import has run yet.") if system in can_reimport else _("Not connected yet: no import reads this system.")
		elif last[0].status == "Failed":
			row["note"] = _("The last run failed: {0}").format(last[0].message or "")
		elif cint(row.get("failed")) or cint(row.get("changed")):
			row["note"] = _("Open the log for the rows to look at.")
		rows.append(row)
	return rows


@frappe.whitelist()
def reimport_period(source_system, from_date, to_date):
	"""Run again the files of `source_system` that came in from_date..to_date (by the day they were imported),
	oldest first, each distinct file once. Returns the new logs. The owner and the accountant only, and the import
	itself checks the user may make what it imports."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	if source_system not in SOURCE_SYSTEMS:
		frappe.throw(_("Unknown source system {0}.").format(source_system))
	importer = importers().get(source_system)
	if not importer:
		frappe.throw(_("No import reads {0} yet, so there is nothing to run again.").format(_(SYSTEM_LABELS[source_system])))
	from_date, to_date = getdate(from_date), getdate(to_date)
	if to_date < from_date:
		frappe.throw(_("The period ends before it starts."))
	logs = frappe.get_all(
		"Integration Import Log",
		filters={
			"source_system": source_system,
			"started_at": ("between", [from_date, add_days(to_date, 1)]),
			"file_content": ("is", "set"),
		},
		fields=["name", "file_name", "file_hash", "file_content", "started_at"],
		order_by="started_at asc, creation asc",
	)
	# started_at is a datetime: "between" up to the next day's midnight takes in the whole last day.
	logs = [log for log in logs if from_date <= getdate(log.started_at) <= to_date]
	if not logs:
		frappe.throw(_("No file of {0} came in from {1} to {2}.").format(_(SYSTEM_LABELS[source_system]), from_date, to_date))
	done, results = set(), []
	for log in logs:
		if log.file_hash in done:
			continue
		done.add(log.file_hash)
		new = importer(log.file_content.encode(), file_name=log.file_name)
		results.append({"from": log.name, "log": new.name, "status": new.status, "inserted": new.inserted, "skipped": new.skipped, "failed": new.failed})
	return results
