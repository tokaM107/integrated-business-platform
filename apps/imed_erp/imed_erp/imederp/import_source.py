# Where a record came from (INT-01, INT-06, INT-14), for the app's records that an import also makes: App Course
# and App Subscription (the booking keeps its own, booking.py check_source).
#
# Every such record has source (Manual / Imported), source_system, external_id, import_key (unique: the system and
# the id together) and import_log. Only an import makes an imported record (it sets doc.flags.from_import), and a
# record entered by hand can never claim to be imported. An imported record is changed in its source system, and
# the next import lists the change (it never overwrites it); here only the fields named as the ERP's own may change.

import frappe
from frappe import _

MANUAL, IMPORTED = "Manual", "Imported"
SOURCE_FIELDS = ("source", "source_system", "external_id", "import_key", "import_log")


def check_source(doc, own_fields=()):
	"""Call from validate (and before_update_after_submit for a submitted record)."""
	if doc.flags.from_import:
		doc.source = IMPORTED
		if not (doc.source_system and doc.external_id):
			frappe.throw(_("An imported record needs its source system and its id there."))
		doc.import_key = f"{doc.source_system}:{doc.external_id}"
		return
	if doc.is_new():
		doc.source = MANUAL
		for field in SOURCE_FIELDS[1:]:
			doc.set(field, None)
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	for field in SOURCE_FIELDS:
		doc.set(field, before.get(field))
	if before.source != IMPORTED:
		return
	changed = [
		df.label or df.fieldname
		for df in doc.meta.fields
		if df.fieldtype not in frappe.model.no_value_fields
		and df.fieldname not in (*SOURCE_FIELDS, *own_fields)
		and doc.has_value_changed(df.fieldname)
	]
	if changed:
		frappe.throw(
			_("{0} was imported from {1}. Change it there; the next import lists the change. Changed here: {2}.").format(
				doc.name, before.source_system, ", ".join(_(label) for label in changed)
			),
			title=_("Imported Record"),
		)
