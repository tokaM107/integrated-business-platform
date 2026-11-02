# A navigation adapter, not a domain model: the DocTypes, Reports and Workspaces an app's Workspace Sidebar gives its
# users. An integration may use it to say "the assistant may read what the user can already open from the sidebar";
# each item is still checked against the user's own permission (the DocType's read, the Report's roles), so the
# assistant never reaches more than the screens would show the same user.

from __future__ import annotations

from dataclasses import dataclass, field

import frappe


@dataclass
class SidebarSurface:
	doctypes: list[str] = field(default_factory=list)
	reports: list[str] = field(default_factory=list)
	workspaces: list[str] = field(default_factory=list)


def surface(app: str) -> SidebarSurface:
	out = SidebarSurface()
	for sidebar in frappe.get_all("Workspace Sidebar", filters={"app": app}, pluck="name"):
		for item in frappe.get_cached_doc("Workspace Sidebar", sidebar).items:
			if item.type != "Link" or not item.link_to:
				continue
			target = {"DocType": out.doctypes, "Report": out.reports, "Workspace": out.workspaces}.get(item.link_type)
			if target is not None and item.link_to not in target:
				target.append(item.link_to)
	return out


def readable_doctypes(names: list[str]) -> list[str]:
	return [dt for dt in names if frappe.db.exists("DocType", dt) and frappe.has_permission(dt, "read")]


def runnable_reports(names: list[str], area: str) -> list[dict[str, str]]:
	out = []
	for name in names:
		if not frappe.db.exists("Report", name):
			continue
		report = frappe.get_cached_doc("Report", name)
		if not report.disabled and report.is_permitted():
			out.append({"name": name, "ref_doctype": report.ref_doctype or "", "area": area})
	return out
