import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_datetime, getdate

from imed_erp.imederp.doctype.printing_machine.printing_machine import check_library

# A machine's counter only goes up: each reading starts where the machine's last one ended (PRN-01, PRN-02).


class PrinterReading(Document):
    def validate(self):
        machine = frappe.db.get_value("Printing Machine", self.machine, ["cost_center", "disabled"], as_dict=True)
        if machine.disabled:
            frappe.throw(_("{0} is out of service and takes no counter readings.").format(self.machine))
        # The library is the machine's, never typed.
        self.branch = machine.cost_center
        check_library(self.branch)
        self.set_opening()
        self.consumed = cint(self.closing_reading) - cint(self.opening_reading)
        if self.consumed < 0:
            frappe.throw(
                _("The closing reading {0} is below the opening reading {1}. A counter only goes up.").format(
                    self.closing_reading, self.opening_reading
                ),
                title=_("Reading Too Low"),
            )
        self.variance = self.consumed - cint(self.sold_sheets)

    def set_opening(self):
        # The machine's last submitted reading gives the opening: read again on submit, in case another reading
        # of the same machine was submitted in between.
        last = last_reading(self.machine, exclude=self.name)
        if not last:
            return  # The machine's first reading: the opening is typed.
        if getdate(self.reading_date) < getdate(last.reading_date):
            frappe.throw(
                _("{0} already has a reading on {1}. A new reading cannot be dated before it.").format(
                    self.machine, frappe.format_value(last.reading_date, {"fieldtype": "Date"})
                )
            )
        self.opening_reading = last.closing_reading

    def before_cancel(self):
        # Recorded on the day's screen: cancelled with it, so the screen and its readings agree.
        if self.daily_counter_reading and not self.flags.from_daily_counter_reading:
            if frappe.db.get_value("Daily Counter Reading", self.daily_counter_reading, "docstatus") == 1:
                frappe.throw(
                    _("{0} was recorded on {1}. Cancel that instead.").format(self.name, self.daily_counter_reading),
                    title=_("Recorded on the Day's Screen"),
                )
        # Only the machine's latest reading is taken back, so the next one still starts where the last one ended.
        last = last_reading(self.machine, exclude=self.name)
        if last and (getdate(last.reading_date), get_datetime(last.creation)) > (
            getdate(self.reading_date),
            get_datetime(self.creation),
        ):
            frappe.throw(
                _("{0} has a later reading, {1}. Cancel that one first.").format(self.machine, last.name),
                title=_("Not the Latest Reading"),
            )


def last_reading(machine, exclude=None):
    """The machine's latest submitted reading (name, date, closing reading, creation), or None."""
    filters = {"machine": machine, "docstatus": 1}
    if exclude:
        filters["name"] = ["!=", exclude]
    readings = frappe.get_all(
        "Printer Reading",
        filters=filters,
        fields=["name", "reading_date", "closing_reading", "creation"],
        order_by="reading_date desc, creation desc",
        limit=1,
    )
    return readings[0] if readings else None


@frappe.whitelist()
def get_opening(machine):
    """For the form: the machine's last closing reading, or None for its first reading."""
    frappe.has_permission("Printer Reading", "create", throw=True)
    last = last_reading(machine)
    return last.closing_reading if last else None
