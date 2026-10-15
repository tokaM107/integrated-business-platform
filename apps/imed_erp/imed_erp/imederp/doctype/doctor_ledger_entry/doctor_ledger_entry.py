# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, today

from imed_erp.imederp.doctor_accrual import PAYABLE_ACCOUNT, account, cancel
from imed_erp.imederp.doctype.book_edition.book_edition import get_copy_cost, get_sold_qty
from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import check_submitted, get_balance, update_balance
from imed_erp.imederp.doctype.expense.expense import APPROVER_ROLE, get_approvers, is_approver
from imed_erp.imederp.expense_reminders import notify

# Which agreement each kind of entry is for. Books: the group owes the doctor and pays him out; copies he asked
# for and left unsold are charged back to him (owner, 10 Oct 2026). App: the doctor owes the group its fees
# and the group collects them. Accruals and adjustments go on either.
ONLY_ON = {"Payout": "Books", "Unsold Copies Charge": "Books", "Collection": "App"}

# DOC-22: a deduction from the doctor is applied only once the owner or the accountant approves it, the same
# approvers and the same way as an expense (Expense Approver). Set only by the system, Approve and Reject.
PENDING, APPROVED, REJECTED = "Pending Approval", "Approved", "Rejected"
APPROVAL_FIELDS = ("approval_status", "approved_by", "rejection_reason")


class DoctorLedgerEntry(Document):
	def onload(self):
		# The form shows Approve and Reject from this.
		self.set_onload("is_approver", is_approver())

	def validate(self):
		self.protect_approval()
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
		self.validate_payout()

	def is_deduction(self):
		"""A charge for unsold copies, or an adjustment taking money off the doctor by hand. A credit note's
		adjustment is not one: the returned copies are simply no longer sold."""
		return self.entry_type == "Unsold Copies Charge" or (
			self.entry_type == "Adjustment" and flt(self.amount) < 0 and not self.sales_invoice
		)

	def protect_approval(self):
		# The form shows these read-only, but the server does not enforce that: a draft saved as Approved through
		# the API would otherwise be applied without an approver.
		if self.flags.approval_action:
			return
		before = self.get_doc_before_save()
		if not before:
			for field in APPROVAL_FIELDS:
				self.set(field, None)
			return
		if before.approval_status == REJECTED:
			frappe.throw(
				_("{0} was rejected and is closed. Make a new entry if it is still needed.").format(self.name),
				title=_("Rejected"),
			)
		if any(self.get(field) != before.get(field) for field in APPROVAL_FIELDS):
			frappe.throw(_("A deduction is approved or rejected only with Approve or Reject."), title=_("Approval Needed"))

	@frappe.whitelist()
	def approve(self):
		frappe.only_for(APPROVER_ROLE)
		self.check_waiting()
		self.approval_status, self.approved_by = APPROVED, frappe.session.user
		self.flags.approval_action = True
		self.submit()

	@frappe.whitelist()
	def reject(self, reason=None):
		frappe.only_for(APPROVER_ROLE)
		self.check_waiting()
		# Saved, so the history keeps who rejected it and why; from now on it cannot be changed or submitted.
		self.approval_status, self.approved_by, self.rejection_reason = REJECTED, frappe.session.user, reason
		self.flags.approval_action = True
		self.save()

	def check_waiting(self):
		if self.docstatus != 0 or not self.is_deduction() or self.approval_status == REJECTED:
			frappe.throw(_("{0} is not a deduction waiting for approval.").format(self.name))

	def validate_approved(self):
		if not self.is_deduction() or self.approval_status == APPROVED:
			return
		# An approver's own deduction is approved as he submits it, like an expense.
		if is_approver():
			self.approval_status, self.approved_by = APPROVED, frappe.session.user
			return
		frappe.throw(
			_("A deduction from a doctor is applied only once the owner or the accountant approves it."),
			title=_("Approval Needed"),
		)

	def validate_payout(self):
		# DOC-09, ACC-11: money paid to the doctor comes out of a treasury, in part and as often as needed, but
		# never more than he is owed (that would leave him a debt by mistake; DOC-20 debts come from charges).
		if self.entry_type != "Payout":
			self.treasury = None
			return
		if not self.treasury:
			frappe.throw(_("Choose the treasury the money is paid from."), title=_("Treasury Required"))
		treasury = frappe.db.get_value("Account", self.treasury, ["account_type", "is_group"], as_dict=True)
		if not treasury or treasury.is_group or treasury.account_type not in ("Cash", "Bank"):
			frappe.throw(_("{0} is not a treasury. Choose a cash box or a wallet.").format(self.treasury), title=_("Wrong Treasury"))
		owed = flt(get_balance(self.agreement), 2)
		if flt(self.amount) > owed:
			frappe.throw(
				_("The doctor is owed {0} under {1}; a payout of {2} is more than that. Pay {0} or less.").format(
					owed, self.agreement, flt(self.amount)
				),
				title=_("More Than Owed"),
			)

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

	def before_submit(self):
		self.validate_approved()
		if self.entry_type == "Payout":
			self.journal_entry = self.post_payout()

	def post_payout(self):
		"""Dr مستحقات للأطباء — الكتب / Cr the treasury. The journal entry runs its own checks, among them the
		treasuries the user may pay from (treasuries.check_entry_treasuries)."""
		company = frappe.db.get_value("Account", self.treasury, "company")
		doctor = frappe.db.get_value("Doctor Agreement", self.agreement, "doctor")
		journal_entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": company,
				"posting_date": self.entry_date,
				"accounts": [
					{"account": account(company, PAYABLE_ACCOUNT), "debit_in_account_currency": flt(self.amount)},
					{"account": self.treasury, "credit_in_account_currency": flt(self.amount)},
				],
				"user_remark": _("Payout to {0} under {1} ({2}).").format(doctor, self.agreement, self.name),
			}
		)
		journal_entry.insert()
		journal_entry.submit()
		return journal_entry.name

	# The agreement's Balance is worked out from these entries (doctor_agreement.py).
	def on_submit(self):
		update_balance(self.agreement, self)

	def on_cancel(self):
		# A payout's journal entry goes with it; a sale's goes with the sale (doctor_accrual.cancel_accruals).
		if self.entry_type == "Payout" and self.journal_entry:
			if frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
				cancel("Journal Entry", self.journal_entry)
		update_balance(self.agreement, self)


