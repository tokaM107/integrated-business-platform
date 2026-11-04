# A read-only mirror of one document of the library's own system (Tanmya Market, SQL Server), read by the
# connector (scripts/library_connector) and written only by imederp/library_sync/sync.py. Nothing is posted from it.
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from imed_erp.imederp.library_sync.contract import RETURN_KINDS, SALES_KINDS


class LibrarySalesDocument(Document):
	def validate(self):
		if not frappe.flags.library_sync and not frappe.flags.in_install and not frappe.flags.in_migrate:
			frappe.throw(_("{0} is read from the library system. Change it there; the next sync brings the change.").format(self.name or _("A library document")))

	def on_trash(self):
		if not frappe.flags.library_sync:
			frappe.throw(_("A library document is kept: it is the library system's record, mirrored here."))


@frappe.whitelist()
def list_summary(cost_center=None):
	"""The band above the list: today's issued sales and returns (how many, how much) and when the library's
	connector last delivered; of one library when the list is filtered to its cost center (the sidebar's
	"Azarita Invoices" / "Mawasah Invoices"), of all otherwise. Read through get_list, so the user sees only what
	their permissions show."""
	today = nowdate()
	one = {"cost_center": cost_center} if cost_center else {}
	rows = frappe.get_list(
		"Library Sales Document",
		filters={
			"reg_date": ["between", [f"{today} 00:00:00", f"{today} 23:59:59"]],
			"is_final": 1,
			"is_cancelled": 0,
			"document_kind": ["in", SALES_KINDS + RETURN_KINDS],
			**one,
		},
		fields=["document_kind", {"COUNT": "*", "as": "n"}, {"SUM": "total", "as": "value"}],
		group_by="document_kind",
	)
	out = {"sales_count": 0, "sales_value": 0.0, "returns_count": 0, "returns_value": 0.0}
	for row in rows:
		side = "sales" if row.document_kind in SALES_KINDS else "returns"
		out[f"{side}_count"] += row.n
		out[f"{side}_value"] = flt(out[f"{side}_value"] + flt(row.value), 2)
	last = frappe.get_list("Library Sales Document", filters=one, fields=[{"MAX": "last_synced_at", "as": "at"}])
	out["last_synced_at"] = last[0].at if last else None
	out["currency"] = frappe.db.get_default("currency") or "EGP"
	return out
