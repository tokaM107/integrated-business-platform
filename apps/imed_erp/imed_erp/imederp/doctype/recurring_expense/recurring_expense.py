# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A bill paid every month (EXP-05): rent, electricity, internet... One record per bill and place, kept in a
# list the owner and the accountant edit themselves. Each one:
#   - is offered on the Expense screen, where picking it fills in the business, category and treasury;
#   - reminds the owner and the accountant before its day (expense_reminders.py);
#   - when it has an expected amount, makes a draft Expense with it on its day; someone enters the actual
#     amount, attaches that month's receipt and submits it.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, cint, flt, get_first_day, get_last_day, getdate, today

from imed_erp.imederp.expense_reminders import send_recurring_expense_reminders


class RecurringExpense(Document):
    def validate(self):
        if not 1 <= cint(self.day_of_month) <= 31:
            frappe.throw(_("Day of Month must be between 1 and 31, got {0}.").format(self.day_of_month))
        if not self.next_date or (not self.is_new() and self.has_value_changed("day_of_month")):
            self.next_date = next_due_date(self.day_of_month, today())
        if flt(self.amount) < 0:
            frappe.throw(_("Expected Amount cannot be negative, got {0}.").format(self.amount))
        # An expense that would fail on these fails here instead, while someone is looking at it.
        expense = self.new_expense()
        expense.validate_activity()
        expense.validate_category()
        expense.validate_treasury()
        expense.validate_company()
        # Several places pay the same bill, so the dropdown on Expense names both.
        self.title = f"{self.expense_category} - {frappe.db.get_value('Cost Center', self.activity, 'cost_center_name')}"

    def new_expense(self):
        return frappe.get_doc(
            {
                "doctype": "Expense",
                "posting_date": self.next_date,
                "activity": self.activity,
                "expense_type": "Every Month",
                "expense_category": self.expense_category,
                "amount": self.amount,
                "treasury": self.treasury,
                "description": self.description,
                "recurring_expense": self.name,
            }
        )

    def make_expense(self):
        """Make this month's draft, if the bill has an expected amount, and move on to next month."""
        expense = self.new_expense().insert() if flt(self.amount) else None
        self.db_set("next_date", due_date_in(add_months(self.next_date, 1), self.day_of_month))
        return expense


def due_date_in(month, day_of_month):
    """The day in the month of `month`, or the month's last day when it is shorter."""
    return min(add_days(get_first_day(month), cint(day_of_month) - 1), getdate(get_last_day(month)))


def next_due_date(day_of_month, from_date):
    """The first due date on or after `from_date`."""
    this_month = due_date_in(from_date, day_of_month)
    return this_month if this_month >= getdate(from_date) else due_date_in(add_months(from_date, 1), day_of_month)


def run_daily():
    """Run by the scheduler (hooks.py). One job, so the month's drafts exist before reminders look for them."""
    make_due_expenses()
    send_recurring_expense_reminders()


def make_due_expenses():
    """Also catches up on days the scheduler did not run."""
    for name in frappe.get_all(
        "Recurring Expense", filters={"enabled": 1, "next_date": ["<=", today()]}, pluck="name"
    ):
        recurring = frappe.get_doc("Recurring Expense", name)
        frappe.db.savepoint("recurring_expense")
        try:
            # More than once when the scheduler was off for over a month: one draft per month missed.
            while getdate(recurring.next_date) <= getdate(today()):
                recurring.make_expense()
        except Exception:
            frappe.db.rollback(save_point="recurring_expense")
            # One bad record must not stop the other bills; the error log shows what went wrong.
            frappe.log_error(title=_("Recurring Expense {0} could not make its expense").format(name))
