# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from imed_erp.imederp.doctor_accrual import EXPENSE_ACCOUNT, PAYABLE_ACCOUNT, account, cancel
from imed_erp.imederp.platform_fee_posting import RECEIVABLE_ACCOUNT, REVENUE_ACCOUNT, app_cost_center
from imed_erp.imederp.doctype.book_edition.book_edition import get_copy_cost, get_sold_qty
from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import BALANCE_SIGN, check_submitted, get_balance, update_balance
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
		if self.app_course and frappe.db.get_value("App Course", self.app_course, "agreement") != self.agreement:
			frappe.throw(_("Course {0} belongs to another agreement.").format(self.app_course))
		self.refuse_unsold_copies_charge()
		self.validate_source()
		self.validate_payout()

	def refuse_unsold_copies_charge(self):
		"""Owner, 21 Oct 2026: the doctor bears nothing for copies left unsold, carried forward or made obsolete by a
		change of curriculum; the library bears the loss (book_edition.dispose_as_scrap). No charge is saved or
		submitted any more. One recorded before stays on record: a draft can only be rejected, a submitted one
		cancelled (docs/known-issues.md lists them)."""
		if self.entry_type != UNSOLD:
			return
		if self.flags.approval_action and self.approval_status == REJECTED:
			return
		frappe.throw(
			_("A doctor is never charged for unsold copies: the library bears them. A curriculum change is disposed of as scrap on the edition."),
			title=_("Not Charged to the Doctor"),
		)

	def is_deduction(self):
		"""A charge for unsold copies, or an adjustment taking money off the doctor by hand. A credit note's
		adjustment is not one: the returned copies are simply no longer sold."""
		return self.entry_type == "Unsold Copies Charge" or (
			self.entry_type == "Adjustment" and flt(self.amount) < 0 and not self.sales_invoice and not self.app_course
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
		# APP-06: money collected from him goes into a treasury, never more than he owes.
		if self.entry_type not in ("Payout", "Collection"):
			self.treasury = None
			return
		if not self.treasury:
			frappe.throw(
				_("Choose the treasury the money is paid from.")
				if self.entry_type == "Payout"
				else _("Choose the treasury the money goes into."),
				title=_("Treasury Required"),
			)
		treasury = frappe.db.get_value("Account", self.treasury, ["account_type", "is_group"], as_dict=True)
		if not treasury or treasury.is_group or treasury.account_type not in ("Cash", "Bank"):
			frappe.throw(_("{0} is not a treasury. Choose a cash box or a wallet.").format(self.treasury), title=_("Wrong Treasury"))
		# QA-11: the agreement's row is locked first, so two payouts or collections submitted together wait for each
		# other and the second sees the balance the first left.
		lock_agreement(self.agreement)
		owed = flt(get_balance(self.agreement), 2)
		if self.entry_type == "Collection":
			if flt(self.amount) > owed:
				frappe.throw(
					_("The doctor owes {0} under {1}; a collection of {2} is more than that. Collect {0} or less.").format(
						owed, self.agreement, flt(self.amount)
					),
					title=_("More Than Owed"),
				)
			return
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
		elif self.entry_type == "Collection":
			self.journal_entry = self.post_collection()
		elif self.is_entered_by_hand():
			self.journal_entry = self.post_by_hand()

	def is_entered_by_hand(self):
		"""An accrual, an adjustment, or a charge for unsold copies recorded before 21 Oct 2026, that no sale and no
		course posted."""
		return self.entry_type in ("Accrual", "Adjustment", UNSOLD) and not self.sales_invoice and not self.app_course

	def post_by_hand(self):
		"""QA-02: the accounts follow the doctor's ledger for what is entered by hand too, or the two drift apart.
		  Books, more for the doctor (an accrual, a plus adjustment):
		    Dr حصة الأطباء / Cr مستحقات للأطباء — الكتب, as a sale posts it (doctor_accrual.py)
		  Books, less (a charge for unsold copies, a minus adjustment): the other way round. The charge takes back
		    what the copies cost from the doctors' share, so the payable stays equal to the ledger (accountant to
		    confirm; known-issues.md).
		  App, more (a plus adjustment, an accrual): Dr مستحقات على الأطباء — رسوم المنصة (party: the doctor) /
		    Cr إيراد رسوم المنصة, as a course posts it (platform_fee_posting.py); less: the other way round.
		Every line on the business's cost center: the edition's library for books, the app for app fees."""
		amount = abs(flt(self.amount))
		more = BALANCE_SIGN.get(self.entry_type, 0) * flt(self.amount) > 0
		agreement = frappe.db.get_value("Doctor Agreement", self.agreement, ["doctor", "agreement_type"], as_dict=True)
		if agreement.agreement_type == "App":
			# The doctor owes the group: more on his account is more owed by him.
			cost_center = app_cost_center()
			debit = {"account": RECEIVABLE_ACCOUNT, "party_type": "Customer", "party": agreement.doctor}
			credit = {"account": REVENUE_ACCOUNT}
		else:
			cost_center = self.books_cost_center()
			debit, credit = {"account": EXPENSE_ACCOUNT}, {"account": PAYABLE_ACCOUNT}
		company = frappe.db.get_value("Cost Center", cost_center, "company")
		if not more:
			debit, credit = credit, debit
		journal_entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": company,
				"posting_date": self.entry_date,
				"accounts": [
					{**debit, "account": account(company, debit["account"]), "cost_center": cost_center, "debit_in_account_currency": amount},
					{**credit, "account": account(company, credit["account"]), "cost_center": cost_center, "credit_in_account_currency": amount},
				],
				"user_remark": _("{0} {1} for {2} under {3}. {4}").format(
					_(self.entry_type), self.name, agreement.doctor, self.agreement, self.remarks or ""
				).strip(),
			}
		)
		# The entry was approved where it needed to be (DOC-22); the journal entry is its posting, not a new decision.
		journal_entry.flags.ignore_permissions = True
		journal_entry.insert()
		journal_entry.submit()
		return journal_entry.name

	def books_cost_center(self):
		"""The library of the edition, else of the agreement's latest edition, else the company's default."""
		edition = self.edition or frappe.db.get_value(
			"Book Edition", {"agreement": self.agreement, "docstatus": 1}, "name", order_by="creation desc"
		)
		cost_center = edition and frappe.db.get_value("Book Edition", edition, "cost_center")
		return cost_center or frappe.get_cached_value("Company", frappe.defaults.get_global_default("company"), "cost_center")

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

	def post_collection(self):
		"""APP-06: Dr the treasury / Cr مستحقات على الأطباء — رسوم المنصة, the doctor as the party: the fees the
		courses posted (platform_fee_posting.py) are paid off."""
		company = frappe.db.get_value("Account", self.treasury, "company")
		doctor = frappe.db.get_value("Doctor Agreement", self.agreement, "doctor")
		journal_entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": company,
				"posting_date": self.entry_date,
				"accounts": [
					{"account": self.treasury, "debit_in_account_currency": flt(self.amount)},
					{
						"account": account(company, RECEIVABLE_ACCOUNT),
						"party_type": "Customer",
						"party": doctor,
						"credit_in_account_currency": flt(self.amount),
					},
				],
				"user_remark": _("Platform fees collected from {0} under {1} ({2}).").format(doctor, self.agreement, self.name),
			}
		)
		journal_entry.insert()
		journal_entry.submit()
		return journal_entry.name

	# The agreement's Balance is worked out from these entries (doctor_agreement.py).
	def on_submit(self):
		update_balance(self.agreement, self)
		self.send_statement()

	def send_statement(self):
		# DOC-23: a settlement by hand (a payout, an approved charge, an adjustment, a collection) sends the doctor
		# his statement. Sales do not: there would be one a copy.
		if self.sales_invoice or self.app_course or self.entry_type == "Accrual":
			return
		from imed_erp.imederp.report.doctor_statement.doctor_statement import send_statement, statement_period

		period = statement_period(self)
		if period:
			send_statement(self.agreement, period, _("{0} {1} of {2}").format(_(self.entry_type), self.name, abs(flt(self.amount))))

	def on_cancel(self):
		# A payout's or a collection's journal entry goes with it; a sale's goes with the sale
		# (doctor_accrual.cancel_accruals). A course's entries are never cancelled (platform_fee_posting.py).
		if (self.entry_type in ("Payout", "Collection") or self.is_entered_by_hand()) and self.journal_entry:
			if frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
				cancel("Journal Entry", self.journal_entry)
		update_balance(self.agreement, self)


UNSOLD = "Unsold Copies Charge"


def lock_agreement(agreement):
	frappe.db.get_value("Doctor Agreement", agreement, "name", for_update=True)


EDITION_COST_FIELDS = ["paper_cost", "ink_cost", "overhead_cost", "pages", "binding_cost"]


def descendants(period):
	"""The rounds and modules under a period, at any depth."""
	found, parents = [], [period]
	while parents:
		children = frappe.get_all("Academic Period", filters={"parent_period": ["in", parents]}, pluck="name")
		found += children
		parents = children
	return found

