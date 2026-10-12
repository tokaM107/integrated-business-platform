# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import update_balance


class DoctorLedgerEntry(Document):
	# The agreement's Balance is worked out from these entries (doctor_agreement.py).
	def on_submit(self):
		update_balance(self.agreement)

	def on_cancel(self):
		update_balance(self.agreement)
