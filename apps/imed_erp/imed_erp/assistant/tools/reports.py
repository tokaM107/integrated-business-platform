# Run one of the ERP's reports. Which ones: the reports the registry found for the asking user (the sidebar's, each
# checked with the Report's own permission). The report runs through Frappe's query_report.run, as the user.

from __future__ import annotations

import os
import re
from typing import Any

import frappe
from frappe import _

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.tools.base import compact_rows


# A company filter in the report's own filters, or ERPNext's shared financial-statement filters (company, required).
COMPANY_FILTER = re.compile(r"""fieldname\s*:\s*["']company["']|\$\.extend\(\s*\{\s*\}\s*,\s*erpnext\.financial_statements\s*\)""")


CODE_READS_COMPANY = re.compile(r"""filters\.company|filters\.get\(\s*["']company["']|filters\[\s*["']company["']|["']company["']\s*,""")


def takes_company(report: str) -> bool:
	"""Whether the report declares a company filter (its standard .js filters, or the Report's own filter rows).
	Such a report is run with the request's company forced; any other report reads across companies."""
	doc = frappe.get_cached_doc("Report", report)
	if doc.report_type == "Report Builder" and any(row.fieldname == "company" for row in doc.get("filters") or []):
		return True  # a Report Builder report filters through get_list: a company filter there is always applied
	if doc.is_standard != "Yes" or not doc.module:
		return False
	app = frappe.local.module_app.get(frappe.scrub(doc.module))
	if not app:
		return False
	folder = frappe.get_app_path(app, frappe.scrub(doc.module), "report", frappe.scrub(doc.name))
	script, code = (os.path.join(folder, frappe.scrub(doc.name) + ext) for ext in (".js", ".py"))
	if not (os.path.exists(script) and os.path.exists(code)):
		return False
	with open(script, encoding="utf-8") as f:
		declared = bool(COMPANY_FILTER.search(f.read()))
	with open(code, encoding="utf-8") as f:
		# Fail closed (review of 2 Nov 2026): a filter the screen declares but the code never reads would be forced
		# for nothing. The code must name it; tests/test_assistant_isolation.py runs each such report for one
		# company with another company's rows present.
		read = bool(CODE_READS_COMPANY.search(f.read()))
	return declared and read


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
		filters = dict(arguments.get("filters") or {})
		if takes_company(report):
			# The request's company, whatever the model or a retrieved record asked for.
			filters["company"] = context.company
		elif not context.all_companies:
			raise frappe.PermissionError(
				_("{0} is not limited to one company, and you may not read every company: open it in the ERP.").format(report)
			)
		from frappe.desk.query_report import run

		result = run(report, filters=filters)
		columns = [c.get("fieldname") or c.get("label") if isinstance(c, dict) else str(c) for c in result.get("columns") or []]
		rows = [row if isinstance(row, dict) else dict(zip(columns, row)) for row in result.get("result") or []]
		return compact_rows({"columns": columns, "rows": rows})
