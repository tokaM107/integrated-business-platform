# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The daily close of a branch's cash box (ACC-03; owner, 21 Oct 2026). The branch manager counts the cash at the end
# of the day and submits the close; the accountant does not approve each day but reviews the week (Weekly Cash
# Reconciliation).
#
#   Opening   = the cash counted at the box's last close (the ledger's balance before the day, for its first close)
#   Inflows   = collections and transfers in, since the last close
#   Outflows  = expenses and payouts, transfers out, cash handed over to the owner or the accountant (Cash Handover,
#               pending or confirmed: the cash left the box that day), refunds and other payments, since the last close
#   Expected  = Opening + Inflows - Outflows
#   Variance  = Counted - Expected (below zero: a shortage; above: a surplus)
#
# The movements are the box's ledger lines dated after its last close up to the close's date. A book adjustment of
# an earlier difference (Cash Discrepancy, Post Adjustment) is left out: the opening already is the cash counted.
#
# The close posts nothing and changes no ledger line. A difference opens a Cash Discrepancy, which the accountant
# investigates; nothing is charged to anybody and nothing reaches revenue by itself.
#
# Once a day per cash box, in order: a close is not made for a day before the box's last close. Reopening (cancelling
# with a reason, then amending) is for the owner and the accountant only (reopen below); the original stays,
# cancelled, with its figures; later closes of the box and any reviewed week holding it are marked for review.
# A cash entry dated into a closed day is refused to a branch manager; the accountant's is accepted and marks the
# closes it changes for review (check_closed_days).

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, now_datetime

from imed_erp.imederp.branches import check_has_branch
from imed_erp.imederp.sales_cancellation import clean_reason
from imed_erp.imederp.treasuries import check_treasury

CASH = "Cash"
REOPEN_ROLES = ("Accounts Manager", "System Manager")
MAX_REASON_LENGTH = 500


class TreasuryClose(Document):
	def validate(self):
		self.check_treasury()
		self.check_once_a_day()
		self.check_in_order()
		if flt(self.counted) < 0:
			frappe.throw(_("The cash counted cannot be below zero."))
		if self.is_new() or not self.counted_by:
			self.counted_by = frappe.session.user
		self.set_figures()

	def before_submit(self):
		# Entries may have been posted since it was saved: the books as they are when it is submitted.
		self.check_once_a_day()
		self.check_in_order()
		self.set_figures()
		self.counted_by = frappe.session.user
		self.closed_on = now_datetime()

	def on_submit(self):
		if abs(flt(self.difference)) >= 0.005:
			from imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy import open_for

			self.db_set("cash_discrepancy", open_for(self))

	def before_cancel(self):
		# Cancelling a close is reopening it: the owner or the accountant, with a reason (reopen below).
		frappe.only_for(REOPEN_ROLES)
		if not clean_reason(self.reopen_reason):
			frappe.throw(_("Reopening a close needs a reason."), title=_("Reason Needed"))
		if self.cash_discrepancy:
			from imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy import check_can_withdraw

			check_can_withdraw(self.cash_discrepancy)

	def on_cancel(self):
		if self.cash_discrepancy:
			from imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy import withdraw

			withdraw(self.cash_discrepancy, self.name)
		mark_for_review(
			self.treasury,
			self.close_date,
			_("{0} of {1} was reopened by {2}: {3}").format(
				self.name, frappe.format_value(self.close_date, {"fieldtype": "Date"}), self.reopened_by, self.reopen_reason
			),
			skip=self.name,
		)

	def check_treasury(self):
		account = frappe.db.get_value("Account", self.treasury, ["account_type", "is_group"], as_dict=True)
		if not account or account.is_group or account.account_type != CASH:
			frappe.throw(_("{0} is not a cash box. Choose your branch's cash box.").format(self.treasury), title=_("Wrong Treasury"))
		if frappe.db.get_value("Cost Center", self.business, "is_group"):
			frappe.throw(_("Cost Center {0} is a group. Choose a business under it.").format(self.business))
		allowed = frappe.get_all(
			"User Permission", filters={"user": frappe.session.user, "allow": "Cost Center"}, pluck="for_value"
		)
		check_has_branch(allowed)
		# A branch manager closes only her own business's cash box (treasuries.py); the business is checked against
		# her branches by its permissions.
		check_treasury(self.business, self.treasury)

	def check_once_a_day(self):
		# Locked first, so two people closing the same box at once wait for each other; then read with a locking read,
		# which sees what the other committed (a plain read would see this transaction's older snapshot).
		frappe.db.get_value("Account", self.treasury, "name", for_update=True)
		other = frappe.db.get_value(
			"Treasury Close",
			{"treasury": self.treasury, "close_date": self.close_date, "docstatus": ("<", 2), "name": ("!=", self.name or "")},
			"name",
			for_update=True,
		)
		if other:
			frappe.throw(
				_("{0} is already closed for {1}: {2}.").format(
					self.treasury, frappe.format_value(self.close_date, {"fieldtype": "Date"}), other
				),
				title=_("Already Closed"),
			)

	def check_in_order(self):
		# A reopened close is amended in its place; any other close comes after the box's last one.
		if self.amended_from:
			return
		later = frappe.db.get_value(
			"Treasury Close",
			{"treasury": self.treasury, "close_date": (">", self.close_date), "docstatus": 1},
			["name", "close_date"],
			as_dict=True,
			order_by="close_date desc",
			for_update=True,
		)
		if later:
			frappe.throw(
				_("{0} was already closed later, on {1} ({2}). A day before it can be closed only by reopening.").format(
					self.treasury, frappe.format_value(later.close_date, {"fieldtype": "Date"}), later.name
				),
				title=_("Already Closed"),
			)

	def set_figures(self):
		last = last_close(self.treasury, self.close_date)
		self.last_close = last.name if last else None
		start = add_days(last.close_date, 1) if last else self.close_date
		figures = movements(self.treasury, start, self.close_date)
		self.opening = flt(last.counted, 2) if last else balance_before(self.treasury, self.close_date)
		self.collections = figures.collections
		self.transfers_in = figures.transfers_in
		self.expenses_and_payouts = figures.expenses_and_payouts
		self.transfers_out = figures.transfers_out
		self.other_out = figures.other_out
		self.handed_over = figures.handed_over
		self.money_in = flt(self.collections + self.transfers_in, 2)
		self.money_out = flt(self.expenses_and_payouts + self.transfers_out + self.handed_over + self.other_out, 2)
		self.expected = flt(self.opening + self.money_in - self.money_out, 2)
		self.difference = flt(flt(self.counted) - self.expected, 2)
		self.book_balance = balance_before(self.treasury, add_days(self.close_date, 1))


