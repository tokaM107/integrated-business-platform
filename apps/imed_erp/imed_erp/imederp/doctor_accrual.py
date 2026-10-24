# The doctor's amount on every copy sold (DOC-07, LIB-05; owner, 10 Oct 2026: on copies sold only).
#
# A sales invoice row that names a Book Edition (imederp/edition_sales.py) sold copies of a doctor's book. When the
# invoice is submitted, each such row adds one Accrual to the doctor's ledger: the row's quantity (in the item's
# stock unit) x the edition's Doctor's Amount per Copy, which the edition kept when it was approved. The point of
# sale makes Sales Invoices too (POS Settings), so its sales are counted the same way.
#
# The row is the key: an entry names its invoice and its invoice line (Doctor Ledger Entry sales_invoice,
# invoice_item), and a line already in the ledger is skipped, so counting an invoice again adds nothing.
# A credit note gives the copies back: its rows add an Adjustment of minus their amount, keyed the same way.
#
# In the accounts, one Journal Entry per invoice for its new rows (the entries name it in journal_entry):
#   Dr حصة الأطباء                  the cost of the doctors' share, on the row's library cost center
#   Cr مستحقات للأطباء — الكتب       owed to the doctors, on the same cost center; which doctor is in the
#                                   entries, since a doctor (a Customer) cannot be a payable party
# A credit note's rows post the other way round.
#
# hooks.py runs on Sales Invoice:
#   on_submit   accrue            the entries and their journal entry
#   on_cancel   cancel_accruals   cancelled with the sale, so the balance and the accounts go back. They are
#                                 cancelled before ERPNext checks for documents still linked to the invoice.
# and before_cancel on Doctor Ledger Entry and Journal Entry (block_cancel_of_accrual): what a sale posted is
# cancelled only by cancelling the sale.
#
# run_daily (scheduler, daily) is the safety net, for sales that reached the books without these hooks (the daily
# import of week B) or failed on the way: every submitted invoice line with an edition and no entry is counted,
# with the same key, and the entries of a cancelled invoice are cancelled. Running it again changes nothing.

import frappe
from frappe import _
from frappe.utils import flt, getdate

from imed_erp.imederp.edition_sales import FIELD

LEDGER = "Doctor Ledger Entry"
EXPENSE_ACCOUNT = "حصة الأطباء"
PAYABLE_ACCOUNT = "مستحقات للأطباء — الكتب"


def accrue(doc, method=None):
	"""Sales Invoice on_submit hook."""
	rows = [row for row in doc.items if row.get(FIELD) and not counted(row)]
	accruals = [accrual for accrual in map(lambda row: make_accrual(doc, row), rows) if accrual]
	if not accruals:
		return
	journal_entry = post(doc, accruals)
	for entry in accruals:
		entry.journal_entry = journal_entry
		# The seller (a branch manager) cannot open the doctors' accounts; the sale posts the entry for them.
		entry.flags.ignore_permissions = True
		entry.insert()
		entry.submit()


def counted(row):
	return frappe.db.exists(LEDGER, {"invoice_item": row.name, "docstatus": ["<", 2]})


def make_accrual(doc, row):
	edition = frappe.db.get_value(
		"Book Edition", row.get(FIELD), ["agreement", "period", "carried_to_period", "doctor_share"], as_dict=True
	)
	qty = flt(row.stock_qty or row.qty)
	amount = flt(qty * flt(edition.doctor_share), frappe.get_precision(LEDGER, "amount"))
	if not amount:
		return None
	entry = frappe.get_doc(
		{
			"doctype": LEDGER,
			"agreement": edition.agreement,
			"period": sale_period(edition, doc.posting_date),
			"entry_date": doc.posting_date,
			# A credit note takes the copies back: an adjustment carries its own sign.
			"entry_type": "Adjustment" if amount < 0 else "Accrual",
			"edition": row.get(FIELD),
			"qty": qty,
			"amount": amount,
			"sales_invoice": doc.name,
			"invoice_item": row.name,
			"remarks": _("{0} row #{1}: {2} x {3}").format(doc.name, row.idx, qty, flt(edition.doctor_share)),
		}
	)
	entry.flags.cost_center = row.cost_center or doc.cost_center
	return entry


def sale_period(edition, posting_date):
	"""The period a copy is sold in, for the doctor's statement of that period (DOC-08): the edition's own, or the
	period it was carried forward to (DOC-15) once that period has started."""
	if edition.carried_to_period:
		start = frappe.db.get_value("Academic Period", edition.carried_to_period, "start_date")
		if start and getdate(posting_date) >= getdate(start):
			return edition.carried_to_period
	return edition.period


def account(company, account_name):
	name = frappe.db.get_value("Account", {"account_name": account_name, "company": company, "is_group": 0})
	if not name:
		frappe.throw(
			_("Account {0} is missing for {1}. Run setup_coa.py.").format(account_name, company), title=_("Missing Account")
		)
	return name


def post(doc, accruals):
	"""One submitted Journal Entry for the invoice's new rows; returns its name."""
	expense, payable = account(doc.company, EXPENSE_ACCOUNT), account(doc.company, PAYABLE_ACCOUNT)
	rows = []
	for entry in accruals:
		amount = abs(flt(entry.amount))
		owed = flt(entry.amount) > 0
		cost_center = entry.flags.cost_center
		rows.append(
			{
				"account": expense,
				"cost_center": cost_center,
				"debit_in_account_currency": amount if owed else 0,
				"credit_in_account_currency": 0 if owed else amount,
			}
		)
		rows.append(
			{
				# A plain liability: each doctor's share is in his ledger (setup_coa.py).
				"account": payable,
				"cost_center": cost_center,
				"debit_in_account_currency": 0 if owed else amount,
				"credit_in_account_currency": amount if owed else 0,
			}
		)
	journal_entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": doc.company,
			"posting_date": doc.posting_date,
			"accounts": rows,
			"user_remark": _("The doctor's amount on the copies sold in {0}.").format(doc.name),
		}
	)
	# Branch managers make no journal entries (owner, 12 Oct 2026); this one is the sale's own posting.
	journal_entry.flags.ignore_permissions = True
	journal_entry.flags.from_doctor_accrual = True
	journal_entry.insert()
	journal_entry.submit()
	return journal_entry.name


