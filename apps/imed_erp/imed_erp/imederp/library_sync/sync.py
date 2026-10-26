# The ERP end of the library connector (scripts/library_connector/tanmya_connector.py): one batch of documents
# in, one Integration Import Log out, Library Sales Documents upserted by their source id. Read-only toward the
# library (the connector only SELECTs) and nothing financial here: no invoice, payment, journal or stock entry.
#
#   new import_key                 inserted
#   known, same payload hash       skipped
#   known, different hash          updated (the library is the source of truth), listed as Changed in Source
#   unknown operation code         imported as kind Other and listed for review
#   a row that cannot be mapped    fails alone, with the key it lacks; the others go on
import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from imed_erp.imederp.doctype.integration_import_log.integration_import_log import ImportRun
from imed_erp.imederp.library_sync import contract as c
from imed_erp.imederp.library_sync.mappers import MappingError, map_document

ROLES = ("System Manager", "Accounts Manager")
LOCK = "imed_library_sync"
SAVEPOINT = "library_doc"


@frappe.whitelist()
def receive(batch=None):
	"""POST /api/method/imed_erp.imederp.library_sync.sync.receive  {"batch": {...}} (token auth)."""
	frappe.only_for(ROLES)
	if isinstance(batch, str):
		batch = json.loads(batch)
	batch = frappe._dict(batch or {})
	if not batch.get("documents"):
		frappe.throw(_("The batch holds no documents."))
	log = import_batch(batch)
	return {"log": log.name, "status": log.status, "counts": {k: log.get(k) for k in ("rows_read", "inserted", "updated", "skipped", "changed", "failed")}}


def import_batch(batch):
	source = batch.get("source") or c.SOURCE
	if source != c.SOURCE:
		frappe.throw(_("Unknown source {0}.").format(source))
	if cint(frappe.db.sql("select get_lock(%s, 5)", LOCK)[0][0]) != 1:
		frappe.throw(_("Another library batch is being imported. Try again in a moment."))
	try:
		return _import(batch)
	finally:
		frappe.db.sql("select release_lock(%s)", LOCK)


def _import(batch):
	settings = {k: batch.get(k) or {} for k in ("branch_map", "operation_map")}
	settings["issued_status_codes"] = batch.get("issued_status_codes") or []
	settings["cancelled_status_codes"] = batch.get("cancelled_status_codes") or []
	documents = batch.get("documents") or []
	run = ImportRun(c.SOURCE, file_name=_("Library connector batch of {0} documents, read {1}").format(len(documents), batch.get("read_at") or "?"))
	frappe.flags.library_sync = True
	try:
		for row_no, document in enumerate(documents, start=1):
			run.read()
			family = document.get("_family") or "stock"
			external_id = str(document.get(c.FAMILIES.get(family, c.FAMILIES["stock"])["id"]) or "?")
			frappe.db.savepoint(SAVEPOINT)
			try:
				import_one(run, row_no, family, external_id, document, settings)
			except MappingError as e:
				frappe.db.rollback(save_point=SAVEPOINT)
				run.failed(row_no, external_id, str(e))
			except Exception as e:
				frappe.db.rollback(save_point=SAVEPOINT)
				run.failed(row_no, external_id, frappe.utils.cstr(getattr(e, "message", None) or e)[:300])
		log = run.finish()
		if not frappe.flags.in_test:
			frappe.db.commit()
		return log
	finally:
		frappe.flags.library_sync = False


def import_one(run, row_no, family, external_id, document, settings):
	fields, notes = map_document(family, document, settings)
	lines = fields.pop("lines")
	existing = frappe.db.get_value("Library Sales Document", {"import_key": fields["import_key"]}, ["name", "payload_hash"], as_dict=True)
	if existing and existing.payload_hash == fields["payload_hash"]:
		run.skipped()
		frappe.db.set_value("Library Sales Document", existing.name, "last_synced_at", now_datetime(), update_modified=False)
		return
	fields["last_synced_at"] = now_datetime()
	fields["source_payload"] = json.dumps({k: v for k, v in document.items() if not str(k).startswith("_")}, ensure_ascii=False, default=str)
	if existing:
		doc = frappe.get_doc("Library Sales Document", existing.name)
		doc.update(fields)
		doc.set("lines", [])
		for line in lines:
			doc.append("lines", line)
		doc.save(ignore_permissions=True)
		run.updated()
		run.changed(row_no, external_id, _("Changed in the library system after it was read; the copy here now follows it."))
	else:
		doc = frappe.get_doc({"doctype": "Library Sales Document", **fields})
		for line in lines:
			doc.append("lines", line)
		doc.insert(ignore_permissions=True)
		run.inserted()
		run.created(1)
	for note in notes:
		run.review(row_no, external_id, note)
