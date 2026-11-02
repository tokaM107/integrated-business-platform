# A business area as the system itself describes it: a section of the app's Workspace Sidebar (workspace_sidebar/
# *.json, the same record the users' sidebar is drawn from), with the DocTypes and Reports linked under it. Nothing
# is listed here by hand: add a section or a link to the sidebar and the assistant reads it on the next request,
# filtered to what the asking user may read (the DocType's read permission; the Report's own roles).

from __future__ import annotations

import frappe

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.interfaces import Tool


class SidebarBusiness:
	def __init__(self, key: str, label: str, doctype_links: list[str], report_links: list[str], workspaces: list[str]):
		self.key = key
		self.label = label
		self._doctypes = doctype_links
		self._reports = report_links
		self.workspaces = workspaces

	def doctypes(self, context: RequestContext) -> list[str]:
		return [dt for dt in self._doctypes if frappe.db.exists("DocType", dt) and frappe.has_permission(dt, "read")]

	def reports(self, context: RequestContext) -> list[dict[str, str]]:
		out = []
		for name in self._reports:
			if not frappe.db.exists("Report", name):
				continue
			report = frappe.get_cached_doc("Report", name)
			if report.disabled or not report.is_permitted():
				continue
			out.append({"name": name, "ref_doctype": report.ref_doctype or "", "area": self.label})
		return out

	def tools(self, context: RequestContext) -> list[Tool]:
		return []  # the common tools (records, reports, dashboard) already cover a sidebar section


def from_sidebars(app: str) -> list[SidebarBusiness]:
	"""One business per sidebar section of `app`'s Workspace Sidebars; the workspace links before the first section
	belong to every business (the dashboard)."""
	businesses: list[SidebarBusiness] = []
	for sidebar in frappe.get_all("Workspace Sidebar", filters={"app": app}, pluck="name"):
		doc = frappe.get_cached_doc("Workspace Sidebar", sidebar)
		workspaces = [i.link_to for i in doc.items if i.type == "Link" and i.link_type == "Workspace" and i.link_to]
		current = None
		for item in doc.items:
			if item.type == "Section Break":
				current = SidebarBusiness(frappe.scrub(item.label), item.label, [], [], workspaces)
				businesses.append(current)
			elif current and item.type == "Link" and item.link_to:
				if item.link_type == "DocType" and item.link_to not in current._doctypes:
					current._doctypes.append(item.link_to)
				elif item.link_type == "Report" and item.link_to not in current._reports:
					current._reports.append(item.link_to)
	return businesses
