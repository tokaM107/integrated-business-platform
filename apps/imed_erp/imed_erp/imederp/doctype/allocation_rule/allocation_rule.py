# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# How a shared cost center's expenses are split between businesses (EXP-03/04). Submitting a rule makes
# an ERPNext Cost Center Allocation with the same shares from Valid From on, and ERPNext splits each
# expense posted on the shared cost center by it.
#
# Shares are fixed percentages agreed with the owner (60% halls / 40% studio to start). Shares by area or by
# revenue were left out on purpose; the notes say what each rule's shares are based on.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, formatdate, getdate


class AllocationRule(Document):
    def validate(self):
        # The same rules ERPNext's Cost Center Allocation enforces, checked here first so the accountant
        # gets a clear message while filling in the rule, not an English one when it is submitted.
        self.validate_duplicates()
        self.validate_businesses()
        self.validate_total()
        self.validate_valid_from()

    def validate_duplicates(self):
        seen = set()
        for row in self.businesses:
            if row.cost_center in seen:
                frappe.throw(
                    _("Row {0}: {1} is already in the rule. Each business can appear only once.").format(
                        row.idx, row.cost_center
                    )
                )
            seen.add(row.cost_center)

    def validate_businesses(self):
        for row in self.businesses:
            if row.cost_center == self.main_cost_center:
                frappe.throw(
                    _("Row {0}: the shared cost center {1} cannot share its own expenses.").format(
                        row.idx, row.cost_center
                    )
                )
            if frappe.db.get_value("Cost Center", row.cost_center, "is_group"):
                frappe.throw(
                    _("Row {0}: {1} is a group. Choose a business under it.").format(row.idx, row.cost_center)
                )

    def validate_total(self):
        total = flt(sum(flt(row.percentage) for row in self.businesses), 2)
        if total != 100:
            frappe.throw(_("The shares must add up to 100%, got {0}%.").format(frappe.format(total)))

    def validate_valid_from(self):
        # A rule never reaches back over expenses already posted, so past months keep their split. Once
        # split, an expense's ledger entries sit on the businesses, not on the shared cost center, so the
        # expenses themselves are checked too (ERPNext looks at the ledger only).
        last_posting_date = max(
            (
                getdate(d)
                for d in (
                    frappe.db.get_value(
                        "GL Entry",
                        {"cost_center": self.main_cost_center, "is_cancelled": 0},
                        "posting_date",
                        order_by="posting_date desc",
                    ),
                    frappe.db.get_value(
                        "Expense",
                        {"activity": self.main_cost_center, "docstatus": 1},
                        "posting_date",
                        order_by="posting_date desc",
                    ),
                )
                if d
            ),
            default=None,
        )
        if last_posting_date and getdate(self.valid_from) <= last_posting_date:
            frappe.throw(
                _("Valid From must be after {0}, the date of the last expense posted on {1}.").format(
                    formatdate(last_posting_date), self.main_cost_center
                )
            )

        # Shares change by a new rule from a later date, so the rules follow one another in time.
        latest = frappe.db.get_value(
            "Allocation Rule",
            {"main_cost_center": self.main_cost_center, "docstatus": 1, "name": ["!=", self.name]},
            ["name", "valid_from"],
            order_by="valid_from desc",
            as_dict=True,
        )
        if latest and getdate(self.valid_from) <= getdate(latest.valid_from):
            frappe.throw(
                _("Valid From must be after {0}, the date rule {1} starts on.").format(
                    formatdate(latest.valid_from), latest.name
                )
            )

    def on_submit(self):
        # ERPNext splits every entry posted on the shared cost center from Valid From on by this record.
        allocation = frappe.get_doc(
            {
                "doctype": "Cost Center Allocation",
                "company": self.company,
                "main_cost_center": self.main_cost_center,
                "valid_from": self.valid_from,
                "allocation_percentages": [
                    {"cost_center": row.cost_center, "percentage": row.percentage} for row in self.businesses
                ],
            }
        )
        # Whoever may submit the rule may make its allocation; the rule is the gate.
        allocation.flags.ignore_permissions = True
        allocation.insert()
        allocation.submit()
        self.db_set("cost_center_allocation", allocation.name)

    def on_cancel(self):
        # Expenses already split keep their split. Those posted from now on follow the previous rule again,
        # or stay on the shared cost center if there is none.
        if (
            self.cost_center_allocation
            and frappe.db.get_value("Cost Center Allocation", self.cost_center_allocation, "docstatus") == 1
        ):
            allocation = frappe.get_doc("Cost Center Allocation", self.cost_center_allocation)
            allocation.flags.ignore_permissions = True
            allocation.cancel()
