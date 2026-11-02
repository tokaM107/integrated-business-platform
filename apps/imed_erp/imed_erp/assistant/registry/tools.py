# The tools of one request: the common reads (dashboard, reports, records, ledger), their scope set from what the
# businesses expose to the asking user, plus any tool a business adds. Built per request (what a user may read
# changes with permissions), kept nowhere between requests.

from __future__ import annotations

from typing import Any

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.exceptions import ToolNotFound
from imed_erp.assistant.core.interfaces import BusinessIntegration, Tool
from imed_erp.assistant.tools.base import guarded
from imed_erp.assistant.tools.dashboard import DashboardTool
from imed_erp.assistant.tools.ledger import AccountBalanceTool
from imed_erp.assistant.tools.records import CountRecordsTool, ListRecordsTool
from imed_erp.assistant.tools.reports import RunReportTool


class ToolRegistry:
	def __init__(self, businesses: list[BusinessIntegration], context: RequestContext):
		self.businesses = businesses
		doctypes, reports, workspaces, tools = [], [], [], []
		for business in businesses:
			for dt in business.doctypes(context):
				if dt not in doctypes:
					doctypes.append(dt)
			for report in business.reports(context):
				if report["name"] not in {r["name"] for r in reports}:
					reports.append(report)
			for ws in getattr(business, "workspaces", []) or []:
				if ws not in workspaces:
					workspaces.append(ws)
			tools.extend(business.tools(context))
		common: list[Tool] = [DashboardTool(workspaces)]
		if reports:
			common.append(RunReportTool(reports))
		if doctypes:
			common += [ListRecordsTool(doctypes), CountRecordsTool(doctypes)]
		common.append(AccountBalanceTool())
		self._tools: dict[str, Tool] = {t.name: t for t in common + tools}

	def names(self, context: RequestContext) -> list[str]:
		return list(self._tools)

	def specs(self, context: RequestContext) -> list[dict[str, Any]]:
		return [t.spec(context) for t in self._tools.values()]

	def catalogue(self, context: RequestContext) -> str:
		"""The tools, compact, for the planner."""
		lines = []
		for spec in self.specs(context):
			args = ", ".join(spec["input_schema"].get("properties", {}).keys()) or "no arguments"
			lines.append(f"- {spec['name']}({args}): {spec['description']}")
		lines.append('Filters: [{"field": ..., "operator": "=|!=|>|<|>=|<=|like|in|between|is", "value": "text; a JSON list for in/between"}]')
		return "\n".join(lines)

	def business_labels(self) -> list[str]:
		return [b.label for b in self.businesses]

	def run(self, name: str, arguments: dict, context: RequestContext) -> tuple[str, bool]:
		tool = self._tools.get(name)
		if not tool:
			return guarded(lambda a, c: (_ for _ in ()).throw(ToolNotFound(f"Unknown tool {name}.")), arguments, context)
		return guarded(tool.run, arguments, context)
