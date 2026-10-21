# No completed transaction is dated after today (QA-24; owner, 21 Oct 2026: staff never record a completed
# money or stock transaction ahead of time). Checked on every save, whoever saves it, through the API too.
#
# Only what happened: an expense paid, a transfer sent, a doctor paid or collected from, a counter read, stock
# counted, damaged or sold, a student subscribed, and ERPNext's invoices, payments, journal and stock entries.
# What is planned keeps its future date: a booking, a monthly bill's next date, an allocation rule's or a fee
# schedule's Valid From, an academic period.

import frappe
from frappe import _
from frappe.utils import getdate, today

DATE_FIELD = {
	# The app
	"Expense": "posting_date",
	"Inter Business Transfer": "posting_date",
	"Doctor Ledger Entry": "entry_date",
	"Printer Reading": "reading_date",
	"Daily Counter Reading": "reading_date",
	"Stock Count": "posting_date",
	"Damaged Stock Entry": "posting_date",
	"Damaged Stock Sale": "posting_date",
	"App Subscription": "subscription_date",
	# ERPNext
	"Sales Invoice": "posting_date",
	"POS Invoice": "posting_date",
	"Purchase Invoice": "posting_date",
	"Payment Entry": "posting_date",
	"Journal Entry": "posting_date",
	"Stock Entry": "posting_date",
	"Stock Reconciliation": "posting_date",
	"Delivery Note": "posting_date",
	"Purchase Receipt": "posting_date",
}


def refuse_future_date(doc, method=None):
	"""validate hook for every doctype (hooks.py, "*"); returns at once for those not listed."""
	field = DATE_FIELD.get(doc.doctype)
	if not field or not doc.get(field):
		return
	if getdate(doc.get(field)) > getdate(today()):
		frappe.throw(
			_("{0} cannot be dated after today: {1}. Record it on the day it happens.").format(
				_(doc.doctype), frappe.format_value(doc.get(field), {"fieldtype": "Date"})
			),
			title=_("Date in the Future"),
		)
