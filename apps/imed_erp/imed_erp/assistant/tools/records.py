# List and count records of the DocTypes the registry found for the asking user, through frappe.get_list, which
# applies that user's permissions (roles, user permissions, if-owner): the assistant never knows more than its user.

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.tools.base import FILTERS_SCHEMA, MAX_ROWS_TO_MODEL, compact_rows, parse_filters

# Never sent to a model, whatever the user's level: secrets and the raw payloads mirrored from other systems.
NEVER_READ = ("Password", "Attach", "Attach Image", "Signature", "Code", "JSON")


def cost_center_field(doctype: str) -> str | None:
	meta = frappe.get_meta(doctype)
	for df in meta.fields:
		if df.fieldtype == "Link" and df.options == "Cost Center":
			return df.fieldname
	return None


def scoped(doctype: str, filters: list | dict, context: RequestContext) -> list | dict:
	"""A DocType with a company field is read for the request's company only, whatever the user's wider rights. For
	a user who may not read every company, a DocType with no company field but a cost center is read for that
	company's cost centers only (a booking, a counter reading)."""
	if not context.company:
		raise frappe.PermissionError(_("No company for this request."))
	extra = None
	if frappe.get_meta(doctype).has_field("company"):
		extra = ["company", "=", context.company]
	elif not context.all_companies and (field := cost_center_field(doctype)):
		centers = frappe.get_all("Cost Center", filters={"company": context.company}, pluck="name") or ["\0"]
		extra = [field, "in", centers]
	if extra is None:
		return filters
	if isinstance(filters, dict):
		return {**filters, extra[0]: (extra[1], extra[2])}
	return [*filters, extra]


def readable_fields(doctype: str) -> set[str]:
	"""The fields of `doctype` the asking user may read: at a permission level the user has, not a secret type."""
	meta = frappe.get_meta(doctype)
	levels = set(meta.get_permlevel_access("read"))
	return {"name", "owner", "creation", "modified", "docstatus"} | {
		df.fieldname for df in meta.fields if df.fieldtype not in NEVER_READ and (df.permlevel or 0) in levels and df.fieldname
	}


class _RecordsTool:
	def __init__(self, doctypes: list[str]):
		self.doctypes = doctypes

	def check(self, doctype: str) -> None:
		if doctype not in self.doctypes:
			raise frappe.ValidationError(_("The assistant may not read {0} for this user.").format(doctype))

	@staticmethod
	def check_filters(filters: list | dict, allowed: set[str]) -> None:
		"""A filter on a field the user may not read would leak it through the rows or the count it selects."""
		names = filters.keys() if isinstance(filters, dict) else [f[0] for f in filters]
		hidden = [f for f in names if f not in allowed]
		if hidden:
			raise frappe.PermissionError(_("Not allowed to filter on {0}.").format(", ".join(hidden)))


class ListRecordsTool(_RecordsTool):
	name = "list_records"

	def spec(self, context: RequestContext) -> dict[str, Any]:
		return {
			"name": self.name,
			"description": "List records of a DocType with filters, as the asking user may see them. DocTypes: " + ", ".join(self.doctypes) + ". Use count_records when only the number matters.",
			"input_schema": {
				"type": "object",
				"properties": {
					"doctype": {"type": "string", "enum": self.doctypes},
					"filters": FILTERS_SCHEMA,
					"fields": {"type": "array", "items": {"type": "string"}, "description": "field names to return; [] for the name and the title"},
					"order_by": {"type": "string", "description": "e.g. 'booking_date desc'; '' for the default"},
					"limit": {"type": "integer", "minimum": 1, "maximum": MAX_ROWS_TO_MODEL},
				},
				"required": ["doctype", "filters", "fields", "order_by", "limit"],
				"additionalProperties": False,
			},
		}

	def run(self, arguments: dict, context: RequestContext) -> dict:
		doctype = arguments.get("doctype")
		self.check(doctype)
		allowed = readable_fields(doctype)
		filters = parse_filters(arguments.get("filters"))
		self.check_filters(filters, allowed)
		fields = [f for f in (arguments.get("fields") or []) if f in allowed]
		if not fields:
			title = frappe.get_meta(doctype).title_field
			fields = ["name"] + ([title] if title in allowed else [])
		rows = frappe.get_list(
			doctype,
			filters=scoped(doctype, filters, context),
			fields=fields,
			order_by=arguments.get("order_by") or None,
			limit=min(cint(arguments.get("limit")) or 50, MAX_ROWS_TO_MODEL),
		)
		return compact_rows({"rows": rows, "count": len(rows)})


class CountRecordsTool(_RecordsTool):
	name = "count_records"

	def spec(self, context: RequestContext) -> dict[str, Any]:
		return {
			"name": self.name,
			"description": "Count the records of a DocType matching filters (same DocTypes and filters as list_records).",
			"input_schema": {
				"type": "object",
				"properties": {"doctype": {"type": "string", "enum": self.doctypes}, "filters": FILTERS_SCHEMA},
				"required": ["doctype", "filters"],
				"additionalProperties": False,
			},
		}

	def run(self, arguments: dict, context: RequestContext) -> dict:
		doctype = arguments.get("doctype")
		self.check(doctype)
		if not frappe.has_permission(doctype, "read"):
			raise frappe.PermissionError(_("Not allowed to read {0}.").format(doctype))
		filters = parse_filters(arguments.get("filters"))
		self.check_filters(filters, readable_fields(doctype))
		# get_list with a count keeps the user's permission conditions, which db.count would skip.
		rows = frappe.get_list(doctype, filters=scoped(doctype, filters, context), fields=[{"COUNT": "*", "as": "n"}])
		return {"count": cint(rows[0].n) if rows else 0}
