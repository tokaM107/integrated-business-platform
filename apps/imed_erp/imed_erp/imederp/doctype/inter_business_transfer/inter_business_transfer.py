# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

# A treasury is a cash box or a wallet: a leaf Account of one of these types.
TREASURY_TYPES = ("Cash", "Bank")


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
