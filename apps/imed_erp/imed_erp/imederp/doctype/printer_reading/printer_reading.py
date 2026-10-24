import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_datetime, getdate

from imed_erp.imederp.doctype.printing_machine.printing_machine import check_library

# A machine's counter only goes up: each reading starts where the machine's last one ended (PRN-01, PRN-02).
# Branch staff read the counters on the day's screen (Daily Counter Reading), which makes these readings; a reading
# on its own, or a counter reset after a repair, is the owner's or the accountant's (QA-20, QA-21).

ACCOUNTS_ROLES = ("Accounts Manager", "System Manager")


class PrinterReading(Document):
    def validate(self):
        machine = frappe.db.get_value("Printing Machine", self.machine, ["cost_center", "disabled"], as_dict=True)
        if machine.disabled:
            frappe.throw(_("{0} is out of service and takes no counter readings.").format(self.machine))
        # The library is the machine's, never typed.
        self.branch = machine.cost_center
        check_library(self.branch)
        self.check_who_reads()
        self.check_one_a_day()
        self.set_opening()
        self.consumed = cint(self.closing_reading) - cint(self.opening_reading)
        if self.consumed < 0:
            frappe.throw(
                _("The closing reading {0} is below the opening reading {1}. A counter only goes up.").format(
                    self.closing_reading, self.opening_reading
                ),
                title=_("Reading Too Low"),
            )
        # Sales do not say which machine printed them, so what was sold is set against the counters of the whole
        # library for the day, on the Daily Counter Reading.
        self.sold_sheets = self.variance = None

    def check_who_reads(self):
        """QA-20: a reading made outside the day's screen moves the machine's counter on without its sheets being in
        any day's waste, so branch staff use the screen; the accounts may correct by hand. QA-21: so may they record a
        counter reset, which no one else can."""
        on_screen = self.daily_counter_reading or self.flags.from_daily_counter_reading
        accounts = set(ACCOUNTS_ROLES) & set(frappe.get_roles())
        if self.counter_reset:
            if not accounts:
                frappe.throw(_("Only the owner or the accountant records a counter reset."), frappe.PermissionError)
            if not (self.reset_note or "").strip():
                frappe.throw(_("Say what happened to the counter."), title=_("Counter Reset"))
        elif not on_screen and not accounts:
            frappe.throw(
                _("Read the counters on the day's screen (Daily Counter Reading), with every machine of the library."),
                frappe.PermissionError,
                title=_("Use the Day's Screen"),
            )

    def check_one_a_day(self):
        # QA-20: one reading a machine a day; a counter reset stands beside the day's reading.
        if self.counter_reset:
            return
        other = frappe.db.exists(
            "Printer Reading",
            {
                "machine": self.machine,
                "reading_date": self.reading_date,
                "docstatus": ("<", 2),
                "counter_reset": 0,
                "name": ("!=", self.name),
            },
        )
        if other:
            frappe.throw(
                _("{0} already has a reading on {1}: {2}.").format(
                    self.machine, frappe.format_value(self.reading_date, {"fieldtype": "Date"}), other
                ),
                title=_("Already Read"),
            )

    def set_opening(self):
        # The machine's last submitted reading gives the opening: read again on submit, in case another reading
        # of the same machine was submitted in between.
        last = last_reading(self.machine, exclude=self.name)
        self.gap = 0
        if not last or self.counter_reset:
            # The machine's first reading, or a counter reset: the opening is typed, the counter as it showed.
            # QA-30: 0 on a first reading would count the machine's whole life as one day's sheets.
            if not last and cint(self.opening_reading) <= 0:
                frappe.throw(
                    _("Type the counter of {0} as it shows before today's printing: its first reading.").format(self.machine),
                    title=_("Opening Needed"),
                )
            if last and getdate(self.reading_date) < getdate(last.reading_date):
                frappe.throw(
                    _("{0} already has a reading on {1}. A new reading cannot be dated before it.").format(
                        self.machine, frappe.format_value(last.reading_date, {"fieldtype": "Date"})
                    )
                )
            return
        if getdate(self.reading_date) < getdate(last.reading_date):
            frappe.throw(
                _("{0} already has a reading on {1}. A new reading cannot be dated before it.").format(
                    self.machine, frappe.format_value(last.reading_date, {"fieldtype": "Date"})
                )
            )
        if self.daily_counter_reading or self.flags.from_daily_counter_reading:
            # Read in the morning on the day's screen (22 Oct 2026): kept as read; above the last closing is a gap.
            self.gap = cint(self.opening_reading) - cint(last.closing_reading)
            if self.gap < 0:
                frappe.throw(
                    _("The opening reading {0} is below the last closing {1}. A counter only goes up.").format(
                        self.opening_reading, last.closing_reading
                    ),
                    title=_("Reading Too Low"),
                )
            return
        self.gap = 0
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
    # SEC-08: another library's machine, and its counter, are not shown.
    frappe.has_permission("Printing Machine", "read", doc=machine, throw=True)
    last = last_reading(machine)
    return last.closing_reading if last else None
