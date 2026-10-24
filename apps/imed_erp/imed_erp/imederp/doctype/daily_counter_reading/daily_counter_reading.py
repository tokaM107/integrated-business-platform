# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A library's counters for the day on one screen (PRN-01): the branch, the date and every machine of the branch in
# service. Every counter is read twice a day (22 Oct 2026):
#   morning  each machine's counter is read and typed, and the screen saved: who read them and when is kept, and a
#            branch manager cannot change them afterwards. A morning reading above the machine's last closing is a
#            gap, sheets printed while no reading was taken, and says why; one below it is refused (a counter only
#            goes up: a reset is the accountant's, a Counter Reset reading).
#   evening  each closing is typed and the screen submitted. Printed = evening - morning.
# Submitting it makes one Printer Reading per machine, which keeps each machine's own chain of readings; cancelling it
# cancels them. One per library a day, and a day is not started while an earlier one waits for its evening readings.
#
# Printed is not sold: the screen sets the sheets printed against those the day's sales sold, the paper those sales
# took out of the store, and the sheets recorded as damaged. The counters move no stock: the paper of a sheet leaves
# the store once, with the sale that sold it (paper_use.py); what was printed and not sold shows as waste here, and
# as a shortage at the next stock count.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, now_datetime

from imed_erp.imederp.doctype.book_edition.book_edition import get_paper_cost
from imed_erp.imederp.doctype.printer_reading.printer_reading import ACCOUNTS_ROLES, last_reading
from imed_erp.imederp.doctype.printing_cost_settings.printing_cost_settings import get_rates
from imed_erp.imederp.paper_use import sales_value, sheets_sold
from imed_erp.imederp.doctype.printing_machine.printing_machine import check_library


