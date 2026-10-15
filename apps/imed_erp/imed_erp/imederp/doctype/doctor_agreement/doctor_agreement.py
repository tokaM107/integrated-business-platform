# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

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
# shrinks with a payout to the doctor, a charge for unsold copies or a collection from him; an adjustment
# counts with its own sign.
BALANCE_SIGN = {"Accrual": 1, "Payout": -1, "Unsold Copies Charge": -1, "Adjustment": 1, "Collection": -1}

# A settlement is money changing hands: paid out to the doctor (books) or collected from him (app).
SETTLEMENTS = ["Payout", "Collection"]


class DoctorAgreement(Document):
	def validate(self):
		self.validate_doctor()
		self.balance_direction = DIRECTION.get(self.agreement_type)
		self.validate_terms()
		self.validate_settlement_period()
		self.set_summary()

	def set_summary(self):
		# SEC-07: the balance is never typed, not even through the API; it is the doctor's ledger, where every
		# change is an entry made by the accountant or the owner.
		self.balance = get_balance(self.name) if not self.is_new() else 0
		self.last_settlement_date, self.last_settlement_amount = last_settlement(self.name) if not self.is_new() else (None, 0)

	def before_update_after_submit(self):
		# A submitted agreement takes new terms, a new status and the next settlement period without an
		# amendment; validate does not run then, so they are checked here. The summary is read again from the
		# ledger, so a form opened before an entry was posted saves the right figures.
		self.validate_terms()
		self.validate_settlement_period()
		self.set_summary()

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
		# a new row from after the last one, so no edition already dated is moved to another amount. A term
		# that has not started yet may still be taken back.
		before = self.get_doc_before_save()
		if self.docstatus != 1 or not before:
			return
		given = {(getdate(t.valid_from), flt(t.amount_per_copy)) for t in before.terms}
		now = {(getdate(t.valid_from), flt(t.amount_per_copy)) for t in self.terms}
		last = max((date for date, _amount in given), default=None)
		for date, _amount in now - given:
			if last and date <= last:
				frappe.throw(
					_("A new term starts after the last one, {0}. An earlier date would change editions already priced.").format(
						frappe.format_value(last, {"fieldtype": "Date"})
					),
					title=_("Term Already Given"),
				)
		for term in before.terms:
			if (getdate(term.valid_from), flt(term.amount_per_copy)) not in now and getdate(term.valid_from) <= getdate(today()):
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
	"""(date, amount) of the latest payout or collection on the agreement in the doctor's ledger, or (None, 0)."""
	payments = frappe.get_all(
		"Doctor Ledger Entry",
		filters={"agreement": agreement, "entry_type": ["in", SETTLEMENTS], "docstatus": 1},
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


@frappe.whitelist()
def get_doctor_summary(doctor):
	"""DOC-29: the doctor's file (his Customer) shows every agreement of his with its balance, which way it runs and
	when it is next settled. The balances stay apart: nothing is offset between them. Empty for whoever may not
	read the agreements (a branch manager adding a customer)."""
	if not frappe.has_permission("Doctor Agreement", "read"):
		return []
	summary = []
	for agreement in frappe.get_all(
		"Doctor Agreement",
		filters={"doctor": doctor, "docstatus": 1},
		fields=["name", "agreement_type", "status", "balance", "next_settlement_date"],
		order_by="agreement_type, name",
	):
		direction = DIRECTION.get(agreement.agreement_type)
		if flt(agreement.balance) < 0:
			# DOC-20, DOC-30: below zero it runs the other way.
			direction = OWED_BY_DOCTOR if direction == OWED_TO_DOCTOR else OWED_TO_DOCTOR
		summary.append(
			{
				"agreement": agreement.name,
				"agreement_type": _(agreement.agreement_type),
				"status": _(agreement.status),
				"balance": abs(flt(agreement.balance)),
				"direction": _(direction),
				"owed_by_doctor": direction == OWED_BY_DOCTOR,
				"next_settlement_date": agreement.next_settlement_date,
			}
		)
	return summary


def open_amounts(agreement, as_of, owed_by_doctor=False):
	"""What is still open under the agreement up to `as_of`, as the parts it arose in, oldest first: each a dict of
	the date, period, branch and amount still open. Later movements the other way settle the oldest parts first, so
	a payout pays the oldest dues and the next amount earned pays the oldest debt (DOC-20).

	owed_by_doctor: the doctor's debt (a books balance below zero, an app's fees not collected); otherwise what the
	group owes him. Doctor Dues and Doctor Debts are built on this."""
	agreement_type = frappe.db.get_value("Doctor Agreement", agreement, "agreement_type")
	# The balance runs in the agreement's own direction (DIRECTION); turn it to the side asked for.
	side = 1 if (DIRECTION.get(agreement_type) == OWED_BY_DOCTOR) == bool(owed_by_doctor) else -1
	position, parts = 0, []
	for entry in frappe.get_all(
		"Doctor Ledger Entry",
		filters={"agreement": agreement, "docstatus": 1, "entry_date": ["<=", as_of]},
		fields=["entry_date", "entry_type", "amount", "period", "branch"],
		order_by="entry_date, creation",
	):
		before = max(position, 0)
		position += side * BALANCE_SIGN.get(entry.entry_type, 0) * flt(entry.amount)
		after = max(position, 0)
		if after > before:
			parts.append(
				frappe._dict(date=getdate(entry.entry_date), period=entry.period, branch=entry.branch, amount=after - before)
			)
			continue
		settled = before - after
		while settled > 0 and parts:
			taken = min(settled, parts[0].amount)
			parts[0].amount -= taken
			settled -= taken
			if not parts[0].amount:
				parts.pop(0)
	for part in parts:
		part.amount = flt(part.amount, 2)
	return [part for part in parts if part.amount]


def update_balance(agreement, entry=None):
	"""The account summary is read-only and kept up to date from the ledger (Doctor Ledger Entry submit and
	cancel): the balance and the last settlement. Each agreement has its own; none is offset against another.

	SEC-07: a change made by hand (`entry` not posted by a sale) goes into the agreement's history too, with the
	balance before and after, who and when, as if the field had been edited. Sales post too many to list there;
	each one is on its invoice."""
	date, amount = last_settlement(agreement)
	before = frappe.db.get_value(
		"Doctor Agreement", agreement, ["balance", "last_settlement_date", "last_settlement_amount"], as_dict=True
	)
	after = {"balance": get_balance(agreement), "last_settlement_date": date, "last_settlement_amount": amount}
	frappe.db.set_value("Doctor Agreement", agreement, after, update_modified=False)
	if entry is not None and not entry.get("sales_invoice"):
		changed = [
			[field, before.get(field), value]
			for field, value in after.items()
			if (
				str(before.get(field) or "") != str(value or "")
				if field == "last_settlement_date"
				else flt(before.get(field)) != flt(value)
			)
		]
		if changed:
			frappe.get_doc(
				{
					"doctype": "Version",
					"ref_doctype": "Doctor Agreement",
					"docname": agreement,
					"data": frappe.as_json({"changed": changed, "added": [], "removed": [], "row_changed": []}),
				}
			).insert(ignore_permissions=True)


def check_submitted(agreement):
	"""Editions, subscriptions and ledger entries go on a submitted agreement: a draft's terms can still change
	under them, and a cancelled one is replaced by its amended copy."""
	docstatus = frappe.db.get_value("Doctor Agreement", agreement, "docstatus")
	if docstatus == 0:
		frappe.throw(_("Agreement {0} is not submitted yet. Submit it before adding to it.").format(agreement), title=_("Agreement Not Submitted"))
	if docstatus == 2:
		frappe.throw(_("Agreement {0} was cancelled. Use its amended copy.").format(agreement), title=_("Agreement Cancelled"))


def check_active(agreement):
	"""A suspended agreement takes no new editions or subscriptions."""
	check_submitted(agreement)
	if frappe.db.get_value("Doctor Agreement", agreement, "status") == SUSPENDED:
		frappe.throw(
			_("Agreement {0} is suspended. Make it Active again before adding to it.").format(agreement),
			title=_("Agreement Suspended"),
		)