UNSOLD = "Unsold Copies Charge"


def charge_unsold_copies(period):
	"""When a term or a module ends (its Academic Period is closed), the copies the doctor asked for and did not
	sell are charged to him at what they cost to make (owner, 10 Oct 2026; DOC-18). Copies the library added are
	its own, so sales count against the doctor's copies first. Each charge is a draft: it is applied only when the
	accountant or the owner submits it (DOC-22). An edition already charged for the period is skipped, so closing
	again adds nothing. Returns the drafts made."""
	periods = [period, *descendants(period)]
	drafts = []
	for edition in frappe.get_all(
		"Book Edition",
		filters={"docstatus": 1},
		fields=["name", "agreement", "period", "carried_to_period", "status", "doctor_qty", "edition_name",
			"paper_cost", "ink_cost", "overhead_cost", "pages", "binding_cost"],
	):
		# An edition carried forward ends with the period it was carried to.
		current = edition.carried_to_period or edition.period
		if current not in periods:
			continue
		unsold = cint(edition.doctor_qty) - cint(get_sold_qty(edition.name))
		amount = flt(max(unsold, 0) * get_copy_cost(edition), 2)
		if amount <= 0 or frappe.db.exists(
			"Doctor Ledger Entry", {"edition": edition.name, "period": current, "entry_type": UNSOLD, "docstatus": ["<", 2]}
		):
			continue
		entry = frappe.get_doc(
			{
				"doctype": "Doctor Ledger Entry",
				"agreement": edition.agreement,
				"period": current,
				"entry_date": today(),
				"entry_type": UNSOLD,
				"edition": edition.name,
				"qty": unsold,
				"amount": amount,
				"remarks": _("{0}: {1} of the doctor's {2} copies unsold x {3} a copy, when {4} ended.").format(
					edition.edition_name, unsold, cint(edition.doctor_qty), get_copy_cost(edition), period
				),
			}
		)
		# Closing a period is the accountant's or the owner's (Academic Period); the charge waits for an approver.
		entry.approval_status = PENDING
		entry.flags.approval_action = True
		entry.insert()
		drafts.append(entry.name)
		notify(
			get_approvers(),
			_("Charge {0} of {1} on {2} for unsold copies of {3} is waiting for your approval.").format(
				entry.name, frappe.format_value(amount, {"fieldtype": "Currency"}), edition.agreement, edition.edition_name
			),
			"Doctor Ledger Entry",
			entry.name,
			event="expense_approval",
		)
	return drafts


def descendants(period):
	"""The rounds and modules under a period, at any depth."""
	found, parents = [], [period]
	while parents:
		children = frappe.get_all("Academic Period", filters={"parent_period": ["in", parents]}, pluck="name")
		found += children
		parents = children
	return found

