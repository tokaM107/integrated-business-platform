# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The daily close of a treasury (ACC-03: "a daily close that compares the actual balance with the recorded one";
# Manager / Accountant). Each day and cash box once: the day as the books show it (at the start of the day, money in,
# money out, the expected balance, from the ledger as Treasury Balances shows it), the cash counted, and the
# difference. Who counted it and when are kept; the record is submitted, and cancelled by the accounts like any
# other.
#
# What it does not do, because nobody has decided it yet (docs/known-issues.md, ACC-03): it posts nothing for a
# difference (the account فروقات الخزينة exists, the treatment does not), it needs nobody's approval, and it does
# not stop a closed day from taking more entries.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from imed_erp.imederp.branches import check_has_branch
from imed_erp.imederp.report.treasury_balances.treasury_balances import day_figures
from imed_erp.imederp.treasuries import check_treasury

TREASURY_TYPES = ("Cash", "Bank")


class TreasuryClose(Document):
	def validate(self):
		self.check_treasury()
		self.check_once_a_day()
		if flt(self.counted) < 0:
			frappe.throw(_("The cash counted cannot be below zero."))
		if self.is_new() or not self.counted_by:
			self.counted_by = frappe.session.user
		self.set_figures()

	def before_submit(self):
		# Entries may have been posted since it was saved: the books as they are when it is submitted.
		self.set_figures()

	def check_treasury(self):
		account = frappe.db.get_value("Account", self.treasury, ["account_type", "is_group"], as_dict=True)
		if not account or account.is_group or account.account_type not in TREASURY_TYPES:
			frappe.throw(_("{0} is not a treasury. Choose a cash box or a wallet.").format(self.treasury), title=_("Wrong Treasury"))
		if frappe.db.get_value("Cost Center", self.business, "is_group"):
			frappe.throw(_("Cost Center {0} is a group. Choose a business under it.").format(self.business))
		allowed = frappe.get_all(
			"User Permission", filters={"user": frappe.session.user, "allow": "Cost Center"}, pluck="for_value"
		)
		check_has_branch(allowed)
		# A branch manager closes her own business's cash box or a group wallet (treasuries.py).
		check_treasury(self.business, self.treasury)

	def check_once_a_day(self):
		# Locked first, so two people closing the same box at once wait for each other.
		frappe.db.get_value("Account", self.treasury, "name", for_update=True)
		other = frappe.db.exists(
			"Treasury Close",
			{"treasury": self.treasury, "close_date": self.close_date, "docstatus": ("<", 2), "name": ("!=", self.name)},
		)
		if other:
			frappe.throw(
				_("{0} is already closed for {1}: {2}.").format(
					self.treasury, frappe.format_value(self.close_date, {"fieldtype": "Date"}), other
				),
				title=_("Already Closed"),
			)

	def set_figures(self):
		self.opening, self.money_in, self.money_out = day_figures([self.treasury], self.close_date)[self.treasury]
		self.expected = flt(self.opening + self.money_in - self.money_out, 2)
		self.difference = flt(flt(self.counted) - self.expected, 2)
