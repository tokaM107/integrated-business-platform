# What every read tool shares: a guarded run and the compaction of a result to what an answer needs.
#
# The guard: the read runs as the asking user, inside its own savepoint, rolled back after; a commit attempted
# inside it fails (a tool is a read, whatever code it calls); a refusal or a validation error is returned as text
# the model can read; an unexpected error is logged before it is returned, never swallowed.

from __future__ import annotations

import json
from contextlib import contextmanager
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


class WriteAttempted(Exception):
	"""A tool tried to commit: refused, the tool's work is rolled back."""


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


def error_text(message: str) -> str:
	return to_text({"error": message})


@contextmanager
def no_commit():
	"""Inside, frappe.db.commit raises: a read tool never persists anything, whatever code it calls."""
	original = frappe.db.commit

	def refuse(*args, **kwargs):
		raise WriteAttempted(_("A read tried to save to the database; refused."))

	frappe.db.commit = refuse
	try:
		yield
	finally:
		frappe.db.commit = original


def guarded(run, arguments: dict, context: RequestContext) -> tuple[str, bool]:
	"""(text, is_error): the tool's result as text."""
	frappe.db.savepoint(SAVEPOINT)
	try:
		with no_commit():
			return to_text(run(arguments, context)), False
	except frappe.PermissionError as e:
		return error_text(_("Not allowed for this user: {0}").format(str(getattr(e, "message", None) or e)[:300])), True
	except (frappe.ValidationError, WriteAttempted) as e:
		return error_text(str(getattr(e, "message", None) or e)[:500]), True
	except Exception as e:
		frappe.log_error(title="Assistant tool failed", message=frappe.get_traceback())
		return error_text(_("The read failed: {0}").format(str(e)[:300])), True
	finally:
		frappe.clear_messages()
		frappe.db.rollback(save_point=SAVEPOINT)
