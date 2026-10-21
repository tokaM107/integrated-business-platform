# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Two settings of the cash close that wait for a decision (21 Oct 2026):
# - the reporting week: its first and last working days (owner, 21 Oct 2026: Saturday to Thursday, Friday off);
#   empty, a weekly review may start on any day and covers seven days;
# - whether shortages may be recovered from employees at all: off until the owner approves a written policy checked
#   by a lawyer or HR. Only the owner switches it, and who and when is kept. Nothing is deducted from a salary by the
#   system either way (cash_discrepancy.py).

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

OWNER_ROLE = "Super Admin"


class CashCloseSettings(Document):
	def validate(self):
		before = self.get_doc_before_save()
		was = cint(before.recovery_policy_approved) if before else 0
		if cint(self.recovery_policy_approved) == was:
			return
		if OWNER_ROLE not in frappe.get_roles():
			frappe.throw(_("Only the owner approves or withdraws the recovery policy."), frappe.PermissionError)
		if self.recovery_policy_approved and not (self.recovery_policy_reference or "").strip():
			frappe.throw(_("Name the approved policy first: its title, date and who checked it."), title=_("Policy Needed"))
		self.recovery_policy_approved_by = frappe.session.user
		self.recovery_policy_approved_on = now_datetime()


def week_starts_on():
	return frappe.db.get_single_value("Cash Close Settings", "week_starts_on") or None


def week_ends_on():
	return frappe.db.get_single_value("Cash Close Settings", "week_ends_on") or None


def recovery_allowed():
	return bool(cint(frappe.db.get_single_value("Cash Close Settings", "recovery_policy_approved")))
