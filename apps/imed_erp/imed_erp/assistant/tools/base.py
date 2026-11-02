# What every read tool shares: a guarded run and the compaction of a result to what an answer needs.
#
# The guard: the read runs as the asking user, inside its own savepoint, rolled back after; a commit attempted
# or any other write inside it is refused at the connection (a tool is a read, whatever code it calls); a refusal or a validation error is returned as text
# the model can read; an unexpected error is logged before it is returned, never swallowed.

from __future__ import annotations

import json
import re
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
	"""A tool sent a statement that writes: refused, the tool's work is rolled back."""


# The statements a read may send. Anything else (INSERT, UPDATE, DELETE, REPLACE, CREATE, ALTER, DROP, TRUNCATE,
# COMMIT, LOCK, CALL, ...) is refused before it reaches the database.
READ_STATEMENTS = ("select", "with", "show", "explain", "describe", "desc", "savepoint", "release", "rollback to")
_LEADING_COMMENT = re.compile(r"^\s*(/\*.*?\*/\s*)*", re.S)


def is_read(query) -> bool:
	text = _LEADING_COMMENT.sub("", str(query)).lstrip().lower()
	return text.startswith(READ_STATEMENTS) or text.startswith("set @")


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
def read_only():
	"""Inside, the database connection accepts reads only. Every query of Frappe, raw frappe.db.sql, the query
	builder, set_value, insert and commit alike, passes through Database.execute_query: a write is refused there,
	before it reaches the database."""
	db = frappe.local.db
	original = db.execute_query

	def guard(query, values=None):
		if not is_read(query):
			raise WriteAttempted(_("A read tried to write to the database; refused."))
		return original(query, values)

	def no_job(*args, **kwargs):
		# A job queued now would run later, outside this guard and as whoever runs the worker (review of 2 Nov 2026).
		raise WriteAttempted(_("A read tried to queue a background job; refused."))

	db.execute_query = guard
	saved = frappe.enqueue, frappe.enqueue_doc
	frappe.enqueue = frappe.enqueue_doc = no_job
	try:
		yield
	finally:
		db.execute_query = original
		frappe.enqueue, frappe.enqueue_doc = saved


def guarded(run, arguments: dict, context: RequestContext) -> tuple[str, bool]:
	"""(text, is_error): the tool's result as text."""
	frappe.db.savepoint(SAVEPOINT)
	try:
		with read_only():
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
