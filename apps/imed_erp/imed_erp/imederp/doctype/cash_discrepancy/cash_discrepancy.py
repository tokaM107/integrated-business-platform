# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A difference between the cash counted at a close and the cash expected (owner, 21 Oct 2026). Opened by the close
# when it is submitted; investigated and settled by the accountant; the owner sees every one; a branch manager reads
# her own branch's.
#
# Shortage: Pending Investigation -> Responsibility Determined -> Recovery Recommended -> Recovery Approved, or Written
#   Off (the company bears it). Nobody is responsible until the investigation says so: the employees on shift are
#   listed, not charged. Four eyes: the accountant recommends a recovery only once she has named the employee
#   responsible, told the employee and heard them, confirmed the recovery is allowed by the contract and the labour
#   law, and typed each employee's amount (nothing is split by itself); the owner approves it, or returns it. The owner
#   cannot approve while the recovery policy is not approved (Cash Close Settings), nor approve a recovery they
#   recommended themselves. An approved recovery is ready for the payroll review report; the system deducts nothing from
#   a salary (there is no payroll here).
# Surplus: Pending Review -> Explained, only with where the cash came from and its cause (22 Oct 2026). Until then it
#   stays under review, in the open count and in every later weekly review; it is never revenue by itself, and no
#   account is assumed for it. The cause decides the account its adjustment credits:
#     Omitted Customer Payment     the customer's own receivable account (the payment that was not recorded)
#     Money Held for a Customer    a liability account the accountant names (the cash is the customer's)
#     Recording Error              the account the error was made in, named by the accountant
#     Other Identified Adjustment  the account the verified source belongs to, named by the accountant
# Either, once settled: Post Adjustment brings the books to the cash counted, by the accountant only, once: a shortage
#   against فروقات الخزينة (written off, or recovered through payroll), a surplus against its cause's account.
# Withdrawn: its close was reopened.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, today

from imed_erp.imederp.doctype.cash_close_settings.cash_close_settings import OWNER_ROLE, recovery_allowed
from imed_erp.imederp.sales_cancellation import clean_reason

ACCOUNTS_ROLES = ("Accounts Manager", "System Manager")
CASH_DIFFERENCES = "فروقات الخزينة"
OPEN = ("Pending Investigation", "Responsibility Determined", "Recovery Recommended", "Pending Review")
SETTLED = ("Recovery Approved", "Written Off", "Explained")


class CashDiscrepancy(Document):
	def validate(self):
		before = self.get_doc_before_save()
		if before and before.status in SETTLED + ("Withdrawn", "Recovery Recommended"):
			# Settled: what was decided stays as it was decided.
			for field in ("employees", "reason", "investigation_notes", "legal_check", "shift", "surplus_cause", "surplus_customer", "surplus_account"):
				if decided(before, field) != decided(self, field) and not self.flags.by_action:
					frappe.throw(_("{0} is {1}: it can no longer be changed.").format(self.name, _(before.status)))
		users = [row.user for row in self.employees]
		if len(users) != len(set(users)):
			frappe.throw(_("An employee is listed twice."))
		for row in self.employees:
			if flt(row.recovery_amount) < 0:
				frappe.throw(_("A recovery amount cannot be below zero."))
			if flt(row.recovery_amount) and not row.responsible:
				frappe.throw(_("{0} is not found responsible: nothing can be recovered from them.").format(row.user))
		if self.kind == "Surplus" and any(flt(row.recovery_amount) for row in self.employees):
			frappe.throw(_("Nothing is recovered on a surplus."))

	def on_trash(self):
		frappe.throw(_("A cash discrepancy is kept. A reopened close withdraws it."))


def decided(doc, field):
	value = doc.get(field)
	if field == "employees":
		return [(r.user, r.responsible, flt(r.recovery_amount), str(r.notified_on or ""), r.employee_response) for r in value]
	return value