def cancel_accruals(doc, method=None):
	"""Sales Invoice on_cancel hook: the copies are no longer sold, so the doctor's amount on them goes, in his
	ledger and in the accounts."""
	entries = frappe.get_all(LEDGER, filters={"sales_invoice": doc.name, "docstatus": 1}, fields=["name", "journal_entry"])
	for entry in entries:
		cancel(LEDGER, entry.name)
	for journal_entry in sorted({entry.journal_entry for entry in entries if entry.journal_entry}):
		if frappe.db.get_value("Journal Entry", journal_entry, "docstatus") == 1:
			cancel("Journal Entry", journal_entry)


def cancel(doctype, name):
	doc = frappe.get_doc(doctype, name)
	doc.flags.ignore_permissions = True
	doc.flags.from_doctor_accrual = True
	doc.cancel()


def block_cancel_of_accrual(doc, method=None):
	"""Doctor Ledger Entry and Journal Entry before_cancel hook: what a sale posted for the doctor goes only when
	the sale is cancelled, and a payout's journal entry only with the payout, otherwise his ledger and the accounts
	would no longer agree."""
	if doc.flags.from_doctor_accrual:
		return
	if doc.doctype == LEDGER:
		if doc.app_course:
			# APP-05: the course's fee follows its subscriptions (platform_fee_posting.py).
			frappe.throw(
				_("{0} is the platform fee of course {1}. It changes with the course's subscriptions.").format(doc.name, doc.app_course),
				title=_("Posted by a Course"),
			)
		invoice = doc.sales_invoice
	else:
		entry = frappe.db.get_value(LEDGER, {"journal_entry": doc.name, "docstatus": 1}, ["name", "sales_invoice"], as_dict=True)
		if entry and not entry.sales_invoice:
			# A payout's journal entry goes with the payout.
			frappe.throw(
				_("{0} was posted by Doctor Ledger Entry {1}. Cancel that entry instead.").format(doc.name, entry.name),
				title=_("Posted by the Doctor's Ledger"),
			)
		invoice = entry.sales_invoice if entry else None
	if invoice and frappe.db.get_value("Sales Invoice", invoice, "docstatus") == 1:
		frappe.throw(
			_("{0} was posted by Sales Invoice {1} for the doctor's amount. Cancel the invoice instead.").format(doc.name, invoice),
			title=_("Posted by a Sale"),
		)


def run_daily():
	"""Run by the scheduler (hooks.py). Returns (invoices counted, invoices whose entries were cancelled)."""
	report_sales_in_closed_periods()
	return (
		catch_up(missed_sales(), accrue, _("Sales Invoice {0}: the doctor's amount could not be counted")),
		catch_up(cancelled_sales(), cancel_accruals, _("Sales Invoice {0}: the doctor's amount could not be cancelled")),
	)


def missed_sales(closed=False):
	"""Submitted invoices with an edition line not in the doctor's ledger. Editions with no amount per copy are
	left out: they never make an entry, so they would be picked up every day.

	QA-33: a sale whose edition's period is closed cannot be counted any more (the period is locked); it is listed
	apart (closed=True) and reported once, not tried and logged again every day."""
	return frappe.db.sql_list(
		f"""select distinct sii.parent from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		join `tabBook Edition` be on be.name = sii.{FIELD}
		left join `tabAcademic Period` ap on ap.name = coalesce(nullif(be.carried_to_period, ''), be.period)
		where si.docstatus = 1 and be.doctor_share != 0 and ifnull(ap.is_closed, 0) = %s and not exists (
			select 1 from `tabDoctor Ledger Entry` dle where dle.invoice_item = sii.name and dle.docstatus < 2
		)
		order by si.posting_date, si.name""",
		(1 if closed else 0,),
	)


def report_sales_in_closed_periods():
	"""One Error Log per sale the daily job cannot count because its period is closed: the accountant decides (open
	the period, or settle the doctor by hand)."""
	for invoice in missed_sales(closed=True):
		title = _("Sales Invoice {0}: the doctor's amount was not counted; its period is closed").format(invoice)
		if not frappe.db.exists("Error Log", {"method": title}):
			frappe.log_error(title=title, message=title)


def cancelled_sales():
	"""Cancelled invoices whose entries still count."""
	return frappe.db.sql_list(
		"""select distinct dle.sales_invoice from `tabDoctor Ledger Entry` dle
		join `tabSales Invoice` si on si.name = dle.sales_invoice
		where dle.docstatus = 1 and si.docstatus = 2
		order by dle.sales_invoice"""
	)


def catch_up(invoices, action, error_title):
	count = 0
	for name in invoices:
		frappe.db.savepoint("doctor_accrual")
		try:
			action(frappe.get_doc("Sales Invoice", name))
			count += 1
		except Exception:
			frappe.db.rollback(save_point="doctor_accrual")
			# One bad invoice must not stop the others; the error log shows what went wrong.
			frappe.log_error(title=error_title.format(name))
	return count

