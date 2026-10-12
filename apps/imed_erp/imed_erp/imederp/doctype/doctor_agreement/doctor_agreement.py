# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

# A doctor is a Customer in this group (CRM-01): one record for the person, whatever they buy or earn.
# setup/setup_core.py makes it.
DOCTOR_GROUP = "طبيب"

ACTIVE, SUSPENDED = "Active", "Suspended"

# DOC-30: which way the balance runs, set by the type. Books: the group owes the doctor his amount on the
# copies sold. App: the doctor owes the group the platform fees. A doctor's agreements are never offset
# against each other (owner's decision), so each keeps its own direction.
OWED_TO_DOCTOR, OWED_BY_DOCTOR = "Owed to Doctor", "Owed by Doctor"
DIRECTION = {"Books": OWED_TO_DOCTOR, "App": OWED_BY_DOCTOR}

# How each kind of ledger entry moves the balance: what is owed under the agreement grows with an accrual and
# shrinks with a payment or a cancellation charge; an adjustment counts with its own sign.
BALANCE_SIGN = {"Accrual": 1, "Payment": -1, "Cancellation Charge": -1, "Adjustment": 1}


class DoctorAgreement(Document):
	def validate(self):
		self.validate_doctor()
		self.balance_direction = DIRECTION.get(self.agreement_type)
		self.validate_terms()
		self.validate_settlement_period()

	def before_update_after_submit(self):
		# A submitted agreement takes new terms, a new status and the next settlement period without an
		# amendment; validate does not run then, so they are checked here. The summary is read again from the
		# ledger, so a form opened before an entry was posted saves the right figures.
		self.validate_terms()
		self.validate_settlement_period()
		self.balance = get_balance(self.name)
		self.last_settlement_date, self.last_settlement_amount = last_settlement(self.name)

	def validate_settlement_period(self):
		# DOC-05/29: each year has its own dates (owner, 12 Oct 2026), so the accountant enters the period
		# being settled; the next settlement is due at its end.
		if self.settlement_from and self.next_settlement_date and getdate(self.next_settlement_date) < getdate(self.settlement_from):
			frappe.throw(_("The settlement period ends before it starts. Check its dates."), title=_("Settlement Period"))

	def validate_doctor(self):
		if frappe.db.get_value("Customer", self.doctor, "customer_group") != DOCTOR_GROUP:
			frappe.throw(
				_("{0} is not a doctor. Choose a customer in the {1} group, or move this customer to it.").format(
					self.doctor, DOCTOR_GROUP
				),
				title=_("Not a Doctor"),
			)


	def validate_terms(self):
		# Books (owner's decision of 8 Oct 2026): the doctor's amount per copy sold, from each date.
		if self.agreement_type != "Books":
			self.terms = []
			return
		if not self.terms:
			frappe.throw(_("A books agreement needs the doctor's amount per copy. Add it under Agreement Terms."))
		for term in self.terms:
			term.valid_from = term.valid_from or self.start_date
			if flt(term.amount_per_copy) < 0:
				frappe.throw(_("Row #{0}: the doctor's amount per copy cannot be negative.").format(term.idx))
		dates = [getdate(term.valid_from) for term in self.terms]
		if len(set(dates)) != len(dates):
			frappe.throw(_("Two terms start on the same date. Keep one amount per date."))
		self.terms = sorted(self.terms, key=lambda term: getdate(term.valid_from))
		for idx, term in enumerate(self.terms, start=1):
			term.idx = idx
		self.keep_past_terms()

	def keep_past_terms(self):
		# Once submitted, a term already given stays as it was: editions were priced on it. A new amount is
		# a new row from a later date.
		before = self.get_doc_before_save()
		if self.docstatus != 1 or not before:
			return
		now = {(getdate(t.valid_from), flt(t.amount_per_copy)) for t in self.terms}
		for term in before.terms:
			if (getdate(term.valid_from), flt(term.amount_per_copy)) not in now:
				frappe.throw(
					_("The term from {0} was already in force. Add a new row from a later date instead of changing it.").format(
						frappe.format_value(term.valid_from, {"fieldtype": "Date"})
					),
					title=_("Term Already Given"),
				)


def get_amount_per_copy(agreement, date):
	"""The doctor's amount per copy in force on `date`: the latest term from on or before it, or None."""
	terms = frappe.get_all(
		"Doctor Agreement Term",
		filters={"parent": agreement, "parenttype": "Doctor Agreement", "valid_from": ["<=", date]},
		fields=["amount_per_copy"],
		order_by="valid_from desc",
		limit=1,
	)
	return flt(terms[0].amount_per_copy) if terms else None


def last_settlement(agreement):
	"""(date, amount) of the latest payment on the agreement in the doctor's ledger, or (None, 0)."""
	payments = frappe.get_all(
		"Doctor Ledger Entry",
		filters={"agreement": agreement, "entry_type": "Payment", "docstatus": 1},
		fields=["entry_date", "amount"],
		order_by="entry_date desc, creation desc",
		limit=1,
	)
	return (payments[0].entry_date, flt(payments[0].amount)) if payments else (None, 0)


def get_balance(agreement):
	"""What is owed under the agreement: its submitted ledger entries, each with the sign of its kind."""
	entries = frappe.get_all(
		"Doctor Ledger Entry", filters={"agreement": agreement, "docstatus": 1}, fields=["entry_type", "amount"]
	)
	return sum(BALANCE_SIGN.get(entry.entry_type, 0) * flt(entry.amount) for entry in entries)


def update_balance(agreement):
	"""The account summary is read-only and kept up to date from the ledger (Doctor Ledger Entry submit and
	cancel): the balance and the last settlement. Each agreement has its own; none is offset against another."""
	date, amount = last_settlement(agreement)
	frappe.db.set_value(
		"Doctor Agreement",
		agreement,
		{"balance": get_balance(agreement), "last_settlement_date": date, "last_settlement_amount": amount},
		update_modified=False,
	)


def check_active(agreement):
	"""A suspended agreement takes no new editions or subscriptions."""
	if frappe.db.get_value("Doctor Agreement", agreement, "status") == SUSPENDED:
		frappe.throw(
			_("Agreement {0} is suspended. Make it Active again before adding to it.").format(agreement),
			title=_("Agreement Suspended"),
		)
