# An account's ledger balance on a date, from the ledger rows the asking user may read (debit less credit).

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
			"description": "The ledger balance (debit less credit) of an account (a cash box, a wallet, a receivable or payable account) on a date. Use the account's full name as in the chart of accounts (list_records on Account to find it).",
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
		if not account or not frappe.db.exists("Account", account):
			raise frappe.ValidationError(_("No account named {0}.").format(account))
		# The account itself, as the user may see it (user permissions on Account, Company, Cost Center), and of the
		# company the user works in: a branch manager never reads another branch's box, nor another company's.
		doc = frappe.get_doc("Account", account)
		if not frappe.has_permission("Account", "read", doc=doc):
			raise frappe.PermissionError(_("Not allowed to read the account {0}.").format(account))
		if context.company and doc.company != context.company:
			raise frappe.PermissionError(_("{0} is not an account of {1}.").format(account, context.company))
		# The balance from the ledger rows the user may read (frappe.get_list applies the GL Entry user permissions,
		# e.g. a cost center), so a restricted user never gets the whole account's balance.
		day = getdate(arguments.get("date")) if arguments.get("date") else getdate(context.today)
		rows = frappe.get_list(
			"GL Entry",
			filters={"account": account, "is_cancelled": 0, "posting_date": ["<=", day]},
			fields=[{"SUM": "debit", "as": "debit"}, {"SUM": "credit", "as": "credit"}],
		)
		balance = flt(rows[0].debit) - flt(rows[0].credit) if rows else 0
		return {"account": account, "date": str(day), "balance": flt(balance, 2)}