def last_close(treasury, before):
	return frappe.db.get_value(
		"Treasury Close",
		{"treasury": treasury, "close_date": ("<", before), "docstatus": 1},
		["name", "close_date", "counted"],
		as_dict=True,
		order_by="close_date desc",
	)


def balance_before(treasury, date):
	return flt(
		frappe.db.sql(
			"select sum(debit - credit) from `tabGL Entry` where account = %s and is_cancelled = 0 and posting_date < %s",
			(treasury, date),
		)[0][0],
		2,
	)


def movements(treasury, start, end):
	"""The box's money in and out from `start` to `end`, by kind, from the ledger."""
	transfers = set(
		frappe.get_all("Inter Business Transfer", filters={"docstatus": 1}, pluck="send_journal_entry")
		+ frappe.get_all("Inter Business Transfer", filters={"docstatus": 1}, pluck="receipt_journal_entry")
	)
	spending = set(
		frappe.get_all("Expense", filters={"journal_entry": ("is", "set")}, pluck="journal_entry")
		+ frappe.get_all("Doctor Ledger Entry", filters={"entry_type": "Payout", "journal_entry": ("is", "set")}, pluck="journal_entry")
	)
	adjustments = set(frappe.get_all("Cash Discrepancy", filters={"adjustment_entry": ("is", "set")}, pluck="adjustment_entry"))
	# A hand-over counts on its day, from the hand-over itself, pending or confirmed; its entry is left out here.
	handovers = frappe.get_all(
		"Cash Handover",
		filters={"treasury": treasury, "docstatus": 1, "handover_date": ("between", (start, end))},
		fields=["amount", "journal_entry"],
	)
	adjustments |= set(frappe.get_all("Cash Handover", filters={"treasury": treasury, "journal_entry": ("is", "set")}, pluck="journal_entry"))
	figures = frappe._dict(collections=0, transfers_in=0, expenses_and_payouts=0, transfers_out=0, other_out=0)
	figures.handed_over = sum(flt(h.amount) for h in handovers)
	for row in frappe.db.sql(
		"""select voucher_type, voucher_no, sum(debit) as debit, sum(credit) as credit from `tabGL Entry`
		where account = %s and is_cancelled = 0 and posting_date between %s and %s
		group by voucher_type, voucher_no""",
		(treasury, start, end),
		as_dict=True,
	):
		journal = row.voucher_type == "Journal Entry"
		if journal and row.voucher_no in adjustments:
			continue
		if journal and row.voucher_no in transfers:
			figures.transfers_in += flt(row.debit)
			figures.transfers_out += flt(row.credit)
		elif journal and row.voucher_no in spending:
			figures.expenses_and_payouts += flt(row.credit) - flt(row.debit)
		else:
			figures.collections += flt(row.debit)
			figures.other_out += flt(row.credit)
	return frappe._dict({key: flt(value, 2) for key, value in figures.items()})


