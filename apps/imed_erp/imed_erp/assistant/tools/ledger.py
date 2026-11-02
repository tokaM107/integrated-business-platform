# An account's ledger balance on a date, from ERPNext's own balance function; the ledger's read permission applies.

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, getdate

from imed_erp.assistant.core.context import RequestContext


class AccountBalanceTool:
	name = "account_balance"

	def spec(self, context: RequestContext) -> dict[str, Any]:
		return {
			"name": self.name,
			"description": "The ledger balance of an account (a cash box, a wallet, a receivable or payable account) on a date, from ERPNext's own balance function. Use the account's full name as in the chart of accounts (list_records on Account to find it).",
			"input_schema": {
				"type": "object",
				"properties": {"account": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD; '' for today"}},
				"required": ["account", "date"],
				"additionalProperties": False,
			},
		}

	def run(self, arguments: dict, context: RequestContext) -> dict:
		if not frappe.has_permission("GL Entry", "read"):
			raise frappe.PermissionError(_("Not allowed to read the ledger."))
		account = arguments.get("account")
		if not frappe.db.exists("Account", account):
			raise frappe.ValidationError(_("No account named {0}.").format(account))
		from erpnext.accounts.utils import get_balance_on

		day = getdate(arguments.get("date")) if arguments.get("date") else getdate(context.today)
		return {"account": account, "date": str(day), "balance": flt(get_balance_on(account, date=day), 2)}