class DailyCounterReading(Document):
	def validate(self):
		check_library(self.branch)
		self.check_one_a_day()
		self.check_earlier_day_closed()
		if not self.machines:
			self.set_machines()
		self.check_machines()
		self.check_morning_kept()
		for row in self.machines:
			self.check_row(row)
		if not self.opening_recorded_on:
			self.opening_recorded_by, self.opening_recorded_on = frappe.session.user, now_datetime()
		self.set_totals()

	def before_submit(self):
		for row in self.machines:
			if cint(row.closing_reading) <= 0:
				frappe.throw(
					_("Row #{0}: read the counter of {1} at the end of the day: its evening reading is missing.").format(row.idx, row.machine),
					title=_("Evening Reading Missing"),
				)
		self.closing_recorded_by, self.closing_recorded_on = frappe.session.user, now_datetime()

	def check_earlier_day_closed(self):
		"""A missing evening reading is found the next day: an earlier day of the library still waiting for it."""
		open_day = frappe.db.get_value(
			"Daily Counter Reading",
			{"branch": self.branch, "reading_date": ("<", self.reading_date), "docstatus": 0, "name": ("!=", self.name or "")},
			["name", "reading_date"],
			as_dict=True,
		)
		if open_day:
			frappe.throw(
				_("{0} of {1} has no evening readings yet. Record them, or ask the accountant to remove that day, first.").format(
					open_day.name, frappe.format_value(open_day.reading_date, {"fieldtype": "Date"})
				),
				title=_("Evening Reading Missing"),
			)

	def check_morning_kept(self):
		"""The morning readings, once saved, are what the counters showed: only the owner or the accountant corrects them."""
		before = self.get_doc_before_save()
		if not before or set(ACCOUNTS_ROLES) & set(frappe.get_roles()):
			return
		morning = {row.machine: cint(row.opening_reading) for row in before.machines}
		changed = [row.machine for row in self.machines if row.machine in morning and cint(row.opening_reading) != morning[row.machine]]
		if changed:
			frappe.throw(
				_("The morning readings of {0} were recorded at {1}. Only the accountant corrects them.").format(
					", ".join(changed), frappe.format_value(before.opening_recorded_on, {"fieldtype": "Datetime"})
				),
				title=_("Morning Reading Recorded"),
			)

	def set_totals(self):
		# PRN-02: what the counters went up by, against the printing and copying the library sold that day.
		self.total_consumed = sum(cint(row.consumed) for row in self.machines)
		self.total_gap = sum(cint(row.gap) for row in self.machines)
		self.sold_sheets = cint(sheets_sold(self.branch, self.reading_date))
		self.variance = self.total_consumed - self.sold_sheets
		self.paper_issued = cint(paper_issued(self.branch, self.reading_date))
		self.damaged_sheets = cint(damaged_sheets(self.branch, self.reading_date))
		self.set_cost()

	def set_cost(self):
		# PRN-08/09: a printed sheet costs its paper (the store's moving average) + waste + the machine's ink +
		# overheads (Printing Cost Settings). The machines' inks differ, so the day's cost per sheet weighs each
		# machine by what it printed (equally on a day nothing was printed). Fixed once the day is submitted.
		if self.docstatus == 1 and self.cost_per_sheet:
			self.update(margin(self.branch, self.reading_date, self.sold_sheets, self.cost_per_sheet))
			return
		rates = get_rates()
		paper = get_paper_cost(self.branch, rates.waste_per_sheet, as_of=self.reading_date)
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
		if last and getdate(self.reading_date) < getdate(last.reading_date):
			frappe.throw(
				_("Row #{0}: {1} already has a reading on {2}. A new reading cannot be dated before it.").format(
					row.idx, row.machine, frappe.format_value(last.reading_date, {"fieldtype": "Date"})
				)
			)
		row.previous_closing = cint(last.closing_reading) if last else None
		if cint(row.opening_reading) <= 0:
			# QA-30: 0 would count the machine's whole life as one day's sheets.
			if not last:
				frappe.throw(_("Row #{0}: type the opening reading of {1}, its first reading.").format(row.idx, row.machine))
			frappe.throw(
				_("Row #{0}: read the counter of {1} at the start of the day: its morning reading is missing.").format(row.idx, row.machine),
				title=_("Morning Reading Missing"),
			)
		row.gap = 0
		if last:
			row.gap = cint(row.opening_reading) - cint(last.closing_reading)
			if row.gap < 0:
				frappe.throw(
					_("Row #{0}: the morning reading of {1}, {2}, is below its last closing {3}. A counter only goes up: if it was reset, the accountant records the reset.").format(
						row.idx, row.machine, row.opening_reading, last.closing_reading
					),
					title=_("Reading Too Low"),
				)
			if row.gap and not (row.gap_note or "").strip():
				frappe.throw(
					_("Row #{0}: {1} printed {2} sheets between its last closing and this morning. Say why (Why the Gap).").format(
						row.idx, row.machine, row.gap
					),
					title=_("Gap Since Last Closing"),
				)
		if not row.gap:
			row.gap_note = None
		if cint(row.closing_reading) <= 0:
			# The morning's save: the evening reading comes later.
			row.consumed = 0
			return
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
		# The morning reading is read off the counter, not copied: the last closing is shown beside it.
		machines.append(
			{"machine": machine.name, "machine_type": machine.machine_type, "previous_closing": last.closing_reading if last else None}
		)
	return machines


def paper_issued(library, date):
	"""Sheets of A4 paper the library's sales of `date` took out of its store (paper_use.py), from the stock ledger."""
	from imed_erp.imederp.doctype.book_edition.book_edition import LIBRARY_PAPER_STORE, PAPER

	abbr = frappe.get_cached_value("Company", frappe.db.get_value("Cost Center", library, "company"), "abbr")
	store = LIBRARY_PAPER_STORE.get((library or "").removesuffix(f" - {abbr}"))
	if not store:
		return 0
	return -flt(
		frappe.db.sql(
			"""select sum(sle.actual_qty) from `tabStock Ledger Entry` sle
			join `tabStock Entry` se on se.name = sle.voucher_no and sle.voucher_type = 'Stock Entry'
			where sle.item_code = %s and sle.warehouse = %s and sle.posting_date = %s and sle.is_cancelled = 0
			and ifnull(se.sales_invoice_no, '') != ''""",
			(PAPER, f"{store} - {abbr}", date),
		)[0][0]
	)


def damaged_sheets(library, date):
	"""Sheets of A4 paper recorded as damaged in the library on `date` (Damaged Stock Entry)."""
	from imed_erp.imederp.doctype.book_edition.book_edition import PAPER

	return flt(
		frappe.db.sql(
			"""select sum(i.qty) from `tabDamaged Stock Item` i join `tabDamaged Stock Entry` d on d.name = i.parent
			where d.docstatus = 1 and d.branch = %s and d.posting_date = %s and i.item_code = %s""",
			(library, date, PAPER),
		)[0][0]
	)
