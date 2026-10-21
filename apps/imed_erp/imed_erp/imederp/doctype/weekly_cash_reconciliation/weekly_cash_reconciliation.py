# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The accountant's weekly review of the daily closes (owner, 21 Oct 2026): every submitted close of the week, by
# branch and cash box, with its figures, its difference, the discrepancy's status and who was found responsible; the
# week's shortages and surpluses; the discrepancies still open; the days a box was not closed. Submitting it marks the
# week reviewed. It moves no money: nothing here says the cash went to the accountant.
#
# One per week and business (or per week for every business). A close of the week reopened afterwards marks it
# Needs Review Again (treasury_close.mark_for_review); cancel and amend it to review the week again.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, flt, getdate, now_datetime, today

from imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy import OPEN
from imed_erp.imederp.treasuries import BUSINESS_TREASURY, abbr_of, plain


class WeeklyCashReconciliation(Document):
	def _validate_links(self):
		# Frappe checks the links before any hook: a close reopened since the last save is cancelled, so the closes
		# are read again first, the reopened one replaced by its correction.
		if self.docstatus == 0 and self.week_start:
			self.week_end = add_days(self.week_start, 6)
			self.fill()
		super()._validate_links()

	def validate(self):
		self.week_end = add_days(self.week_start, 6)
		if getdate(self.week_start) > getdate(today()):
			frappe.throw(_("The week has not started yet."))
		if self.business and frappe.db.get_value("Cost Center", self.business, "is_group"):
			frappe.throw(_("Cost Center {0} is a group. Choose a business under it.").format(self.business))
		self.check_once_a_week()
		self.fill()

	def before_submit(self):
		self.check_once_a_week()
		self.fill()
		if self.unresolved and not (self.review_note or "").strip():
			frappe.throw(
				_("{0} discrepancies are still open. Write a note on them before marking the week reviewed.").format(self.unresolved),
				title=_("Note Needed"),
			)
		self.reviewed_by = frappe.session.user
		self.reviewed_on = now_datetime()
		self.needs_review = 0

	def check_once_a_week(self):
		other = frappe.db.exists(
			"Weekly Cash Reconciliation",
			{
				"week_start": self.week_start,
				"business": self.business or ("is", "not set"),
				"docstatus": ("<", 2),
				"name": ("!=", self.name),
			},
		)
		if other:
			frappe.throw(_("This week is already reconciled: {0}.").format(other), title=_("Already Reconciled"))

	def fill(self):
		filters = {"close_date": ("between", (self.week_start, self.week_end)), "docstatus": 1}
		if self.business:
			filters["business"] = self.business
		closes = frappe.get_all(
			"Treasury Close",
			filters=filters,
			fields=[
				"name", "close_date", "treasury", "business", "counted_by", "opening", "collections", "expenses_and_payouts",
				"other_out", "transfers_in", "transfers_out", "expected", "counted", "difference", "cash_discrepancy",
			],
			order_by="business asc, treasury asc, close_date asc",
		)
		self.items = []
		self.total_shortage = self.total_surplus = 0
		self.unresolved = 0
		for close in closes:
			status, responsible = None, None
			if close.cash_discrepancy:
				status = frappe.db.get_value("Cash Discrepancy", close.cash_discrepancy, "status")
				responsible = ", ".join(
					frappe.get_all(
						"Cash Discrepancy Employee",
						filters={"parent": close.cash_discrepancy, "parenttype": "Cash Discrepancy", "responsible": 1},
						pluck="user",
					)
				)
				if status in OPEN:
					self.unresolved += 1
			if flt(close.difference) < 0:
				self.total_shortage += -flt(close.difference)
			else:
				self.total_surplus += flt(close.difference)
			self.append(
				"items",
				{
					"close_date": close.close_date,
					"treasury": close.treasury,
					"business": close.business,
					"treasury_close": close.name,
					"closed_by": close.counted_by,
					"opening": close.opening,
					"collections": close.collections,
					"expenses_and_payouts": flt(close.expenses_and_payouts) + flt(close.other_out),
					"transfers": flt(close.transfers_in) - flt(close.transfers_out),
					"expected": close.expected,
					"counted": close.counted,
					"difference": close.difference,
					"cash_discrepancy": close.cash_discrepancy,
					"discrepancy_status": _(status) if status else None,
					"responsible": responsible,
				},
			)
		self.total_shortage = flt(self.total_shortage, 2)
		self.total_surplus = flt(self.total_surplus, 2)
		self.missing_days = self.days_without_a_close(closes)

	def days_without_a_close(self, closes):
		last = min(getdate(self.week_end), getdate(today()))
		days = [add_days(self.week_start, i) for i in range(date_diff(last, self.week_start) + 1)]
		closed = {(c.treasury, str(c.close_date)) for c in closes}
		lines = []
		for business, box in boxes(self.business):
			missing = [d for d in days if (box, str(d)) not in closed]
			if missing:
				lines.append(
					"{0}: {1}".format(box, ", ".join(frappe.format_value(d, {"fieldtype": "Date"}) for d in missing))
				)
		return "\n".join(lines)


def boxes(business=None):
	"""(business, its cash box) for every business with a cash box, or for one."""
	company = frappe.defaults.get_global_default("company")
	abbr = frappe.get_cached_value("Company", company, "abbr")
	pairs = []
	for name, box in BUSINESS_TREASURY.items():
		full = (f"{name} - {abbr}", f"{box} - {abbr}")
		if business and plain(business, abbr_of(business)) != name:
			continue
		if frappe.db.exists("Account", {"name": full[1], "account_type": "Cash", "disabled": 0}):
			pairs.append(full)
	return pairs


def mark_weeks_for_review(treasury, from_date, note):
	"""Reviewed weeks holding a day of `treasury` from `from_date` on."""
	business = frappe.db.get_value("Treasury Close", {"treasury": treasury}, "business")
	for week in frappe.get_all(
		"Weekly Cash Reconciliation",
		filters={"docstatus": 1, "week_end": (">=", from_date)},
		fields=["name", "business"],
	):
		if week.business and week.business != business:
			continue
		frappe.db.set_value("Weekly Cash Reconciliation", week.name, "needs_review", 1)
		frappe.get_doc("Weekly Cash Reconciliation", week.name).add_comment("Info", note)
