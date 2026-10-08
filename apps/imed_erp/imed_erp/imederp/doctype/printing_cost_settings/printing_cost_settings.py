# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The rates printed sheets and books are priced on (owner's decision of 8 Oct 2026): they change several
# times a year, so the owner and the accountant set them here instead of in code. Book Edition takes them.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

RATES = ("waste_per_sheet", "ink_per_sheet", "overheads_per_sheet", "profit_per_sheet", "binding_per_copy")


class PrintingCostSettings(Document):
    def validate(self):
        for fieldname in RATES:
            if flt(self.get(fieldname)) < 0:
                frappe.throw(
                    _("{0} cannot be negative, got {1}.").format(_(self.meta.get_label(fieldname)), self.get(fieldname))
                )


def get_rates():
    """The current rates; a rate never saved yet falls back to the default on the screen."""
    settings = frappe.get_cached_doc("Printing Cost Settings")
    meta = frappe.get_meta("Printing Cost Settings")
    return frappe._dict(
        {f: flt(settings.get(f) if settings.get(f) is not None else meta.get_field(f).default) for f in RATES}
    )