def open_for(close):
	"""The discrepancy of a submitted close; its name."""
	shortage = flt(close.difference) < 0
	doc = frappe.get_doc(
		{
			"doctype": "Cash Discrepancy",
			"treasury_close": close.name,
			"treasury": close.treasury,
			"business": close.business,
			"close_date": close.close_date,
			"shift": close.shift,
			"kind": "Shortage" if shortage else "Surplus",
			"amount": abs(flt(close.difference, 2)),
			"status": "Pending Investigation" if shortage else "Pending Review",
			"reason": close.note,
			"evidence": close.evidence,
			# Who closed the box handled the cash; listed, not found responsible.
			"employees": [{"user": close.counted_by}],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def check_can_withdraw(name):
	status, entry = frappe.db.get_value("Cash Discrepancy", name, ["status", "adjustment_entry"])
	if entry:
		frappe.throw(
			_("{0} is already adjusted in the books ({1}). Cancel the adjustment first.").format(name, entry),
			title=_("Cannot Reopen"),
		)
	if status == "Recovery Approved":
		frappe.throw(
			_("{0} has an approved recovery. Withdraw the recovery first.").format(name), title=_("Cannot Reopen")
		)


def withdraw(name, close):
	doc = frappe.get_doc("Cash Discrepancy", name)
	doc.flags.by_action = True
	doc.status = "Withdrawn"
	doc.payroll_status = None
	doc.add_comment("Info", _("Withdrawn: {0} was reopened.").format(close))
	doc.save(ignore_permissions=True)


def get_for_action(name, kinds, statuses):
	frappe.only_for(ACCOUNTS_ROLES)
	doc = frappe.get_doc("Cash Discrepancy", name)
	doc.check_permission("write")
	if doc.kind not in kinds or doc.status not in statuses:
		frappe.throw(_("{0} is {1} ({2}): this cannot be done to it now.").format(doc.name, _(doc.status), _(doc.kind)))
	doc.flags.by_action = True
	return doc


def mark_reviewed(doc):
	doc.reviewed_by = frappe.session.user
	doc.reviewed_on = now_datetime()


@frappe.whitelist(methods=["POST"])
def determine_responsibility(name):
	"""The investigation is done: who is responsible is recorded."""
	doc = get_for_action(name, ("Shortage",), ("Pending Investigation", "Responsibility Determined"))
	if not clean_reason(doc.investigation_notes):
		frappe.throw(_("Write what the investigation found first."), title=_("Investigation Notes Needed"))
	if not any(row.responsible for row in doc.employees):
		frappe.throw(
			_("Mark who is responsible first. If nobody can be, write the shortage off."), title=_("Nobody Responsible")
		)
	doc.status = "Responsibility Determined"
	mark_reviewed(doc)
	doc.save()
	return doc.status


@frappe.whitelist(methods=["POST"])
def recommend_recovery(name):
	"""The accountant recommends recovering the amounts typed for each responsible employee; the owner decides."""
	doc = get_for_action(name, ("Shortage",), ("Responsibility Determined",))
	responsible = [row for row in doc.employees if row.responsible]
	for row in responsible:
		if not row.notified_on:
			frappe.throw(
				_("{0} has not been told yet. Record the day they were told, and their response.").format(row.user),
				title=_("Employee Not Told"),
			)
	if not doc.legal_check:
		frappe.throw(
			_("Confirm the recovery is allowed by the employment contract and the labour law first."),
			title=_("Not Checked"),
		)
	total = flt(sum(flt(row.recovery_amount) for row in responsible), 2)
	if total <= 0:
		frappe.throw(
			_("Type the amount to recover from each responsible employee. Nothing is split by itself."),
			title=_("No Amounts"),
		)
	if total > flt(doc.amount) + 0.005:
		frappe.throw(_("The recovery, {0}, is more than the shortage, {1}.").format(total, doc.amount))
	doc.status = "Recovery Recommended"
	doc.recovery_total = total
	doc.recommended_by = frappe.session.user
	doc.recommended_on = now_datetime()
	doc.save()
	return doc.status


@frappe.whitelist(methods=["POST"])
def approve_recovery(name):
	"""The owner approves the accountant's recommendation, once the recovery policy is approved."""
	frappe.only_for(OWNER_ROLE)
	doc = get_for_action(name, ("Shortage",), ("Recovery Recommended",))
	if not recovery_allowed():
		frappe.throw(
			_("Recovering shortages from employees is blocked until the recovery policy is approved (Cash Close Settings)."),
			title=_("Recovery Blocked"),
		)
	if doc.recommended_by == frappe.session.user:
		frappe.throw(
			_("You recommended this recovery: another person approves it."), frappe.PermissionError, title=_("Four Eyes")
		)
	doc.status = "Recovery Approved"
	doc.payroll_status = "Ready for Payroll Review"
	doc.approved_by = frappe.session.user
	doc.approved_on = now_datetime()
	doc.save()
	return doc.status


@frappe.whitelist(methods=["POST"])
def return_recommendation(name, reason):
	"""The owner sends the recommendation back to the accountant, with a reason."""
	frappe.only_for(OWNER_ROLE)
	reason = clean_reason(reason)
	if not reason:
		frappe.throw(_("Returning a recommendation needs a reason."), title=_("Reason Needed"))
	doc = get_for_action(name, ("Shortage",), ("Recovery Recommended",))
	doc.status = "Responsibility Determined"
	doc.recovery_total = 0
	doc.recommended_by = None
	doc.recommended_on = None
	doc.add_comment("Info", _("Recommendation returned: {0}").format(reason))
	doc.save()
	return doc.status


@frappe.whitelist(methods=["POST"])
def withdraw_recovery(name, reason):
	"""Take back an approved recovery (before it reaches payroll), back to Responsibility Determined."""
	reason = clean_reason(reason)
	if not reason:
		frappe.throw(_("Withdrawing a recovery needs a reason."), title=_("Reason Needed"))
	doc = get_for_action(name, ("Shortage",), ("Recovery Approved",))
	if doc.adjustment_entry:
		frappe.throw(_("{0} is already adjusted in the books ({1}). Cancel the adjustment first.").format(doc.name, doc.adjustment_entry))
	doc.status = "Responsibility Determined"
	doc.recovery_total = 0
	doc.payroll_status = None
	doc.approved_by = None
	doc.approved_on = None
	doc.add_comment("Info", _("Recovery withdrawn: {0}").format(reason))
	doc.save()
	return doc.status


@frappe.whitelist(methods=["POST"])
def write_off(name, reason):
	"""The company bears the shortage: nobody is charged."""
	reason = clean_reason(reason)
	if not reason:
		frappe.throw(_("Writing a shortage off needs a reason."), title=_("Reason Needed"))
	doc = get_for_action(name, ("Shortage",), ("Pending Investigation", "Responsibility Determined", "Recovery Recommended"))
	doc.reason = reason
	for row in doc.employees:
		row.recovery_amount = 0
	doc.recovery_total = 0
	doc.status = "Written Off"
	mark_reviewed(doc)
	doc.approved_by = frappe.session.user
	doc.approved_on = now_datetime()
	doc.save()
	return doc.status


SURPLUS_CAUSES = ("Omitted Customer Payment", "Money Held for a Customer", "Recording Error", "Other Identified Adjustment")
OMITTED, HELD = SURPLUS_CAUSES[0], SURPLUS_CAUSES[1]


def check_surplus_source(doc, cause, customer, account):
	"""The cause and what it names: a customer for a customer's money, an account for anything else."""
	if cause not in SURPLUS_CAUSES:
		frappe.throw(
			_("Choose the surplus's verified cause. If it is not known yet, leave the surplus under review."), title=_("Cause Needed")
		)
	if cause in (OMITTED, HELD) and not (customer and frappe.db.exists("Customer", customer)):
		frappe.throw(_("Name the customer the cash belongs to."), title=_("Customer Needed"))
	if cause == OMITTED:
		return None
	if not account:
		frappe.throw(_("Name the account the verified source belongs to."), title=_("Account Needed"))
	company = frappe.db.get_value("Account", doc.treasury, "company")
	acc = frappe.db.get_value("Account", account, ["company", "is_group", "account_type", "root_type", "disabled"], as_dict=True)
	if not acc or acc.company != company or acc.is_group or acc.disabled:
		frappe.throw(_("{0} is not an account of {1} that takes entries.").format(account, company))
	if acc.account_type in ("Cash", "Bank"):
		frappe.throw(_("{0} is a treasury: the surplus is already in the cash box.").format(account))
	if cause == HELD and acc.root_type != "Liability":
		frappe.throw(_("Money held for a customer is owed to them: choose a liability account."), title=_("Wrong Account"))
	if acc.account_type in ("Receivable", "Payable") and not customer:
		frappe.throw(_("{0} is kept per customer: name the customer.").format(account), title=_("Customer Needed"))
	return account


@frappe.whitelist(methods=["POST"])
def explain_surplus(name, reason, cause=None, customer=None, account=None):
	reason = clean_reason(reason)
	if not reason:
		frappe.throw(_("Write where the extra cash came from. If it is not known yet, leave the surplus under review."), title=_("Reason Needed"))
	doc = get_for_action(name, ("Surplus",), ("Pending Review",))
	doc.surplus_account = check_surplus_source(doc, cause, customer, account)
	doc.surplus_cause, doc.surplus_customer = cause, customer or None
	doc.reason = reason
	doc.status = "Explained"
	mark_reviewed(doc)
	doc.approved_by = frappe.session.user
	doc.approved_on = now_datetime()
	doc.save()
	return doc.status


@frappe.whitelist(methods=["POST"])
def post_adjustment(name):
	"""Bring the books to the cash counted, against فروقات الخزينة, dated today; once, after the review."""
	doc = get_for_action(name, ("Shortage", "Surplus"), SETTLED)
	frappe.db.get_value("Cash Discrepancy", doc.name, "name", for_update=True)
	if frappe.db.get_value("Cash Discrepancy", doc.name, "adjustment_entry"):
		frappe.throw(_("{0} is already adjusted in the books.").format(doc.name), title=_("Already Adjusted"))
	company = frappe.db.get_value("Account", doc.treasury, "company")
	abbr = frappe.get_cached_value("Company", company, "abbr")
	amount = flt(doc.amount, 2)
	into_box = doc.kind == "Surplus"
	other = {"account": f"{CASH_DIFFERENCES} - {abbr}"}
	if into_box:
		other = surplus_counter_line(doc, company)
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"company": company,
			"posting_date": today(),
			"user_remark": _("Cash {0} of {1} at {2}, {3}").format(
				_(doc.kind).lower(), frappe.format_value(doc.close_date, {"fieldtype": "Date"}), doc.treasury, doc.name
			),
			"accounts": [
				{
					"account": doc.treasury,
					"debit_in_account_currency": amount if into_box else 0,
					"credit_in_account_currency": 0 if into_box else amount,
					"cost_center": doc.business,
				},
				{
					**other,
					"debit_in_account_currency": 0 if into_box else amount,
					"credit_in_account_currency": amount if into_box else 0,
					"cost_center": doc.business,
				},
			],
		}
	)
	entry.flags.cash_adjustment = True
	entry.insert()
	entry.submit()
	doc.adjustment_entry = entry.name
	doc.save()
	return entry.name


def surplus_counter_line(doc, company):
	"""The account a surplus's adjustment credits, from its verified cause; refused when none was given (a surplus
	explained before 22 Oct 2026 is classified first)."""
	if doc.surplus_cause not in SURPLUS_CAUSES:
		frappe.throw(
			_("{0} has no verified cause. Classify it (Explained, with its cause) before adjusting the books.").format(doc.name),
			title=_("Cause Needed"),
		)
	if doc.surplus_cause == OMITTED:
		from erpnext.accounts.party import get_party_account

		return {"account": get_party_account("Customer", doc.surplus_customer, company), "party_type": "Customer", "party": doc.surplus_customer}
	line = {"account": check_surplus_source(doc, doc.surplus_cause, doc.surplus_customer, doc.surplus_account)}
	if frappe.db.get_value("Account", line["account"], "account_type") in ("Receivable", "Payable"):
		line.update(party_type="Customer", party=doc.surplus_customer)
	return line


@frappe.whitelist()
def unresolved_count():
	return frappe.db.count("Cash Discrepancy", {"status": ("in", OPEN)})