def mark_for_review(treasury, from_date, note, skip=None):
	"""Later closes of the box, and reviewed weeks holding the day, are flagged: their figures may have changed."""
	for name in frappe.get_all(
		"Treasury Close",
		filters={"treasury": treasury, "close_date": (">=", from_date), "docstatus": 1, "name": ("!=", skip or "")},
		pluck="name",
	):
		frappe.db.set_value("Treasury Close", name, {"needs_review": 1, "review_note": note})
	from imed_erp.imederp.doctype.weekly_cash_reconciliation.weekly_cash_reconciliation import mark_weeks_for_review

	mark_weeks_for_review(treasury, from_date, note)


@frappe.whitelist(methods=["POST"])
def reopen(name, reason):
	"""Reopen a submitted close: the owner or the accountant, with a reason. The close is cancelled (kept, with its
	figures and who reopened it and why) and a new draft amends it; returns the draft's name."""
	frappe.only_for(REOPEN_ROLES)
	reason = clean_reason(reason)
	if not reason:
		frappe.throw(_("Reopening a close needs a reason."), title=_("Reason Needed"))
	if len(reason) > MAX_REASON_LENGTH:
		frappe.throw(_("The reason is too long: at most {0} characters.").format(MAX_REASON_LENGTH))
	close = frappe.get_doc("Treasury Close", name)
	close.check_permission("cancel")
	if close.docstatus != 1:
		frappe.throw(_("Only a submitted close can be reopened."))
	close.reopen_reason = reason
	close.reopened_by = frappe.session.user
	close.reopened_on = now_datetime()
	# The weekly reviews holding it link to it; they are marked for review instead (on_cancel).
	close.flags.ignore_links = True
	close.cancel()
	draft = frappe.copy_doc(close, ignore_no_copy=False)
	draft.docstatus = 0
	draft.amended_from = close.name
	draft.insert()
	return draft.name


def check_closed_days(doc, method=None):
	"""on_submit / on_cancel of every document (hooks.py): a cash entry dated on or before a box's last close changes a
	closed day. Refused to a branch manager; the accountant's is accepted, and the closes it changes are marked."""
	# A confirmed hand-over's entry: its day's close already counted it as handed over.
	if doc.doctype == "Treasury Close" or doc.flags.cash_adjustment or doc.flags.from_cash_handover:
		return
	if doc.docstatus == 2:
		rows = doc.flags.cash_moved or []
	else:
		from imed_erp.imederp.cash_balance import moved_by

		rows = moved_by(doc)
	for account, moved, first_date in rows:
		if not moved or frappe.db.get_value("Account", account, "account_type") != CASH:
			continue
		closed = frappe.db.get_value(
			"Treasury Close",
			{"treasury": account, "close_date": (">=", first_date), "docstatus": 1},
			"name",
			order_by="close_date asc",
		)
		if not closed:
			continue
		if not set(REOPEN_ROLES) & set(frappe.get_roles()):
			frappe.throw(
				_("{0} is already closed for {1} ({2}). Date the entry today, or ask the accountant.").format(
					account, frappe.format_value(first_date, {"fieldtype": "Date"}), closed
				),
				title=_("Day Already Closed"),
			)
		mark_for_review(
			account,
			first_date,
			_("{0} {1} was entered by {2} on a closed day, {3}.").format(
				_(doc.doctype), doc.name, frappe.session.user, frappe.format_value(first_date, {"fieldtype": "Date"})
			),
		)
