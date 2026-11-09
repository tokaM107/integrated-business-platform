# A read-only mirror of one document of the library's own system (Tanmya Market, SQL Server), read by the
# connector (scripts/library_connector) and written only by imederp/library_sync/sync.py. Nothing is posted from it.
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from imed_erp.imederp.library_sync.contract import RETURN_KINDS, SALES_KINDS


def on_doctype_update():
	"""A library's documents of a day or a stretch of days: the owner's page reads them by library and date (owner_periods,
	owner_overview). Without this index each of those reads went through the whole table: 54,063 documents on the live
	site on 9 Nov 2026, over a minute for the page."""
	frappe.db.add_index("Library Sales Document", ["cost_center", "reg_date"])
	# The list itself, newest first, and the band's "last update" (its latest document): by date alone.
	frappe.db.add_index("Library Sales Document", ["reg_date"])


class LibrarySalesDocument(Document):
	def validate(self):
		if not frappe.flags.library_sync and not frappe.flags.in_install and not frappe.flags.in_migrate:
			frappe.throw(_("{0} is read from the library system. Change it there; the next sync brings the change.").format(self.name or _("A library document")))

	def on_trash(self):
		if not frappe.flags.library_sync:
			frappe.throw(_("A library document is kept: it is the library system's record, mirrored here."))


# The date conditions the list's date filter can carry (the bar above the table, a quick chip, a link).
DATE_OPERATORS = ("between", "timespan", ">=", "<=", ">", "<", "=")


@frappe.whitelist()
def list_summary(cost_center=None, date_filter=None):
	"""The band above the list: the issued sales and returns (how many, how much) of the dates the list shows (the
	owner, 9 Nov 2026: "the revenue of this stretch, from this date to that"), today's when it shows every date, and
	when the library's connector last delivered; of one library when the list is filtered to its cost center (the
	sidebar's "Azarita Invoices" / "Mawasah Invoices"), of all otherwise. Read through get_list, so the user sees only
	what their permissions show."""
	date_filter = frappe.parse_json(date_filter) if date_filter else None
	if date_filter and (not isinstance(date_filter, list) or len(date_filter) != 2 or str(date_filter[0]).lower() not in DATE_OPERATORS):
		frappe.throw(_("Unknown date filter."))
	today = nowdate()
	one = {"cost_center": cost_center} if cost_center else {}
	dates = [["reg_date", date_filter[0], date_filter[1]]] if date_filter else [["reg_date", "between", [f"{today} 00:00:00", f"{today} 23:59:59"]]]
	rows = frappe.get_list(
		"Library Sales Document",
		filters=[
			*dates,
			["is_final", "=", 1],
			["is_cancelled", "=", 0],
			["document_kind", "in", SALES_KINDS + RETURN_KINDS],
			*[[k, "=", v] for k, v in one.items()],
		],
		fields=["document_kind", {"COUNT": "*", "as": "n"}, {"SUM": "total", "as": "value"}],
		group_by="document_kind",
	)
	out = {"sales_count": 0, "sales_value": 0.0, "returns_count": 0, "returns_value": 0.0, "is_today": not date_filter}
	for row in rows:
		side = "sales" if row.document_kind in SALES_KINDS else "returns"
		out[f"{side}_count"] += row.n
		out[f"{side}_value"] = flt(out[f"{side}_value"] + flt(row.value), 2)
	# The latest document's reading, through the date index (the greatest reading of all of them read the whole
	# table: 8.5 s on the live site).
	last = frappe.get_list("Library Sales Document", filters=one, fields=["last_synced_at"], order_by="reg_date desc", limit=1)
	out["last_synced_at"] = last[0].last_synced_at if last else None
	out["currency"] = frappe.db.get_default("currency") or "EGP"
	return out
