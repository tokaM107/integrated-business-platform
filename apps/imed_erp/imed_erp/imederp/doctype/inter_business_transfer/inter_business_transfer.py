# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, today

# A treasury is a cash box or a wallet: a leaf Account of one of these types.
TREASURY_TYPES = ("Cash", "Bank")

# Holds the money between the two steps: sent by one business, not yet received by the other.
# A balance sheet account, so a transfer never reaches the P&L of either business.
CURRENT_ACCOUNT = "Inter Business Current Account"

# Only this role may confirm that the money arrived.
RECEIVER_ROLE = "Accounts Manager"


class InterBusinessTransfer(Document):
    def validate(self):
        self.validate_amount()
        self.validate_businesses()
        self.validate_treasuries()
        self.validate_period()

    def validate_amount(self):
        if flt(self.amount) <= 0:
            frappe.throw(f"Amount must be greater than zero, got {self.amount}.")

    def validate_businesses(self):
        if self.from_business == self.to_business:
            frappe.throw("From Business and To Business must be different.")

        # Transfers are posted to one business; group cost centers cannot hold transactions.
        for business in (self.from_business, self.to_business):
            if frappe.db.get_value("Cost Center", business, "is_group"):
                frappe.throw(f"Cost Center {business} is a group. Choose a business under it.")

    def validate_treasuries(self):
        if self.from_treasury == self.to_treasury:
            frappe.throw("From Treasury and To Treasury must be different.")

        for treasury in (self.from_treasury, self.to_treasury):
            account = frappe.db.get_value("Account", treasury, ["account_type", "is_group"], as_dict=True)
            if not account or account.is_group or account.account_type not in TREASURY_TYPES:
                frappe.throw(f"{treasury} is not a treasury. Choose a cash or wallet account.")

    def validate_period(self):
        if frappe.db.get_value("Academic Period", self.period, "is_closed"):
            frappe.throw(f"Period {self.period} is closed. Choose an open period.")

    def on_submit(self):
        # Step 1, the sender hands the money over: it leaves the sending treasury and waits in the current account.
        entry = self.make_journal_entry(
            debit=self.get_current_account(),
            credit=self.from_treasury,
            cost_center=self.from_business,
            posting_date=self.posting_date,
            remark=f"Inter Business Transfer {self.name}: sent from {self.from_business} to {self.to_business}",
        )
        self.db_set({"send_journal_entry": entry, "status": "Sent"})

    @frappe.whitelist()
    def confirm_receipt(self):
        # Step 2, the receiver confirms: the money leaves the current account and enters the receiving treasury.
        if RECEIVER_ROLE not in frappe.get_roles():
            frappe.throw(f"Only a user with the {RECEIVER_ROLE} role can confirm receipt.", frappe.PermissionError)
        if self.docstatus != 1 or self.status != "Sent":
            frappe.throw(f"{self.name} is {self.status}. Only a Sent transfer can be received.")

        entry = self.make_journal_entry(
            debit=self.to_treasury,
            credit=self.get_current_account(),
            cost_center=self.to_business,
            posting_date=today(),
            remark=f"Inter Business Transfer {self.name}: received by {self.to_business} from {self.from_business}",
        )
        self.db_set(
            {
                "receipt_journal_entry": entry,
                "status": "Received",
                "received_by": frappe.session.user,
                "received_on": now_datetime(),
            }
        )

    def on_cancel(self):
        for entry in (self.receipt_journal_entry, self.send_journal_entry):
            if entry and frappe.db.get_value("Journal Entry", entry, "docstatus") == 1:
                journal_entry = frappe.get_doc("Journal Entry", entry)
                journal_entry.flags.ignore_permissions = True
                journal_entry.cancel()
        self.db_set("status", "Cancelled")

    def get_company(self):
        return frappe.db.get_value("Account", self.from_treasury, "company")

    def get_current_account(self):
        company = self.get_company()
        account = frappe.db.get_value("Account", {"account_name": CURRENT_ACCOUNT, "company": company})
        if not account:
            frappe.throw(f"Account '{CURRENT_ACCOUNT}' does not exist for {company}. Run setup_core.py first.")
        return account

    def make_journal_entry(self, debit, credit, cost_center, posting_date, remark):
        journal_entry = frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "voucher_type": "Journal Entry",
                "company": self.get_company(),
                "posting_date": posting_date,
                "user_remark": remark,
                "accounts": [
                    {"account": debit, "debit_in_account_currency": self.amount, "cost_center": cost_center},
                    {"account": credit, "credit_in_account_currency": self.amount, "cost_center": cost_center},
                ],
            }
        )
        # Whoever may submit or receive the transfer may post its entry; the transfer is the gate.
        journal_entry.flags.ignore_permissions = True
        journal_entry.flags.from_inter_business_transfer = True
        journal_entry.insert()
        journal_entry.submit()
        return journal_entry.name


def block_manual_current_account(doc, method=None):
    """Journal Entry validate hook: the current account moves only through an Inter Business Transfer."""
    if doc.flags.from_inter_business_transfer:
        return

    for row in doc.accounts:
        if frappe.db.get_value("Account", row.account, "account_name") == CURRENT_ACCOUNT:
            frappe.throw(
                f"Row {row.idx}: {row.account} cannot be used in a manual entry. "
                "Create an Inter Business Transfer instead."
            )
