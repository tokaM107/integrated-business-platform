# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class ExpenseSettings(Document):
    def validate(self):
        for fieldname in ("reminder_days_before", "overdue_reminder_every_days"):
            if cint(self.get(fieldname)) < 1:
                frappe.throw(
                    _("{0} must be at least 1 day, got {1}.").format(
                        _(self.meta.get_label(fieldname)), self.get(fieldname)
                    )
                )
