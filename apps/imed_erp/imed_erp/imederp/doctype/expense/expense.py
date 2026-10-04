# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from imed_erp.imederp.doctype.expense_category.expense_category import get_expense_account
from imed_erp.imederp.expense_reminders import notify

# A treasury is a cash box or a wallet: a leaf Account of one of these types.
TREASURY_TYPES = ("Cash", "Bank")

EVERY_MONTH = "Every Month"

# Only the owner has it: an expense above the approval threshold is posted once a holder approves it.
APPROVER_ROLE = "Expense Approver"
PENDING, APPROVED, REJECTED = "Pending Approval", "Approved", "Rejected"

# A receipt is a photo or a scan.
RECEIPT_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf")


class Expense(Document):
    def onload(self):
        # The form shows the approval buttons from these.
        self.set_onload("needs_approval", self.needs_approval())
        self.set_onload("is_approver", is_approver())

    def validate(self):
        self.validate_not_rejected()
        self.validate_amount()
        self.validate_activity()
        self.validate_category()
        self.validate_treasury()
        self.validate_company()
        self.validate_recurring_expense()
        self.reset_approval_if_amount_changed()

    def validate_amount(self):
        if flt(self.amount) <= 0:
            frappe.throw(_("Amount must be greater than zero, got {0}.").format(self.amount))

    def validate_activity(self):
        # Expenses are charged to one business; group cost centers cannot hold transactions.
        if frappe.db.get_value("Cost Center", self.activity, "is_group"):
            frappe.throw(_("Cost Center {0} is a group. Choose a business under it.").format(self.activity))

    def validate_category(self):
        if frappe.db.get_value("Expense Category", self.expense_category, "is_group"):
            frappe.throw(
                _("Expense Category {0} is a group. Choose a category under it.").format(self.expense_category)
            )
        self.expense_account = get_expense_account(self.expense_category)
        if not self.expense_account:
            frappe.throw(
                _("Expense Category {0} has no expense account, and neither do its parents.").format(
                    self.expense_category
                )
            )

    def validate_treasury(self):
        account = frappe.db.get_value("Account", self.treasury, ["account_type", "is_group"], as_dict=True)
        if not account or account.is_group or account.account_type not in TREASURY_TYPES:
            frappe.throw(_("{0} is not a treasury. Choose a cash or wallet account.").format(self.treasury))

    def validate_company(self):
        self.company = frappe.db.get_value("Cost Center", self.activity, "company")
        for account in (self.treasury, self.expense_account):
            if frappe.db.get_value("Account", account, "company") != self.company:
                frappe.throw(_("{0} does not belong to {1}, the company of {2}.").format(account, self.company, self.activity))

    def validate_recurring_expense(self):
        if self.expense_type != EVERY_MONTH:
            self.recurring_expense = None
            return
        if self.recurring_expense:
            activity = frappe.db.get_value("Recurring Expense", self.recurring_expense, "activity")
            if activity != self.activity:
                frappe.throw(
                    _("Monthly bill {0} is for {1}, not {2}.").format(self.recurring_expense, activity, self.activity)
                )

    def validate_not_rejected(self):
        # A rejected expense is closed for good; if it is needed after all, a new one is made.
        if self.get_db_value("approval_status") == REJECTED:
            frappe.throw(_("Expense {0} was rejected and cannot be changed. Make a new expense instead.").format(self.name))

    def reset_approval_if_amount_changed(self):
        # The owner approved an amount, not the expense whatever it becomes.
        if self.approval_status in (PENDING, APPROVED) and self.has_value_changed("amount"):
            self.approval_status = None
            self.approved_by = None

    def needs_approval(self):
        threshold = flt(frappe.db.get_single_value("Expense Settings", "approval_threshold"))
        return bool(threshold) and flt(self.amount) > threshold

    def before_submit(self):
        # Checked here, not by a mandatory field, so drafts can be saved before the receipt is at hand,
        # and so it also holds for documents submitted through the API.
        self.validate_receipt()
        self.validate_approved()

    def validate_approved(self):
        if not self.needs_approval() or self.approval_status == APPROVED:
            return
        # The owner's own expenses need no one else's approval.
        if is_approver():
            self.approval_status = APPROVED
            self.approved_by = frappe.session.user
            return
        frappe.throw(
            _("This expense is above the approval threshold of {0}. Request the owner's approval first.").format(
                frappe.format_value(frappe.db.get_single_value("Expense Settings", "approval_threshold"), {"fieldtype": "Currency"})
            ),
            title=_("Approval Needed"),
        )

    @frappe.whitelist()
    def request_approval(self):
        self.check_permission("write")
        if self.docstatus != 0 or self.approval_status in (PENDING, APPROVED, REJECTED):
            frappe.throw(_("Approval can only be requested for a draft that has not been sent yet."))
        if not self.needs_approval():
            frappe.throw(_("This expense is not above the approval threshold. Submit it directly."))
        # The owner decides on the full expense, receipt included.
        self.validate_receipt()
        self.approval_status = PENDING
        self.save()
        notify(
            get_approvers(),
            _("Expense {0} of {1} for {2} ({3}) is waiting for your approval.").format(
                self.name, frappe.format_value(self.amount, {"fieldtype": "Currency"}), self.expense_category, self.activity
            ),
            "Expense",
            self.name,
        )

    @frappe.whitelist()
    def approve(self):
        frappe.only_for(APPROVER_ROLE)
        self.check_pending()
        self.approval_status = APPROVED
        self.approved_by = frappe.session.user
        self.submit()
        self.notify_requester(_("Expense {0} was approved and posted."))

    @frappe.whitelist()
    def reject(self, reason=None):
        frappe.only_for(APPROVER_ROLE)
        self.check_pending()
        # db_set: from now on validate refuses every save.
        self.db_set({"approval_status": REJECTED, "approved_by": frappe.session.user, "rejection_reason": reason})
        self.notify_requester(_("Expense {0} was rejected.") + (f" {reason}" if reason else ""))

    def check_pending(self):
        if self.docstatus != 0 or self.approval_status != PENDING:
            frappe.throw(_("Expense {0} is not waiting for approval.").format(self.name))

    def notify_requester(self, subject):
        notify([self.owner], subject.format(self.name), "Expense", self.name)

    def validate_receipt(self):
        if not self.receipt:
            frappe.throw(_("Receipt attachment is required before submitting this expense."), title=_("Receipt Missing"))
        # The field holds only a URL; it must point at a file that was actually uploaded.
        if not frappe.db.exists("File", {"file_url": self.receipt}):
            frappe.throw(_("Receipt {0} was not found. Attach the receipt again.").format(self.receipt))
        if not self.receipt.lower().endswith(RECEIPT_EXTENSIONS):
            frappe.throw(_("Receipt must be an image or a PDF file, got {0}.").format(self.receipt))

    def on_submit(self):
        # The money leaves the treasury and is charged to the business's expense account.
        journal_entry = frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "voucher_type": "Journal Entry",
                "company": self.company,
                "posting_date": self.posting_date,
                "user_remark": _("Expense {0}: {1}").format(self.name, self.expense_category),
                "accounts": [
                    {"account": self.expense_account, "debit_in_account_currency": self.amount, "cost_center": self.activity},
                    {"account": self.treasury, "credit_in_account_currency": self.amount, "cost_center": self.activity},
                ],
            }
        )
        # Whoever may submit the expense may post its entry; the expense is the gate.
        journal_entry.flags.ignore_permissions = True
        journal_entry.insert()
        journal_entry.submit()
        self.db_set("journal_entry", journal_entry.name)
        self.add_to_monthly_bills()

    def add_to_monthly_bills(self):
        """A monthly expense whose bill was not in the list adds it, so next month it can be picked."""
        if self.expense_type != EVERY_MONTH or self.recurring_expense:
            return
        filters = {"activity": self.activity, "expense_category": self.expense_category}
        bill = frappe.db.get_value("Recurring Expense", filters)
        if not bill:
            bill = frappe.get_doc(
                {
                    "doctype": "Recurring Expense",
                    **filters,
                    "treasury": self.treasury,
                    "day_of_month": getdate(self.posting_date).day,
                }
            )
            # Whoever may submit the expense may add its bill; the expense is the gate.
            bill.flags.ignore_permissions = True
            bill = bill.insert().name
        self.db_set("recurring_expense", bill)

    def on_cancel(self):
        if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
            journal_entry = frappe.get_doc("Journal Entry", self.journal_entry)
            journal_entry.flags.ignore_permissions = True
            journal_entry.flags.from_expense = True
            journal_entry.cancel()


def block_cancel_of_expense_entry(doc, method=None):
    """Journal Entry before_cancel hook: an expense's entry is reversed only by cancelling the expense,
    otherwise the expense would still be counted while its money is back in the treasury."""
    if doc.flags.from_expense:
        return
    expense = frappe.db.get_value("Expense", {"journal_entry": doc.name, "docstatus": 1})
    if expense:
        frappe.throw(_("{0} was posted by Expense {1}. Cancel the expense instead.").format(doc.name, expense))


def is_approver(user=None):
    return APPROVER_ROLE in frappe.get_roles(user)


def get_approvers():
    users = frappe.get_all("Has Role", filters={"role": APPROVER_ROLE, "parenttype": "User"}, pluck="parent")
    # Administrator holds every role but is the developers' account, not a person to ask.
    users = [user for user in users if user != "Administrator"]
    return frappe.get_all(
        "User", filters={"name": ["in", users or [""]], "enabled": 1, "user_type": "System User"}, pluck="name"
    )
