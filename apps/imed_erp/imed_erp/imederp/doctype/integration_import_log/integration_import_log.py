# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# One run of a daily import (INT-07, INT-09): which system, which file, when, by whom, how many rows were read,
# inserted, skipped as already imported, changed in the source and failed, and each row to look at with its
# reason. Shared by the imports of the three systems: BA Plus (app_import.py), the libraries' point of sale and
# the booking system.
#
# Only the import writes it (ImportRun below sets the flag); nobody adds, changes or deletes one, not even a
# System Manager, so what a run did stays as it was. The log is written in the same transaction as the rows it
# counts: a row rolled back to its savepoint is still listed as failed, and if the whole run is rolled back
# (a deadlock, a server error) a Failed log is written after the rollback and committed on its own.

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, now_datetime

SOURCE_SYSTEMS = ("ba_plus", "library_pos", "booking", "xstudio", "tanmya")
FAILED, CHANGED, REVIEW, NOTE = "Failed", "Changed in Source", "Needs Review", "Note"


class IntegrationImportLog(Document):
	def validate(self):
		if not self.flags.from_import_run:
			frappe.throw(_("An import log is written only by the import."), frappe.PermissionError)
		if self.source_system not in SOURCE_SYSTEMS:
			frappe.throw(_("Unknown source system {0}.").format(self.source_system))

	def on_trash(self):
		frappe.throw(_("An import log is kept: it cannot be deleted."), frappe.PermissionError)


class ImportRun:
	"""Counts one run and writes its log.

	run = ImportRun("ba_plus", file_name, content)
	run.read(); run.inserted(); run.updated(); run.skipped(); run.created(); run.changed(row_no, id, reason)
	run.review(row_no, id, reason); run.failed(row_no, id, reason)
	run.finish()          the log, Completed or Completed with Errors, in the caller's transaction
	run.abort(exception)  after rolling the whole run back: a Failed log, committed
	"""

	def __init__(self, source_system, file_name=None, content=None):
		if source_system not in SOURCE_SYSTEMS:
			frappe.throw(_("Unknown source system {0}.").format(source_system))
		self.source_system = source_system
		self.file_name = file_name
		raw = content if isinstance(content, bytes) else cstr(content).encode() if content else None
		self.file_hash = hashlib.sha256(raw).hexdigest() if raw else None
		# Kept with the log, so the file can be imported again for its period (INT-09).
		self.file_content = raw.decode("utf-8-sig") if raw else None
		self.started_at = now_datetime()
		self.counts = dict(rows_read=0, inserted=0, updated=0, records_created=0, skipped=0, changed=0, failed=0)
		self.rows = []

	def read(self):
		self.counts["rows_read"] += 1

	def inserted(self):
		self.counts["inserted"] += 1

	def updated(self):
		"""Already imported, changed in the source, and the change taken over (the XStudio sync does; file imports do not)."""
		self.counts["updated"] += 1

	def created(self, n=1):
		self.counts["records_created"] += n

	def skipped(self):
		self.counts["skipped"] += 1

	def changed(self, row_no, external_id, reason):
		self.counts["changed"] += 1
		self.rows.append({"row_no": row_no, "external_id": external_id, "kind": CHANGED, "reason": reason})

	def review(self, row_no, external_id, reason):
		"""Kept as it was, and listed for someone to decide: counted with the rows to look at."""
		self.counts["changed"] += 1
		self.rows.append({"row_no": row_no, "external_id": external_id, "kind": REVIEW, "reason": reason})

	def note(self, row_no, external_id, reason):
		"""Information only: listed on the log, counted nowhere, and the run is still Completed."""
		self.rows.append({"row_no": row_no, "external_id": external_id, "kind": NOTE, "reason": reason})

	def failed(self, row_no, external_id, reason):
		self.counts["failed"] += 1
		self.rows.append({"row_no": row_no, "external_id": external_id, "kind": FAILED, "reason": reason})

	def finish(self):
		status = "Completed with Errors" if self.counts["failed"] or self.counts["changed"] else "Completed"
		return self.write(status)

	def abort(self, exception):
		# The run's rows were rolled back with everything else: none of them was kept.
		self.counts.update(inserted=0, records_created=0)
		log = self.write("Failed", message=cstr(getattr(exception, "message", None) or exception))
		frappe.db.commit()
		return log

	def write(self, status, message=None):
		log = frappe.get_doc(
			{
				"doctype": "Integration Import Log",
				"source_system": self.source_system,
				"status": status,
				"started_at": self.started_at,
				"finished_at": now_datetime(),
				"run_by": frappe.session.user,
				"file_name": self.file_name,
				"file_hash": self.file_hash,
				"file_content": self.file_content,
				"message": message,
				"errors": self.rows,
				**self.counts,
			}
		)
		log.flags.from_import_run = True
		# Whoever may run an import may not necessarily read the logs; the run writes its own.
		log.flags.ignore_permissions = True
		log.insert()
		return log
