# A read-only mirror of one document of the library's own system (Tanmya Market, SQL Server), read by the
# connector (scripts/library_connector) and written only by imederp/library_sync/sync.py. Nothing is posted from it.
import frappe
from frappe import _
from frappe.model.document import Document


class LibrarySalesDocument(Document):
	def validate(self):
		if not frappe.flags.library_sync and not frappe.flags.in_install and not frappe.flags.in_migrate:
			frappe.throw(_("{0} is read from the library system. Change it there; the next sync brings the change.").format(self.name or _("A library document")))

	def on_trash(self):
		if not frappe.flags.library_sync:
			frappe.throw(_("A library document is kept: it is the library system's record, mirrored here."))
