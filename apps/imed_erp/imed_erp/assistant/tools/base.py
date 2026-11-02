# What every read tool shares: a guarded run (the read as the asking user, in its own savepoint, rolled back
# after; a failure returned as text the model can read, never hidden) and the compaction of a result to what an
# answer needs (results go to a model that is paid by the token).

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from imed_erp.assistant.core.context import RequestContext

MAX_ROWS_TO_MODEL = 60
MAX_CHARS_TO_MODEL = 12_000
SAVEPOINT = "assistant_tool"

# Filters as the model writes them: conditions, each a field, an operator and a text value (a JSON list for in /
# not in / between). One schema for every tool that filters.
FILTERS_SCHEMA = {
	"type": "array",
	"items": {
		"type": "object",
		"properties": {
			"field": {"type": "string"},
			"operator": {"type": "string", "enum": ["=", "!=", ">", "<", ">=", "<=", "like", "not like", "in", "not in", "between", "is"]},
			"value": {"type": "string", "description": "the value; a JSON list for in/not in/between; 'set' or 'not set' for is"},
		},
		"required": ["field", "operator", "value"],
		"additionalProperties": False,
	},
}


def parse_filters(filters: Any) -> list | dict:
	"""The model's conditions as Frappe filters: [[field, operator, value], ...]."""
	if isinstance(filters, str):
		filters = json.loads(filters or "[]")
	if isinstance(filters, dict):
		return filters
	out = []
	for cond in filters or []:
		field, operator, value = cond["field"], cond["operator"], cond.get("value", "")
		if operator in ("in", "not in", "between") or (isinstance(value, str) and value[:1] in "[{"):
			try:
				value = json.loads(value)
			except (TypeError, ValueError):
				pass
		elif isinstance(value, str):
			stripped = value.lstrip("-")
			if stripped.isdigit():
				value = int(value)
			elif stripped.replace(".", "", 1).isdigit():
				value = float(value)
		out.append([field, operator, value])
	return out


def compact_rows(data: dict) -> dict:
	rows = data.get("rows") or []
	return {**data, "rows": rows[:MAX_ROWS_TO_MODEL], "rows_shown": min(len(rows), MAX_ROWS_TO_MODEL), "rows_total": data.get("rows_total", len(rows))}


def to_text(result: Any) -> str:
	text = json.dumps(result, ensure_ascii=False, default=str)
	return text if len(text) <= MAX_CHARS_TO_MODEL else text[:MAX_CHARS_TO_MODEL] + " ...(cut: ask for a narrower filter)"


def guarded(run, arguments: dict, context: RequestContext) -> tuple[str, bool]:
	"""(text, is_error): the tool's result as text; read-only by contract, whatever happens inside."""
	frappe.db.savepoint(SAVEPOINT)
	try:
		return to_text(run(arguments, context)), False
	except frappe.PermissionError as e:
		frappe.clear_messages()
		return to_text({"error": _("Not allowed for this user: {0}").format(str(getattr(e, "message", None) or e)[:300])}), True
	except Exception as e:
		frappe.clear_messages()
		return to_text({"error": str(getattr(e, "message", None) or e)[:500]}), True
	finally:
		frappe.db.rollback(save_point=SAVEPOINT)
