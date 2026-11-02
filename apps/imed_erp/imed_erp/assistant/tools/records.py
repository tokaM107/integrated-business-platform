# List and count records of the DocTypes the registry found for the asking user, through frappe.get_list, which
# applies that user's permissions (roles, user permissions, if-owner): the assistant never knows more than its user.

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.tools.base import FILTERS_SCHEMA, MAX_ROWS_TO_MODEL, compact_rows, parse_filters

MAX_LIMIT = 200


class _RecordsTool:
	def __init__(self, doctypes: list[str]):
		self.doctypes = doctypes

	def check(self, doctype: str) -> None:
		if doctype not in self.doctypes:
			raise frappe.ValidationError(_("The assistant may not read {0} for this user.").format(doctype))


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
					"limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
				},
				"required": ["doctype", "filters", "fields", "order_by", "limit"],
				"additionalProperties": False,
			},
		}

	def run(self, arguments: dict, context: RequestContext) -> dict:
		doctype = arguments.get("doctype")
		self.check(doctype)
		meta = frappe.get_meta(doctype)
		fields = [f for f in (arguments.get("fields") or []) if f == "name" or meta.get_field(f) or f in ("owner", "creation", "modified", "docstatus")]
		if not fields:
			fields = ["name"] + ([meta.title_field] if meta.title_field else [])
		rows = frappe.get_list(
			doctype,
			filters=parse_filters(arguments.get("filters")),
			fields=fields,
			order_by=arguments.get("order_by") or None,
			limit_page_length=min(cint(arguments.get("limit")) or 50, MAX_ROWS_TO_MODEL),
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
		# get_list with a count keeps the user's permission conditions, which db.count would skip.
		rows = frappe.get_list(doctype, filters=parse_filters(arguments.get("filters")), fields=["count(name) as n"])
		return {"count": cint(rows[0].n) if rows else 0}
