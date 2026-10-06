# Reminders for recurring expenses (EXP-05), run once a day by the scheduler (hooks.py).
#
# A Recurring Expense with an expected amount makes a draft Expense on its day of the month; someone enters
# the actual amount, attaches the receipt and submits it. One without an amount is entered by the accountant
# himself. Two reminders keep them from being forgotten:
#   - upcoming: a set number of days before the next one is due, for every bill;
#   - overdue:  while a generated expense is still a draft after its date, again every few days.
# Both numbers come from Expense Settings.
#
# Reminders are in-app notifications of type "Alert", which never send an email.

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.utils import add_days, cint, date_diff, fmt_money, formatdate, today

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


def notify(users, subject, document_type, document_name):
    enqueue_create_notification(
        users,
        {
            "type": "Alert",
            "subject": subject,
            "document_type": document_type,
            "document_name": document_name,
        },
        # The subject carries the date or the days late, so a second run on the same day adds nothing.
        dedupe_on=["document_type", "document_name", "subject"],
    )
