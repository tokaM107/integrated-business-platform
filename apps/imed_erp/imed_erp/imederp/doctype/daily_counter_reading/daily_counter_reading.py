# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A library's counters for the day on one screen (PRN-01): the branch, the date and every machine of the branch in
# service, each with its opening (the machine's last closing reading) and the closing typed now, saved once.
# Submitting it makes one Printer Reading per machine, which keeps each machine's own chain of readings (its
# counter only goes up); cancelling it cancels them. One per library a day.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, today

from imed_erp.imederp.doctype.book_edition.book_edition import get_paper_cost
from imed_erp.imederp.doctype.printer_reading.printer_reading import last_reading
from imed_erp.imederp.doctype.printing_cost_settings.printing_cost_settings import get_rates
from imed_erp.imederp.paper_use import sales_value, sheets_sold
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
		self.set_cost()

	def set_cost(self):
		# PRN-08/09: a printed sheet costs its paper (the store's moving average) + waste + the machine's ink +
		# overheads (Printing Cost Settings). The machines' inks differ, so the day's cost per sheet weighs each
		# machine by what it printed (equally on a day nothing was printed). Fixed once the day is submitted.
		if self.docstatus == 1 and self.cost_per_sheet:
			self.update(margin(self.branch, self.reading_date, self.sold_sheets, self.cost_per_sheet))
			return
		rates = get_rates()
		paper = get_paper_cost(self.branch, rates.waste_per_sheet)
		if not paper:
			frappe.msgprint(
				_("{0} has no paper price yet (no A4 paper received in its store), so the cost of a sheet leaves the paper out.").format(self.branch),
				title=_("No Paper Price"),
				indicator="orange",
			)
		for row in self.machines:
			ink = flt(frappe.db.get_value("Printing Machine", row.machine, "ink_per_sheet"))
			row.cost_per_sheet = flt(paper + ink + flt(rates.overheads_per_sheet), 4)
		printed = sum(max(cint(row.consumed), 0) for row in self.machines)
		weights = [(max(cint(row.consumed), 0) if printed else 1, row.cost_per_sheet) for row in self.machines]
		total_weight = sum(w for w, _cost in weights)
		self.cost_per_sheet = flt(sum(w * cost for w, cost in weights) / total_weight, 4) if total_weight else 0
		self.variance_value = flt(self.variance * flt(self.cost_per_sheet), 2)
		self.update(margin(self.branch, self.reading_date, self.sold_sheets, self.cost_per_sheet))

	def check_one_a_day(self):
		# QA-24: the counters are read when they are there to read.
		if getdate(self.reading_date) > getdate(today()):
			frappe.throw(_("A counter reading cannot be dated after today."), title=_("Date in the Future"))
		# QA-26: the library is locked first, so two screens of the same day saved at once wait for each other and
		# the second sees the first.
		frappe.db.get_value("Cost Center", self.branch, "name", for_update=True)
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
		if row.fault and not (row.fault_note or "").strip():
			# PRN-09: a breakdown is followed up, so it says what happened.
			frappe.throw(_("Row #{0}: say what happened to {1}.").format(row.idx, row.machine), title=_("Breakdown"))
		last = last_reading(row.machine)
		if last:
			if getdate(self.reading_date) < getdate(last.reading_date):
				frappe.throw(
					_("Row #{0}: {1} already has a reading on {2}. A new reading cannot be dated before it.").format(
						row.idx, row.machine, frappe.format_value(last.reading_date, {"fieldtype": "Date"})
					)
				)
			row.opening_reading = last.closing_reading
		elif cint(row.opening_reading) <= 0:
			# QA-30: 0 would count the machine's whole life as one day's sheets.
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


def margin(library, date, sold, cost_per_sheet):
	"""PRN-08: what a printed sheet sold for on average that day, against what it cost."""
	value = sales_value(library, date)
	average = flt(value / cint(sold), 4) if cint(sold) else 0
	return {
		"sales_value": flt(value, 2),
		"average_price": average,
		"margin_per_sheet": flt(average - flt(cost_per_sheet), 4) if cint(sold) else 0,
	}


def refresh_sold(library, date):
	"""A sale (or its cancellation) after the day's counters were submitted: they take it in."""
	for name, consumed, cost in frappe.get_all(
		"Daily Counter Reading",
		filters={"branch": library, "reading_date": date, "docstatus": 1},
		fields=["name", "total_consumed", "cost_per_sheet"],
		as_list=True,
	):
		sold = cint(sheets_sold(library, date))
		variance = cint(consumed) - sold
		frappe.db.set_value(
			"Daily Counter Reading",
			name,
			{
				"sold_sheets": sold,
				"variance": variance,
				"variance_value": flt(variance * flt(cost), 2),
				**margin(library, date, sold, cost),
			},
		)


@frappe.whitelist()
def get_machines(branch):
	"""The library's machines in service, each with its opening: its last closing reading, or None for a first."""
	frappe.has_permission("Daily Counter Reading", "create", throw=True)
	# SEC-08: another library's machines and counters are not shown.
	frappe.has_permission("Cost Center", "read", doc=branch, throw=True)
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
