# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import check_submitted, update_balance


class DoctorLedgerEntry(Document):
	def validate(self):
		check_submitted(self.agreement)
		# The kind of entry gives the sign (doctor_agreement.BALANCE_SIGN); only an adjustment carries its own.
		if self.entry_type != "Adjustment" and flt(self.amount) <= 0:
			frappe.throw(_("The amount must be greater than zero; an Adjustment carries its own sign."))
		if self.entry_type == "Adjustment" and not flt(self.amount):
			frappe.throw(_("An adjustment needs an amount."))
		agreement_type = frappe.db.get_value("Doctor Agreement", self.agreement, "agreement_type")
		if self.entry_type == "Cancellation Charge" and agreement_type != "Books":
			frappe.throw(_("A cancellation charge is for a books agreement."))
		if self.edition and frappe.db.get_value("Book Edition", self.edition, "agreement") != self.agreement:
			frappe.throw(_("Edition {0} belongs to another agreement.").format(self.edition))

	# The agreement's Balance is worked out from these entries (doctor_agreement.py).
	def on_submit(self):
		update_balance(self.agreement)

	def on_cancel(self):
		update_balance(self.agreement)
