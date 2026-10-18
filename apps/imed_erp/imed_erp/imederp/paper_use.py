# Paper used for printing and copying (PRN-02, LIB-03; owner's decision of 12 Oct 2026). Printing and copying
# are services, not stock, so selling them took no paper out of the store: the next count found the sheets
# used and posted them as a shortage on the stock differences account. Now a sale of either issues its sheets
# of A4 paper from the library's raw materials store, as cost of goods sold on the library's cost center, the
# account the paper item already uses (setup_core.py). A count then shows only real losses.
#
# hooks.py runs on Sales Invoice (POS sales reach here too, as the invoice made when the shift is closed):
#   on_submit  issue_paper_used       one Material Issue per invoice, linked by its Sales Invoice field
#   on_cancel  cancel_paper_used      the issue goes with the invoice
# and on Stock Entry before_cancel:
#   block_cancel_of_paper_issue        an invoice's issue is cancelled only with the invoice

import frappe
from frappe import _
from frappe.utils import flt

from imed_erp.imederp.doctype.book_edition.book_edition import LIBRARY_PAPER_STORE, PAPER
from imed_erp.imederp.doctype.expense.expense import get_approvers
from imed_erp.imederp.system_user import as_administrator
from imed_erp.notification_service import notify

# Service item -> sheets of A4 paper per unit sold. Both are sold by the sheet (1 EGP a sheet).
SHEETS_PER_UNIT = {"PRINT-SVC": 1, "COPY-SVC": 1}


def sheets_by_store(invoice):
	"""{(store, library cost center): sheets} the invoice's printing and copying used."""
	abbr = frappe.get_cached_value("Company", invoice.company, "abbr")
	used = {}
	for row in invoice.items:
		per_unit = SHEETS_PER_UNIT.get(row.item_code)
		if not per_unit:
			continue
		library = row.cost_center or invoice.cost_center
		store = LIBRARY_PAPER_STORE.get((library or "").removesuffix(f" - {abbr}"))
		if not store:
			# Printing is sold only by the libraries; anything else has no paper store to take from.
			continue
		key = (f"{store} - {abbr}", library)
		used[key] = used.get(key, 0) + flt(row.stock_qty or row.qty) * per_unit
	return used


def sheets_sold(library, date):
	"""Sheets of printing and copying the library sold on `date` (PRN-02), from its submitted invoices. A refund
	does not take any back: the paper was printed, and the counters counted it."""
	units = ", ".join(["%s"] * len(SHEETS_PER_UNIT))
	return flt(
		frappe.db.sql(
			f"""select sum(sii.stock_qty * case sii.item_code {" ".join("when %s then %s" for _ in SHEETS_PER_UNIT)} end)
			from `tabSales Invoice Item` sii join `tabSales Invoice` si on si.name = sii.parent
			where si.docstatus = 1 and si.is_return = 0 and si.posting_date = %s
			and ifnull(nullif(sii.cost_center, ''), si.cost_center) = %s and sii.item_code in ({units})""",
			(*[v for item, per_unit in SHEETS_PER_UNIT.items() for v in (item, per_unit)], date, library, *SHEETS_PER_UNIT),
		)[0][0]
	)


def refresh_counters(doc, method=None):
	"""Sales Invoice on_submit and on_cancel hook: the day's counters of the library already submitted take the
	sale into what was sold."""
	from imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading import refresh_sold

	for _store, library in sheets_by_store(doc):
		refresh_sold(library, doc.posting_date)


def issue_paper_used(doc, method=None):
	if doc.is_return:
		# A refund does not bring the printed paper back.
		return
	for (store, library), sheets in sheets_by_store(doc).items():
		if sheets <= 0:
			continue
		issue = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Issue",
				"company": doc.company,
				"posting_date": doc.posting_date,
				"posting_time": doc.posting_time,
				"set_posting_time": 1,
				"sales_invoice_no": doc.name,
				"remarks": _("Paper used for printing and copying sold on {0}.").format(doc.name),
				"items": [
					{
						"item_code": PAPER,
						"qty": sheets,
						"s_warehouse": store,
						"cost_center": library,
						"expense_account": paper_expense_account(doc.company),
					}
				],
			}
		)
		issue.flags.from_paper_use = True
		# Posted in the system's name: the cashier sells printing, she does not issue stock.
		enough = on_hand(store, doc.posting_date, doc.posting_time) >= sheets
		if not enough:
			# The store shows fewer sheets than were sold: the sale stands, and the issue waits as a draft for
			# the accountant. It is not tied to the sale's time, so once the missing paper is received he
			# submits it as it is, dated the day he does.
			issue.set_posting_time = 0
		with as_administrator():
			issue.insert()
			if enough:
				issue.submit()
		if not enough:
			message = _("{0} has fewer sheets than the {1} sold for printing and copying. The paper issue {2} is saved as a draft for the accountant.").format(
				store, sheets, issue.name
			)
			frappe.msgprint(message, title=_("Paper Not Issued"), indicator="orange")
			notify("paper_issue_pending", get_approvers(), {"subject": message}, document=("Stock Entry", issue.name))


def cancel_paper_used(doc, method=None):
	for name, docstatus in frappe.get_all(
		"Stock Entry", filters={"sales_invoice_no": doc.name, "docstatus": ["<", 2]}, fields=["name", "docstatus"], as_list=True
	):
		issue = frappe.get_doc("Stock Entry", name)
		issue.flags.ignore_permissions = True
		issue.flags.from_paper_use = True
		if docstatus == 1:
			issue.cancel()
		else:
			frappe.delete_doc("Stock Entry", name, ignore_permissions=True)


def block_cancel_of_paper_issue(doc, method=None):
	"""Stock Entry before_cancel hook: paper issued for a sale is returned only by cancelling the sale."""
	if doc.flags.from_paper_use or not doc.get("sales_invoice_no") or doc.stock_entry_type != "Material Issue":
		return
	if frappe.db.get_value("Sales Invoice", doc.sales_invoice_no, "docstatus") == 1:
		frappe.throw(
			_("{0} is the paper used for Sales Invoice {1}. Cancel the invoice instead.").format(doc.name, doc.sales_invoice_no)
		)


def paper_expense_account(company):
	return frappe.db.get_value("Item Default", {"parent": PAPER, "company": company}, "expense_account") or frappe.get_cached_value(
		"Company", company, "default_expense_account"
	)


def on_hand(store, posting_date, posting_time):
	from erpnext.stock.utils import get_stock_balance

	return flt(get_stock_balance(PAPER, store, posting_date, posting_time))
