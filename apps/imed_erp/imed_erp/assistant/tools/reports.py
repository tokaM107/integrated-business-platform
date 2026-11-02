# Run one of the ERP's reports. Which ones: the reports the registry found for the asking user (the sidebar's, each
# checked with the Report's own permission). The report runs through Frappe's query_report.run, as the user.

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.tools.base import compact_rows


class RunReportTool:
	name = "run_report"

	def __init__(self, reports: list[dict[str, str]]):
		self.reports = reports  # [{name, ref_doctype, area}]

	def spec(self, context: RequestContext) -> dict[str, Any]:
		listing = "; ".join(f"'{r['name']}' (on {r['ref_doctype']}, {r['area']})" for r in self.reports)
		return {
			"name": self.name,
			"description": "Run one of the ERP's reports and get its rows. Reports: " + listing + ". Pass the filters the report needs (dates as YYYY-MM-DD; a report that needs a filter says so in its error).",
			"input_schema": {
				"type": "object",
				"properties": {
					"report": {"type": "string", "enum": [r["name"] for r in self.reports]},
					"filters": {"type": "object", "additionalProperties": True, "description": 'the report\'s filters, e.g. {"from_date": "2026-11-01", "to_date": "2026-11-30"}'},
				},
				"required": ["report", "filters"],
				"additionalProperties": False,
			},
		}

	def run(self, arguments: dict, context: RequestContext) -> dict:
		report = arguments.get("report")
		if report not in {r["name"] for r in self.reports}:
			raise frappe.ValidationError(_("Report {0} is not one the assistant may run for this user.").format(report))
		if frappe.get_cached_value("Report", report, "prepared_report"):
			# A heavy report runs in the background for the desk; the assistant does not force it to run inline.
			raise frappe.ValidationError(_("{0} runs in the background: open it in the ERP.").format(report))
		from frappe.desk.query_report import run

		result = run(report, filters=arguments.get("filters") or {})
		columns = [c.get("fieldname") or c.get("label") if isinstance(c, dict) else str(c) for c in result.get("columns") or []]
		rows = [row if isinstance(row, dict) else dict(zip(columns, row)) for row in result.get("result") or []]
		return compact_rows({"columns": columns, "rows": rows})
