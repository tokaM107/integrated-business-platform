# An account's ledger balance on a date, from the ledger rows the asking user may read (debit less credit).

from __future__ import annotations

import re
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, getdate

from imed_erp.assistant.core.context import RequestContext


def normal(text: str) -> str:
	"""Arabic as people type it: one form of alef, taa marbuta as haa, no tatweel or diacritics, "خزنة" as
	"خزينة" (both are said for a cash box)."""
	text = re.sub(r"[\u064B-\u0652\u0640]", "", (text or "").lower())
	for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي"), ("خزنه", "خزينه")):
		text = text.replace(a, b)
	return re.sub(r"\s+", " ", text).strip()


def readable_accounts(context: RequestContext, **filters) -> list[dict]:
	try:
		return frappe.get_list("Account", filters={"company": context.company, "is_group": 0, "disabled": 0, **filters}, fields=["name", "account_name"], limit=0)
	except frappe.PermissionError:
		frappe.clear_messages()
		return []


def cash_accounts(context: RequestContext) -> list[str]:
	"""The request company's cash boxes and banks the user may read, by name (for the planner to name one exactly)."""
	return [a.name for a in readable_accounts(context, account_type=["in", ["Cash", "Bank"]])]


def resolve_account(asked: str, context: RequestContext) -> str:
	"""The account meant: the exact name, else the one readable account of the company whose name holds every word
	asked (4 Nov 2026: the planner asked for "خزنة الأزاريطة", the chart says "خزينة مكتبة الأزاريطة - MMG")."""
	asked = (asked or "").strip()
	if not asked:
		raise frappe.ValidationError(_("Name the account."))
	if frappe.db.exists("Account", asked):
		return asked
	words = [w for w in normal(asked).replace("-", " ").split() if len(w) > 1]
	fits = [a.name for a in readable_accounts(context) if words and all(w in normal(f"{a.name} {a.account_name}") for w in words)]
	if len(fits) == 1:
		return fits[0]
	if fits:
		raise frappe.ValidationError(_("{0} fits several accounts: {1}. Name one.").format(asked, "; ".join(fits[:8])))
	raise frappe.ValidationError(_("No account named {0}. Cash boxes and banks: {1}.").format(asked, "; ".join(cash_accounts(context)[:15]) or "-"))


class AccountBalanceTool:
	name = "account_balance"

	def spec(self, context: RequestContext) -> dict[str, Any]:
		boxes = cash_accounts(context)
		listing = ("; ".join(boxes[:30])) or "none readable"
		return {
			"name": self.name,
			"description": "The ledger balance (debit less credit) of an account (a cash box, a wallet, a receivable or payable account) on a date. Give the account's name as in the chart of accounts; a part of it is matched when only one account fits. The cash boxes and banks: " + listing + ".",
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
		account = resolve_account(arguments.get("account"), context)
		# The account itself, as the user may see it (user permissions on Account, Company, Cost Center), and of the
		# company the user works in: a branch manager never reads another branch's box, nor another company's.
		doc = frappe.get_doc("Account", account)
		if not frappe.has_permission("Account", "read", doc=doc):
			raise frappe.PermissionError(_("Not allowed to read the account {0}.").format(account))
		if doc.company != context.company:
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
