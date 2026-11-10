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

# The connector's own user holds Library Connector and nothing else (setup/setup_library_connector.py). Only it (and
# the system's manager) writes the mirrored documents: not the accountant, whose Accounts Manager could otherwise make
# up a library's sales (security review of 10 Nov 2026).
ROLES = ("System Manager", "Library Connector")
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
	import re

	library = str(batch.get(c.LIBRARY_KEY) or "").strip()
	if not re.match(c.LIBRARY_SLUG, library):
		frappe.throw(_("The batch names no library (a short slug such as 'pc1' in the connector's config.json): refused, so two libraries' documents are never mixed."))
	if cint(frappe.db.sql("select get_lock(%s, 5)", LOCK)[0][0]) != 1:
		frappe.throw(_("Another library batch is being imported. Try again in a moment."))
	try:
		return _import(batch)
	finally:
		frappe.db.sql("select release_lock(%s)", LOCK)


def allowed_cost_centers():
	"""The cost centers a batch may file documents under: a library's (a leaf cost center named مكتبة ...), and, when
	the connector's user is bound to some (User Permissions on Cost Center: one user a library), those only. The batch
	names its cost centers itself (its branch_map); without this a stolen key could file sales under any cost center,
	or one library's PC under the other's (security review of 10 Nov 2026)."""
	libraries = set(frappe.get_all("Cost Center", filters={"is_group": 0, "cost_center_name": ["like", "مكتبة%"]}, pluck="name"))
	bound = set(frappe.get_all("User Permission", filters={"user": frappe.session.user, "allow": "Cost Center"}, pluck="for_value"))
	return libraries & bound if bound else libraries


def _import(batch):
	settings = {k: batch.get(k) or {} for k in ("branch_map", "operation_map")}
	allowed = allowed_cost_centers()
	refused = {code: cc for code, cc in settings["branch_map"].items() if cc not in allowed}
	if refused:
		frappe.throw(
			_("The batch maps branches to cost centers that are not this connector's library: {0}. Refused; nothing was imported.").format(
				", ".join(f"{code} → {cc}" for code, cc in refused.items())
			),
			frappe.PermissionError,
		)
	settings["library"] = str(batch.get(c.LIBRARY_KEY)).strip()
	settings["allowed_cost_centers"] = allowed
	settings["issued_status_codes"] = batch.get("issued_status_codes") or []
	settings["cancelled_status_codes"] = batch.get("cancelled_status_codes") or []
	documents = batch.get("documents") or []
	run = ImportRun(c.SOURCE, file_name=_("Library {0}: connector batch of {1} documents, read {2}").format(settings["library"], len(documents), batch.get("read_at") or "?"))
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
	existing = frappe.db.get_value("Library Sales Document", {"import_key": fields["import_key"]}, ["name", "payload_hash", "cost_center"], as_dict=True)
	# A document already filed under a library this connector may not write (another library's PC sending the other's
	# name) is never changed from here (security review of 10 Nov 2026).
	if existing and existing.cost_center and existing.cost_center not in settings.get("allowed_cost_centers", {existing.cost_center}):
		raise MappingError(_("{0} belongs to {1}, which this connector does not write; left unchanged.").format(existing.name, existing.cost_center))
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
