# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A library's counters for the day on one screen (PRN-01): the branch, the date and every machine of the branch in
# service, each with its opening (the machine's last closing reading) and the closing typed now, saved once.
# Submitting it makes one Printer Reading per machine, which keeps each machine's own chain of readings (its
# counter only goes up); cancelling it cancels them. One per library a day.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate

from imed_erp.imederp.doctype.printer_reading.printer_reading import last_reading
from imed_erp.imederp.paper_use import sheets_sold
from imed_erp.imederp.doctype.printing_machine.printing_machine import check_library


class DailyCounterReading(Document):
	def validate(self):
		check_library(self.branch)
		self.check_one_a_day()
		if not self.machines:
			self.set_machines()
		self.check_machines()
		for row in self.machines:
			self.check_row(row)
		self.set_totals()

	def set_totals(self):
		# PRN-02: what the counters went up by, against the printing and copying the library sold that day.
		self.total_consumed = sum(cint(row.consumed) for row in self.machines)
		self.sold_sheets = cint(sheets_sold(self.branch, self.reading_date))
		self.variance = self.total_consumed - self.sold_sheets

	def check_one_a_day(self):
		other = frappe.db.exists(
			"Daily Counter Reading",
			{"branch": self.branch, "reading_date": self.reading_date, "docstatus": ["<", 2], "name": ["!=", self.name]},
		)
		if other:
			frappe.throw(
				_("{0} already has its counters for {1}: {2}.").format(
					self.branch, frappe.format_value(self.reading_date, {"fieldtype": "Date"}), other
				),
				title=_("Already Recorded"),
			)

	def set_machines(self):
		for machine in get_machines(self.branch):
			self.append("machines", machine)

	def check_machines(self):
		# Every machine of the library in service, once each; one out of service is marked so on its own screen.
		listed = [row.machine for row in self.machines]
		for machine in {m for m in listed if listed.count(m) > 1}:
			frappe.throw(_("{0} is listed twice.").format(machine))
		expected = frappe.get_all("Printing Machine", filters={"cost_center": self.branch, "disabled": 0}, pluck="name")
		missing = sorted(set(expected) - set(listed))
		if missing:
			frappe.throw(
				_("Read the counter of every machine of {0}: {1} missing. A machine that is not working is marked Out of Service.").format(
					self.branch, ", ".join(missing)
				),
				title=_("Machines Missing"),
			)

	def check_row(self, row):
		machine = frappe.db.get_value("Printing Machine", row.machine, ["cost_center", "disabled"], as_dict=True)
		if not machine or machine.cost_center != self.branch:
			frappe.throw(_("Row #{0}: {1} is not a machine of {2}.").format(row.idx, row.machine, self.branch))
		if machine.disabled:
			frappe.throw(_("Row #{0}: {1} is out of service and takes no counter readings.").format(row.idx, row.machine))
		last = last_reading(row.machine)
		if last:
			if getdate(self.reading_date) < getdate(last.reading_date):
				frappe.throw(
					_("Row #{0}: {1} already has a reading on {2}. A new reading cannot be dated before it.").format(
						row.idx, row.machine, frappe.format_value(last.reading_date, {"fieldtype": "Date"})
					)
				)
			row.opening_reading = last.closing_reading
		elif row.opening_reading in (None, ""):
			frappe.throw(_("Row #{0}: type the opening reading of {1}, its first reading.").format(row.idx, row.machine))
		row.consumed = cint(row.closing_reading) - cint(row.opening_reading)
		if row.consumed < 0:
			frappe.throw(
				_("Row #{0}: the closing reading of {1}, {2}, is below its opening reading {3}. A counter only goes up.").format(
					row.idx, row.machine, row.closing_reading, row.opening_reading
				),
				title=_("Reading Too Low"),
			)

	def on_submit(self):
		for row in self.machines:
			reading = frappe.get_doc(
				{
					"doctype": "Printer Reading",
					"machine": row.machine,
					"reading_date": self.reading_date,
					"opening_reading": row.opening_reading,
					"closing_reading": row.closing_reading,
					"daily_counter_reading": self.name,
				}
			)
			reading.insert()
			reading.submit()
			row.db_set("printer_reading", reading.name)

	def on_cancel(self):
		for row in self.machines:
			if row.printer_reading and frappe.db.get_value("Printer Reading", row.printer_reading, "docstatus") == 1:
				reading = frappe.get_doc("Printer Reading", row.printer_reading)
				reading.flags.from_daily_counter_reading = True
				reading.cancel()


def refresh_sold(library, date):
	"""A sale (or its cancellation) after the day's counters were submitted: they take it in."""
	for name, consumed in frappe.get_all(
		"Daily Counter Reading",
		filters={"branch": library, "reading_date": date, "docstatus": 1},
		fields=["name", "total_consumed"],
		as_list=True,
	):
		sold = cint(sheets_sold(library, date))
		frappe.db.set_value("Daily Counter Reading", name, {"sold_sheets": sold, "variance": cint(consumed) - sold})


@frappe.whitelist()
def get_machines(branch):
	"""The library's machines in service, each with its opening: its last closing reading, or None for a first."""
	frappe.has_permission("Daily Counter Reading", "create", throw=True)
	machines = []
	for machine in frappe.get_all(
		"Printing Machine",
		filters={"cost_center": branch, "disabled": 0},
		fields=["name", "machine_type"],
		order_by="machine_type, name",
	):
		last = last_reading(machine.name)
		machines.append(
			{"machine": machine.name, "machine_type": machine.machine_type, "opening_reading": last.closing_reading if last else None}
		)
	return machines
