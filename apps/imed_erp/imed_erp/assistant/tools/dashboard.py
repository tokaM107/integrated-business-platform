# The dashboard's figures, read from the dashboard itself: the Number Cards of the workspaces an integration names,
# for a workspace the asking user may open (its roles), each card evaluated as the desk evaluates it: a Custom
# card by its method, only if that method is whitelisted (callable from the desk at all), a Document Type card by
# Frappe's own get_result (permissions applied). A card added to a workspace is read on the next request.

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt

from imed_erp.assistant.core.context import RequestContext


def workspace_allowed(workspace: str) -> bool:
	roles = set(frappe.get_all("Has Role", filters={"parent": workspace, "parenttype": "Workspace"}, pluck="role"))
	return not roles or bool(roles & set(frappe.get_roles()))


class DashboardTool:
	name = "dashboard_cards"

	def __init__(self, workspaces: list[str]):
		self.workspaces = [ws for ws in workspaces if frappe.db.exists("Workspace", ws) and workspace_allowed(ws)]
		self._cards = None

	def cards(self) -> list:
		if self._cards is None:
			seen, self._cards = set(), []
			for ws in self.workspaces:
				for row in frappe.get_all("Workspace Number Card", filters={"parent": ws, "parenttype": "Workspace"}, fields=["number_card_name", "label"], order_by="idx"):
					if row.number_card_name not in seen:
						seen.add(row.number_card_name)
						self._cards.append(row)
		return self._cards

	def spec(self, context: RequestContext) -> dict[str, Any]:
		labels = [c.label for c in self.cards()]
		return {
			"name": self.name,
			"description": "The dashboard's cards, live: " + ", ".join(labels) + ". Start here for anything the dashboard shows.",
			"input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
		}

	@staticmethod
	def card_value(card: str) -> Any:
		doc = frappe.get_cached_doc("Number Card", card)
		if doc.type == "Custom" and doc.method:
			method = frappe.get_attr(doc.method)
			frappe.is_whitelisted(method)  # raises PermissionError unless the desk could call it too
			return method().get("value")
		if doc.type == "Document Type":
			from frappe.desk.doctype.number_card.number_card import get_result

			return get_result(doc, doc.filters_json or "[]")
		raise frappe.ValidationError(f"card type {doc.type} is not read by the assistant")

	def run(self, arguments: dict, context: RequestContext) -> dict:
		values: dict[str, Any] = {}
		for card in self.cards():
			try:
				values[card.label] = flt(self.card_value(card.number_card_name), 2)
			except frappe.PermissionError:
				values[card.label] = "not allowed for this user"
			except frappe.ValidationError as e:  # one card that cannot be read never hides the others
				values[card.label] = f"not readable: {str(e)[:80]}"
			finally:
				frappe.clear_messages()
		return {"cards": values}
