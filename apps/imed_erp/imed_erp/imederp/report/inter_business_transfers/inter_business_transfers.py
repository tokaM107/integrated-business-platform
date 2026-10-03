# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters or {})
    return columns, data


def get_columns():
    return [
        {"label": "Transfer", "fieldname": "name", "fieldtype": "Link", "options": "Inter Business Transfer", "width": 150},
        {"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": "Period", "fieldname": "period", "fieldtype": "Link", "options": "Academic Period", "width": 120},
        {"label": "From Business", "fieldname": "from_business", "fieldtype": "Link", "options": "Cost Center", "width": 180},
        {"label": "From Treasury", "fieldname": "from_treasury", "fieldtype": "Link", "options": "Account", "width": 170},
        # Data, not Link: Frappe drops report rows whose Link values fall outside the user's User Permissions,
        # and the receiving business is never the branch manager's own.
        {"label": "To Business", "fieldname": "to_business", "fieldtype": "Data", "width": 180},
        {"label": "To Treasury", "fieldname": "to_treasury", "fieldtype": "Link", "options": "Account", "width": 170},
        {"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 120},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": "Received By", "fieldname": "received_by", "fieldtype": "Link", "options": "User", "width": 160},
        {"label": "Reason", "fieldname": "reason", "fieldtype": "Data", "width": 220},
    ]


def get_data(filters):
    # Submitted transfers only: drafts were never sent and cancelled ones were reversed.
    conditions = {"docstatus": 1}
    for fieldname in ("period", "status"):
        if filters.get(fieldname):
            conditions[fieldname] = filters[fieldname]

    # A business matches when it is on either side of the transfer.
    either_side = {}
    if filters.get("business"):
        either_side = {"from_business": filters["business"], "to_business": filters["business"]}

    # get_list (not get_all) applies User Permissions, so a branch manager sees only their own business.
    # The fields are the column fieldnames, so each value lands under its column.
    return frappe.get_list(
        "Inter Business Transfer",
        filters=conditions,
        or_filters=either_side,
        fields=[column["fieldname"] for column in get_columns()],
        order_by="posting_date desc, name desc",
    )
