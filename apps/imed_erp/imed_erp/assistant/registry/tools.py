# The tools of one request: the common reads, scoped to what the integrations expose to the asking user, plus the
# integrations' own tools. Built per request (what a user may read changes with permissions), kept nowhere after.

from __future__ import annotations

from typing import Any

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.exceptions import ToolConflict
from imed_erp.assistant.core.interfaces import BusinessIntegration, Tool
from imed_erp.assistant.tools.base import error_text, guarded
from imed_erp.assistant.tools.dashboard import DashboardTool
from imed_erp.assistant.tools.ledger import AccountBalanceTool
from imed_erp.assistant.tools.records import CountRecordsTool, ListRecordsTool
from imed_erp.assistant.tools.reports import RunReportTool


def _merge(target: list, items) -> None:
	for item in items:
		if item not in target:
			target.append(item)


class ToolRegistry:
	def __init__(self, integrations: list[BusinessIntegration], context: RequestContext):
		self.integrations = integrations
		doctypes: list[str] = []
		workspaces: list[str] = []
		reports: dict[str, dict] = {}
		own: list[Tool] = []
		for integration in integrations:
			_merge(doctypes, integration.doctypes(context))
			_merge(workspaces, integration.workspaces(context))
			for report in integration.reports(context):
				reports.setdefault(report["name"], report)
			own.extend(integration.tools(context))

		common: list[Tool] = []
		dashboard = DashboardTool(workspaces)
		# Only the workspaces this user may open, and only for a user who may read every company: the cards are not
		# limited to one company.
		if dashboard.workspaces and context.all_companies:
			common.append(dashboard)
		if reports:
			common.append(RunReportTool(list(reports.values())))
		if doctypes:
			common += [ListRecordsTool(doctypes), CountRecordsTool(doctypes)]
		common.append(AccountBalanceTool())

		self._tools: dict[str, Tool] = {}
		for tool in common + own:
			if tool.name in self._tools:
				raise ToolConflict(f"two tools are named {tool.name}")
			self._tools[tool.name] = tool
		self._labels = [label for i in integrations for label in i.businesses(context)]
		self._notes = "\n".join(n for n in (i.prompt_notes(context) for i in integrations) if n)

	def names(self) -> list[str]:
		return list(self._tools)

	def catalogue(self, context: RequestContext) -> str:
		"""The tools, compact, for the planner."""
		lines = []
		for tool in self._tools.values():
			spec = tool.spec(context)
			args = ", ".join(spec["input_schema"].get("properties", {}).keys()) or "no arguments"
			lines.append(f"- {spec['name']}({args}): {spec['description']}")
		lines.append('Filters: [{"field": ..., "operator": "=|!=|>|<|>=|<=|like|in|between|is", "value": "text; a JSON list for in/between"}]')
		return "\n".join(lines)

	def business_labels(self) -> list[str]:
		return self._labels

	def prompt_notes(self) -> str:
		return self._notes

	def run(self, name: str, arguments: dict[str, Any], context: RequestContext) -> tuple[str, bool]:
		tool = self._tools.get(name)
		if tool is None:
			return error_text(f"Unknown tool {name}."), True
		return guarded(tool.run, arguments, context)
