# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate

# "Group Totals By" option -> the columns the totals are grouped on, in order.
GROUPINGS = {
    "Expense Category": ["expense_category"],
    "Activity": ["activity"],
    "Month": ["month"],
    "Activity and Expense Category": ["activity", "expense_category"],
    "Month, Activity and Expense Category": ["month", "activity", "expense_category"],
}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    expenses = get_expenses(filters)

    group_by = GROUPINGS.get(filters.get("group_by"))
    if not group_by:
        return get_detail_columns(), expenses

    data = group_expenses(expenses, group_by)
    return get_group_columns(group_by), data, None, get_chart(data, group_by)


def get_detail_columns():
    return [
        {"label": _("Expense No."), "fieldname": "name", "fieldtype": "Link", "options": "Expense", "width": 150},
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": _("Expense Category"), "fieldname": "expense_category", "fieldtype": "Link", "options": "Expense Category", "width": 170},
        {"label": _("Activity"), "fieldname": "activity", "fieldtype": "Link", "options": "Cost Center", "width": 180},
        {"label": _("Expense Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
        {"label": _("Cash/Bank Account"), "fieldname": "treasury", "fieldtype": "Link", "options": "Account", "width": 170},
        {"label": _("Expense Account"), "fieldname": "expense_account", "fieldtype": "Link", "options": "Account", "width": 170},
        {"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 220},
    ]


def get_group_columns(group_by):
    group_columns = {
        "month": {"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 100},
        "activity": {"label": _("Activity"), "fieldname": "activity", "fieldtype": "Link", "options": "Cost Center", "width": 200},
        "expense_category": {"label": _("Expense Category"), "fieldname": "expense_category", "fieldtype": "Link", "options": "Expense Category", "width": 200},
    }
    return [
        *(group_columns[fieldname] for fieldname in group_by),
        {"label": _("Number of Expenses"), "fieldname": "count", "fieldtype": "Int", "width": 140},
        {"label": _("Total Expenses"), "fieldname": "amount", "fieldtype": "Currency", "width": 140},
    ]


def with_descendants(doctype, name):
    # A group (an activity group or a category group) stands for everything under it.
    return [name, *frappe.db.get_descendants(doctype, name)]


def get_expenses(filters):
    # Submitted expenses only: drafts were never paid and cancelled ones were reversed.
    conditions = {"docstatus": 1}
    if filters.get("from_date") and filters.get("to_date"):
        conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]
    elif filters.get("from_date"):
        conditions["posting_date"] = [">=", filters.from_date]
    elif filters.get("to_date"):
        conditions["posting_date"] = ["<=", filters.to_date]
    for fieldname in ("company", "supplier", "treasury"):
        if filters.get(fieldname):
            conditions[fieldname] = filters[fieldname]
    if filters.get("activity"):
        conditions["activity"] = ["in", with_descendants("Cost Center", filters.activity)]
    if filters.get("expense_category"):
        conditions["expense_category"] = ["in", with_descendants("Expense Category", filters.expense_category)]

    # get_list (not get_all) applies User Permissions, so a branch manager sees only their own business.
    # The fields are the column fieldnames, so each value lands under its column.
    return frappe.get_list(
        "Expense",
        filters=conditions,
        fields=[column["fieldname"] for column in get_detail_columns()],
        order_by="posting_date desc, name desc",
    )


def group_expenses(expenses, group_by):
    groups = {}
    for expense in expenses:
        expense.month = getdate(expense.posting_date).strftime("%Y-%m")
        key = tuple(expense[fieldname] for fieldname in group_by)
        group = groups.setdefault(key, frappe._dict({**dict(zip(group_by, key)), "count": 0, "amount": 0.0}))
        group.count += 1
        group.amount += flt(expense.amount)
    return sorted(groups.values(), key=lambda group: tuple(group[fieldname] or "" for fieldname in group_by))


def get_chart(data, group_by):
    return {
        "data": {
            "labels": [" / ".join(str(row[fieldname]) for fieldname in group_by) for row in data],
            "datasets": [{"name": _("Total Expenses"), "values": [row.amount for row in data]}],
        },
        "type": "bar",
        "fieldtype": "Currency",
    }
