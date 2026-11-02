# The IMED group's integration (this app's own, registered in hooks.py like any other app's would be).
#
#   business units  the Cost Center tree: a business is a cost center (business_figures.py, setup_core.py), so the
#                   units are the company's leaf cost centers the asking user may see (user permissions apply);
#   surface         what this app's sidebar gives its users, as the user may read it (businesses/sidebar.py);
#   own tools       the owner's live band (imederp.owner_yesterday), refused by that service to anyone else;
#   rules           the meanings that are this group's, not the assistant's: XStudio's "due", "held" bookings.

from __future__ import annotations

from typing import Any

import frappe

from imed_erp.assistant.businesses.sidebar import readable_doctypes, runnable_reports, surface
from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.interfaces import BusinessIntegration, Tool

APP = "imed_erp"

NOTES = """- Revenue is invoiced revenue from the ledger; cash is what the ledger says is in a box; a payment is not revenue.
- An external booking system's "due" is what it bills less what it says was paid; it is shown, never posted to the ledger.
- A booking counted "held" is neither cancelled nor a no-show; hours on a prepaid package were paid when the package was bought."""


class OwnerBandTool:
	name = "owner_band_today"

	def spec(self, context: RequestContext) -> dict[str, Any]:
		return {
			"name": self.name,
			"description": "Today's live band of the owner's dashboard: revenue and expenses by business unit, today's bookings, the halls, the app's fees, the printing counters and the integrations' health. The owner's alone.",
			"input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
		}

	def run(self, arguments: dict, context: RequestContext) -> dict:
		if not context.all_companies:
			raise frappe.PermissionError("The owner's band is the group's, not limited to one company.")
		from imed_erp.imederp import owner_yesterday

		band = owner_yesterday.get_yesterday()  # raises PermissionError for anyone but the owner
		money = band.get("money") or {}
		out = {
			"day": band.get("day"),
			"money_today": {
				"rows": [{k: r.get(k) for k in ("business", "revenue", "expenses", "net", "external", "bookings", "paid", "due", "package_bookings")} for r in money.get("rows") or []],
				"total": money.get("total"),
				"ledger_entries_today": money.get("ledger_entries"),
			},
			"bookings_today": band.get("bookings"),
			"halls": band.get("halls"),
			"app_fees": band.get("app"),
			"printing_warnings": (band.get("printing") or {}).get("warnings"),
			"systems": [{"name": s.get("name"), "state": s.get("state"), "detail": (s.get("detail") or "")[:160]} for s in band.get("systems") or []],
		}
		if band.get("ledger_entries_all_time") == 0:
			out["note"] = "no accounting record exists yet: the ledger's zeros are missing data, not a result"
		return out


class ImedIntegration:
	key = "imed"

	def __init__(self):
		self.label = frappe.get_hooks("app_title", app_name=APP)[0] if frappe.get_hooks("app_title", app_name=APP) else APP
		self._surface = surface(APP)

	def businesses(self, context: RequestContext) -> list[str]:
		try:
			return frappe.get_list("Cost Center", filters={"company": context.company, "is_group": 0, "disabled": 0}, pluck="cost_center_name", order_by="lft")
		except frappe.PermissionError:
			frappe.clear_messages()
			return []

	def doctypes(self, context: RequestContext) -> list[str]:
		return readable_doctypes(self._surface.doctypes)

	def reports(self, context: RequestContext) -> list[dict[str, str]]:
		return runnable_reports(self._surface.reports, self.label)

	def workspaces(self, context: RequestContext) -> list[str]:
		return list(self._surface.workspaces)

	def tools(self, context: RequestContext) -> list[Tool]:
		return [OwnerBandTool()] if context.all_companies else []

	def prompt_notes(self, context: RequestContext) -> str:
		return NOTES


def integrations(context: RequestContext) -> list[BusinessIntegration]:
	return [ImedIntegration()]
