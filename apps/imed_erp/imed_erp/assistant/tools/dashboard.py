# The dashboard's figures, read from the dashboard itself: the Number Cards of the workspaces the sidebar links
# (each card's own method or aggregate, with its own permission check), and the owner's live band
# (imederp.owner_yesterday, the owner's alone). Nothing is listed by name here: a card added to the workspace is
# read by the assistant the next request.

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt

from imed_erp.assistant.core.context import RequestContext

LEDGER_CARD_METHODS_PREFIX = "imed_erp.imederp.owner_figures."


class DashboardTool:
	name = "dashboard_today"

	def __init__(self, workspaces: list[str]):
		self.workspaces = workspaces

	def spec(self, context: RequestContext) -> dict[str, Any]:
		cards = [c.label for c in self.cards()]
		return {
			"name": self.name,
			"description": "The dashboard's live figures: its cards (" + ", ".join(cards[:20]) + (")" if len(cards) <= 20 else ", ...)") + " and, for the owner, today's band: revenue and expenses by business, today's bookings, the halls, the app's fees, printing counters and the integrations' health. Start here for anything about today or this month.",
			"input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
		}

	def cards(self) -> list:
		seen, out = set(), []
		for ws in self.workspaces:
			for row in frappe.get_all("Workspace Number Card", filters={"parent": ws, "parenttype": "Workspace"}, fields=["number_card_name", "label"], order_by="idx"):
				if row.number_card_name not in seen:
					seen.add(row.number_card_name)
					out.append(row)
		return out

	def card_value(self, card: str) -> Any:
		doc = frappe.get_cached_doc("Number Card", card)
		if doc.type == "Custom" and doc.method:
			return frappe.get_attr(doc.method)().get("value")
		if doc.type == "Document Type":
			from frappe.desk.doctype.number_card.number_card import get_result

			return get_result(doc, doc.filters_json or "[]")
		return None

	def run(self, arguments: dict, context: RequestContext) -> dict:
		values = {}
		for card in self.cards():
			try:
				values[card.label] = flt(self.card_value(card.number_card_name), 2)
			except frappe.PermissionError:
				values[card.label] = "not allowed for this user"
			except Exception as e:  # one broken card never hides the others
				values[card.label] = f"error: {str(e)[:80]}"
		out: dict[str, Any] = {"cards": values}
		band = self.band()
		if band is not None:
			out["band"] = band
			if band.get("ledger_entries_all_time") == 0:
				out["note"] = "no accounting record exists yet: the ledger cards' zeros are missing data, not a result"
		return out

	def band(self) -> dict | None:
		"""The owner's band, compacted; None for a user it refuses."""
		from imed_erp.imederp import owner_yesterday

		try:
			band = owner_yesterday.get_yesterday()
		except frappe.PermissionError:
			frappe.clear_messages()
			return None
		money = band.get("money") or {}
		return {
			"day": band.get("day"),
			"ledger_entries_all_time": band.get("ledger_entries_all_time"),
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
