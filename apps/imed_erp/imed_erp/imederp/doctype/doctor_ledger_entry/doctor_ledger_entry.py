# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import check_submitted, update_balance

# Which agreement each kind of entry is for. Books: the group owes the doctor and pays him out; copies he asked
# for and left unsold are charged back to him (owner, 10 Oct 2026). App: the doctor owes the group its fees
# and the group collects them. Accruals and adjustments go on either.
ONLY_ON = {"Payout": "Books", "Unsold Copies Charge": "Books", "Collection": "App"}


class DoctorLedgerEntry(Document):
	def validate(self):
		check_submitted(self.agreement)
		# The kind of entry gives the sign (doctor_agreement.BALANCE_SIGN); only an adjustment carries its own.
		if self.entry_type != "Adjustment" and flt(self.amount) <= 0:
			frappe.throw(_("The amount must be greater than zero; an Adjustment carries its own sign."))
		if self.entry_type == "Adjustment" and not flt(self.amount):
			frappe.throw(_("An adjustment needs an amount."))
		agreement_type = frappe.db.get_value("Doctor Agreement", self.agreement, "agreement_type")
		if ONLY_ON.get(self.entry_type, agreement_type) != agreement_type:
			frappe.throw(_("{0} is for a {1} agreement only.").format(_(self.entry_type), _(ONLY_ON[self.entry_type])))
		if self.edition and frappe.db.get_value("Book Edition", self.edition, "agreement") != self.agreement:
			frappe.throw(_("Edition {0} belongs to another agreement.").format(self.edition))
		self.validate_source()

	def validate_source(self):
		# The sale behind an accrual: its invoice and the invoice line, so the same copies sold are never
		# counted twice (DOC-07).
		if not self.invoice_item:
			return
		if frappe.db.get_value("Sales Invoice Item", self.invoice_item, "parent") != self.sales_invoice:
			frappe.throw(_("Invoice line {0} is not on invoice {1}.").format(self.invoice_item, self.sales_invoice))
		counted = frappe.db.exists(
			"Doctor Ledger Entry",
			{
				"invoice_item": self.invoice_item,
				"entry_type": self.entry_type,
				"docstatus": ["<", 2],
				"name": ["!=", self.name],
			},
		)
		if counted:
			frappe.throw(
				_("Invoice line {0} of {1} is already in the doctor's ledger: {2}.").format(
					self.invoice_item, self.sales_invoice, counted
				),
				title=_("Already Counted"),
			)

	# The agreement's Balance is worked out from these entries (doctor_agreement.py).
	def on_submit(self):
		update_balance(self.agreement)

	def on_cancel(self):
		update_balance(self.agreement)
