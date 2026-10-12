# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# A doctor is a Customer in this group (CRM-01): one record for the person, whatever they buy or earn.
# setup/setup_core.py makes it.
DOCTOR_GROUP = "طبيب"

ACTIVE, SUSPENDED = "Active", "Suspended"

# How each kind of ledger entry moves the balance: what is owed under the agreement grows with an accrual and
# shrinks with a payment or a cancellation charge; an adjustment counts with its own sign.
BALANCE_SIGN = {"Accrual": 1, "Payment": -1, "Cancellation Charge": -1, "Adjustment": 1}


class DoctorAgreement(Document):
	def validate(self):
		self.validate_doctor()

	def validate_doctor(self):
		if frappe.db.get_value("Customer", self.doctor, "customer_group") != DOCTOR_GROUP:
			frappe.throw(
				_("{0} is not a doctor. Choose a customer in the {1} group, or move this customer to it.").format(
					self.doctor, DOCTOR_GROUP
				),
				title=_("Not a Doctor"),
			)


def get_balance(agreement):
	"""What is owed under the agreement: its submitted ledger entries, each with the sign of its kind."""
	entries = frappe.get_all(
		"Doctor Ledger Entry", filters={"agreement": agreement, "docstatus": 1}, fields=["entry_type", "amount"]
	)
	return sum(BALANCE_SIGN.get(entry.entry_type, 0) * flt(entry.amount) for entry in entries)


def update_balance(agreement):
	"""The Balance field is read-only and kept up to date from the ledger (Doctor Ledger Entry submit and cancel)."""
	frappe.db.set_value("Doctor Agreement", agreement, "balance", get_balance(agreement), update_modified=False)


def check_active(agreement):
	"""A suspended agreement takes no new editions or subscriptions."""
	if frappe.db.get_value("Doctor Agreement", agreement, "status") == SUSPENDED:
		frappe.throw(
			_("Agreement {0} is suspended. Make it Active again before adding to it.").format(agreement),
			title=_("Agreement Suspended"),
		)
