# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The rates printed sheets and books are priced on (owner's decision of 8 Oct 2026): they change several
# times a year, so the owner and the accountant set them here instead of in code. Book Edition takes them.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

RATES = (
	"waste_per_sheet",
	"ink_per_sheet",
	"overheads_per_sheet",
	"profit_per_sheet",
	"binding_per_copy",
	"epson_ink_per_sheet",
	"riso_ink_per_sheet",
)

# The ink a printed sheet takes on each kind of machine (PRN-08): Riso ink costs more.
MACHINE_INK = {"Epson": "epson_ink_per_sheet", "Riso": "riso_ink_per_sheet"}

# What an ink costs and how many sheets it prints, by machine type: the ink per sheet is the one over the other.
# A Riso ink is one colour; an Epson set is 4 colours (owner, 18 Oct 2026).
INK_PACKS = {"Riso": ("riso_ink_price", "riso_sheets_per_ink"), "Epson": ("epson_ink_set_price", "epson_sheets_per_set")}


def get_machine_ink(machine_type):
	"""The ink per sheet of a machine type, from the settings (or the default on the screen)."""
	return get_rates()[MACHINE_INK[machine_type]] if machine_type in MACHINE_INK else 0


class PrintingCostSettings(Document):
    def validate(self):
        for machine_type, (price, sheets) in INK_PACKS.items():
            for fieldname in (price, sheets):
                if flt(self.get(fieldname)) < 0:
                    frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(fieldname))))
            if cint(self.get(sheets)) > 0:
                self.set(MACHINE_INK[machine_type], flt(flt(self.get(price)) / cint(self.get(sheets)), 4))
        for fieldname in RATES:
            if flt(self.get(fieldname)) < 0:
                frappe.throw(
                    _("{0} cannot be negative, got {1}.").format(_(self.meta.get_label(fieldname)), self.get(fieldname))
                )

    def on_update(self):
        # A machine still on its type's rate follows the new one; a rate set on a machine stays.
        before = self.get_doc_before_save()
        for machine_type, fieldname in MACHINE_INK.items():
            old = flt(before.get(fieldname)) if before and before.get(fieldname) is not None else flt(self.meta.get_field(fieldname).default)
            new = flt(self.get(fieldname))
            if old == new:
                continue
            for machine in frappe.get_all(
                "Printing Machine", filters={"machine_type": machine_type, "ink_per_sheet": old}, pluck="name"
            ):
                frappe.db.set_value("Printing Machine", machine, "ink_per_sheet", new)


def get_rates():
    """The current rates; a rate never saved yet falls back to the default on the screen."""
    settings = frappe.get_cached_doc("Printing Cost Settings")
    meta = frappe.get_meta("Printing Cost Settings")
    return frappe._dict(
        {f: flt(settings.get(f) if settings.get(f) is not None else meta.get_field(f).default) for f in RATES}
    )
