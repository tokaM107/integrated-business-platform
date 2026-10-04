# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet


class ExpenseCategory(NestedSet):
    nsm_parent_field = "parent_expense_category"

    def validate(self):
        self.validate_parent()
        self.validate_expense_account()

    def validate_parent(self):
        if self.parent_expense_category and not frappe.db.get_value(
            "Expense Category", self.parent_expense_category, "is_group"
        ):
            frappe.throw(
                _("{0} is not a group. Only a group category can have categories under it.").format(
                    self.parent_expense_category
                )
            )

    def validate_expense_account(self):
        if not self.expense_account:
            return
        account = frappe.db.get_value("Account", self.expense_account, ["root_type", "is_group"], as_dict=True)
        if not account or account.is_group or account.root_type != "Expense":
            frappe.throw(_("{0} is not an expense account. Choose an account under Expenses.").format(self.expense_account))

    def on_trash(self):
        if frappe.db.exists("Expense", {"expense_category": self.name}):
            frappe.throw(_("{0} has expenses recorded under it and cannot be deleted.").format(self.name))
        super().on_trash()


def get_expense_account(category):
    """The category's expense account, or its nearest parent's when it has none of its own."""
    lft, rgt = frappe.db.get_value("Expense Category", category, ["lft", "rgt"])
    # The category and its parents, nearest first.
    for account in frappe.get_all(
        "Expense Category",
        filters={"lft": ["<=", lft], "rgt": [">=", rgt]},
        order_by="lft desc",
        pluck="expense_account",
    ):
        if account:
            return account
    return None
