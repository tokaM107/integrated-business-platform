# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from imed_erp.imederp.doctype.expense_category.expense_category import get_expense_account

# A treasury is a cash box or a wallet: a leaf Account of one of these types.
TREASURY_TYPES = ("Cash", "Bank")

# A receipt is a photo or a scan.
RECEIPT_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf")


class Expense(Document):
    def validate(self):
        self.validate_amount()
        self.validate_activity()
        self.validate_category()
        self.validate_treasury()
        self.validate_company()

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

    def before_submit(self):
        # Checked here, not by a mandatory field, so drafts can be saved before the receipt is at hand,
        # and so it also holds for documents submitted through the API.
        self.validate_receipt()

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

    def on_cancel(self):
        if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
            journal_entry = frappe.get_doc("Journal Entry", self.journal_entry)
            journal_entry.flags.ignore_permissions = True
            journal_entry.cancel()
