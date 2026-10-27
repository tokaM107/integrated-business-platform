# Pure mapping from a connector document (library_sync/contract.py) to the fields of a Library Sales Document.
# No frappe, no database: tested on mock rows (test_library_sync.py). Nothing here invents a value: a missing
# required key raises MappingError with the key's name, an unknown operation code gives kind "Other" and a note.
import hashlib
import json
from datetime import date, datetime

from imed_erp.imederp.library_sync import contract as c


class MappingError(Exception):
	pass


def import_key(library, family, external_id):
	return f"{c.SOURCE}:{library}:{family}:{external_id}"


def payload_hash(document):
	"""Stable over key order; the connector's own bookkeeping keys (starting with _) are left out."""
	clean = {k: v for k, v in document.items() if not str(k).startswith("_")}
	return hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def num(value):
	if value in (None, ""):
		return 0.0
	try:
		return float(value)
	except (TypeError, ValueError) as e:
		raise MappingError(f"not a number: {value!r}") from e


def when(value):
	"""SQL Server datetime as the connector sends it ('2026-10-24 18:05:00' or ISO), library local time (Cairo)."""
	if isinstance(value, datetime):
		return value
	if isinstance(value, date):
		return datetime(value.year, value.month, value.day)
	text = str(value or "").strip().replace("T", " ")
	for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
		try:
			return datetime.strptime(text[: 26 if fmt.endswith("%f") else len(text)], fmt)
		except ValueError:
			continue
	raise MappingError(f"not a date: {value!r}")


def kind_of(family, document, operation_map):
	spec = c.FAMILIES[family]
	if "kind" in spec:
		return spec["kind"], None
	code = str(document.get(spec["operation_code"], "")).strip()
	kind = operation_map.get(code)
	if kind in c.ALL_KINDS:
		return kind, None
	return "Other", f"operation code {code!r} ({document.get(spec['operation_name']) or '?'}) is not in the operation map"


def map_document(family, document, settings):
	"""settings: branch_map, operation_map, issued_status_codes, cancelled_status_codes (from the connector's
	config, sent with every batch). Returns (fields, notes): fields for Library Sales Document (lines included as
	dicts), notes = things to look at (not errors)."""
	if family not in c.FAMILIES:
		raise MappingError(f"unknown document family {family!r}")
	spec = c.FAMILIES[family]
	notes = []
	for req in c.REQUIRED:
		if document.get(spec[req]) in (None, ""):
			raise MappingError(f"missing {spec[req]}")
	kind, note = kind_of(family, document, settings.get("operation_map") or {})
	if note:
		notes.append(note)
	status_code = str(document.get(spec["status_code"])).strip()
	issued = {str(x) for x in settings.get("issued_status_codes") or []}
	cancelled = {str(x) for x in settings.get("cancelled_status_codes") or []}
	if not issued:
		notes.append("no issued status code is configured: every document is kept as not final")
	branch_code = str(document.get(spec["branch_code"])).strip()
	cost_center = (settings.get("branch_map") or {}).get(branch_code)
	if not cost_center:
		notes.append(f"branch code {branch_code!r} is not mapped to a cost center")
	fields = {
		"source_system": c.SOURCE,
		"family": family,
		"external_id": str(document[spec["id"]]),
		"library": settings["library"],
		"import_key": import_key(settings["library"], family, document[spec["id"]]),
		"document_kind": kind,
		"operation_code": str(document.get(spec["operation_code"]) or ""),
		"operation_name": str(document.get(spec["operation_name"]) or "") if spec["operation_name"] else "",
		"number": str(document[spec["number"]]),
		"reg_date": when(document[spec["date"]]),
		"status_code": status_code,
		"status_name": str(document.get(spec["status_name"]) or ""),
		"is_final": 1 if status_code in issued else 0,
		"is_cancelled": 1 if status_code in cancelled else 0,
		"branch_code": branch_code,
		"branch_name": str(document.get(spec["branch_name"]) or ""),
		"cost_center": cost_center,
		"payload_hash": payload_hash(document),
		"lines": [],
	}
	head_map = c.STOCK_HEAD if family == "stock" else c.CASH_HEAD["Receipt" if family == "cash_receipt" else "Payment"]
	for key, field in head_map.items():
		if key in document and document[key] is not None:
			fields[field] = num(document[key]) if field.endswith(("_value", "_percent")) else str(document[key])
	line_map = c.STOCK_LINE if family == "stock" else c.CASH_LINE["Receipt" if family == "cash_receipt" else "Payment"]
	numeric = {"qty_out", "qty_in", "qty_return", "unit_factor", "price_small", "price_small_before_discount", "price_big", "price_big_before_discount", "discount_percent", "discount_value", "value_out", "value_in", "vat_value", "cost_price", "cost_avg", "debit", "credit"}
	for raw in document.get("lines") or []:
		line = {}
		for key, field in line_map.items():
			if key in raw and raw[key] is not None:
				line[field] = num(raw[key]) if field in numeric else (1 if raw[key] in (1, True, "1", "True") else 0) if field == "is_small_unit" else str(raw[key])
		if "external_id" not in line:
			raise MappingError(f"a line of document {fields['external_id']} has no {spec['line_id']}")
		if family == "stock":
			line["qty"] = line.get("qty_out") or line.get("qty_in") or line.get("qty_return") or 0.0
			line["line_total"] = line.get("value_out") if kind in c.SALES_KINDS + ("Adjustment Out", "Transfer", "Purchase Return") else line.get("value_in", line.get("value_out", 0.0))
			line["price"] = line.get("price_big") if line.get("is_small_unit") == 0 and line.get("price_big") else line.get("price_small", 0.0)
		else:
			line["qty"] = 0.0
			line["line_total"] = line.get("debit", 0.0) or line.get("credit", 0.0)
			line["price"] = 0.0
		fields["lines"].append(line)
	if family == "stock":
		fields["total"] = round(sum(l.get("line_total") or 0.0 for l in fields["lines"]), 2)
		fields["qty_total"] = round(sum(l.get("qty") or 0.0 for l in fields["lines"]), 3)
		if kind in c.SALES_KINDS + c.RETURN_KINDS + ("Purchase", "Purchase Return") and not fields["lines"]:
			notes.append("no lines came with the document")
	else:
		fields["total"] = round(sum(l.get("debit") or 0.0 for l in fields["lines"]) or sum(l.get("credit") or 0.0 for l in fields["lines"]), 2)
		fields["qty_total"] = 0.0
	fields["money_direction"] = "In" if kind in c.MONEY_IN_KINDS or kind == "Cash Receipt" else "Out" if kind in c.MONEY_OUT_KINDS or kind == "Cash Payment" else "None"
	return fields, notes
