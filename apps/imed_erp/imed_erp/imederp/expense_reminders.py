# Reminders for recurring expenses (EXP-05), run once a day by the scheduler (hooks.py).
#
# A Recurring Expense with an expected amount makes a draft Expense on its day of the month; someone enters
# the actual amount, attaches the receipt and submits it. One without an amount is entered by the accountant
# himself. Two reminders keep them from being forgotten:
#   - upcoming: a set number of days before the next one is due, for every bill;
#   - overdue:  while a generated expense is still a draft after its date, again every few days; one waiting
#               for the owner's approval reminds the owner instead.
# Both numbers come from Expense Settings.
#
# Reminders, like the approval notices on Expense, go through the unified notification service (CORE-10) as
# in-app alerts.

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, fmt_money, formatdate, today

from imed_erp import notification_service

EXPENSE = "Expense"

# The owner and the accountant are the only users with this role.
RECIPIENT_ROLE = "Accounts Manager"


def send_recurring_expense_reminders():
    settings = frappe.get_single("Expense Settings")
    users = get_recipients()
    if not users:
        return
    remind_upcoming(users, cint(settings.reminder_days_before) or 3)
    remind_overdue(users, cint(settings.overdue_reminder_every_days) or 2)
    remind_pending_approvals(cint(settings.overdue_reminder_every_days) or 2)


def get_recipients():
    holders = frappe.get_all("Has Role", filters={"role": RECIPIENT_ROLE, "parenttype": "User"}, pluck="parent")
    # Administrator holds every role but is the developers' account, not a person to remind.
    holders = [user for user in holders if user not in ("Administrator", "Guest")]
    if not holders:
        return []
    return frappe.get_all(
        "User", filters={"name": ["in", holders], "enabled": 1, "user_type": "System User"}, pluck="name"
    )


def remind_upcoming(users, days_before):
    due_date = add_days(today(), days_before)
    for recurring in frappe.get_all(
        "Recurring Expense",
        filters={"enabled": 1, "next_date": due_date},
        fields=["name", "expense_category", "activity", "amount"],
    ):
        if recurring.amount:
            subject = _("Recurring expense {0} ({1}) is due on {2}, expected {3}.").format(
                recurring.expense_category, recurring.activity, formatdate(due_date), fmt_money(recurring.amount)
            )
        else:
            subject = _("Recurring expense {0} ({1}) is due on {2}.").format(
                recurring.expense_category, recurring.activity, formatdate(due_date)
            )
        notify(users, subject, "Recurring Expense", recurring.name)


def remind_overdue(users, every_days):
    for expense in frappe.get_all(
        EXPENSE,
        filters={
            "docstatus": 0,
            "recurring_expense": ["is", "set"],
            "posting_date": ["<", today()],
            # Waiting on the owner, or closed by him: not for the accountant to submit.
            "approval_status": ["is", "not set"],
        },
        fields=["name", "expense_category", "activity", "posting_date"],
    ):
        days_late = date_diff(today(), expense.posting_date)
        if days_late % every_days:
            continue
        notify(
            users,
            _(
                "Recurring expense {0} ({1}) was due on {2} and is still a draft, {3} days late. "
                "Enter the actual amount, attach the receipt and submit it."
            ).format(expense.expense_category, expense.activity, formatdate(expense.posting_date), days_late),
            EXPENSE,
            expense.name,
        )


def remind_pending_approvals(every_days):
    """A monthly draft waiting for the owner's approval past its date reminds the owner, not the accountant."""
    from imed_erp.imederp.doctype.expense.expense import PENDING, get_approvers

    approvers = get_approvers()
    if not approvers:
        return
    for expense in frappe.get_all(
        EXPENSE,
        filters={"docstatus": 0, "approval_status": PENDING, "posting_date": ["<", today()]},
        fields=["name", "expense_category", "activity", "amount", "posting_date"],
    ):
        days_late = date_diff(today(), expense.posting_date)
        if days_late % every_days:
            continue
        notify(
            approvers,
            _("Expense {0} of {1} for {2} ({3}) is still waiting for your approval, {4} days after its date.").format(
                expense.name, fmt_money(expense.amount), expense.expense_category, expense.activity, days_late
            ),
            EXPENSE,
            expense.name,
        )


def notify(users, subject, document_type, document_name, event="expense_reminder"):
    # Through the unified notification service (CORE-10). The subject carries the date or the days late,
    # and the service skips a notification a user already has for the same document, so a second run on
    # the same day adds nothing.
    notification_service.notify(event, users, {"subject": subject}, document=(document_type, document_name))
