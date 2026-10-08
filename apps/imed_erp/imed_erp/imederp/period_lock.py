# Closed periods (CORE-09) on the app's own documents, the same way ERPNext locks its own.
#
# Month-end closing is ERPNext's Accounting Period (setup/close_period.py). It locks every document type in
# the `period_closing_doctypes` hook, and hooks.py adds the app's documents to that list. ERPNext's own check
# reads `posting_date` and `company`, which most of the app's documents do not have, so this one finds the
# date and the company on each document. A document linked to a closed academic period is locked too.

import frappe
from frappe import _

# The doctypes this check runs on (hooks.py: period_closing_doctypes and doc_events).
LOCKED_DOCTYPES = [
	"Expense",
	"Inter Business Transfer",
	"Doctor Ledger Entry",
	"App Subscription",
	"Printer Reading",
]

DATE_FIELDS = ("posting_date", "entry_date", "subscription_date", "reading_date")
COST_CENTER_FIELDS = ("activity", "from_business", "cost_center", "branch")


def validate_closed_period(doc, method=None):
	validate_academic_period(doc)
	date = next((doc.get(f) for f in DATE_FIELDS if doc.get(f)), None)
	company = doc.get("company") or next(
		(frappe.db.get_value("Cost Center", doc.get(f), "company") for f in COST_CENTER_FIELDS if doc.get(f)), None
	)
	if not date or not company:
		return

	ap = frappe.qb.DocType("Accounting Period")
	cd = frappe.qb.DocType("Closed Document")
	period = (
		frappe.qb.from_(ap)
		.from_(cd)
		.select(ap.name, ap.exempted_role)
		.where(
			(ap.name == cd.parent)
			& (ap.company == company)
			& (ap.disabled == 0)
			& (cd.closed == 1)
			& (cd.document_type == doc.doctype)
			& (date >= ap.start_date)
			& (date <= ap.end_date)
		)
	).run(as_dict=True)
	if period and not (period[0].exempted_role and period[0].exempted_role in frappe.get_roles()):
		frappe.throw(
			_("{0} is in the closed accounting period {1}. Choose a date in an open month.").format(
				frappe.format_value(date, {"fieldtype": "Date"}), period[0].name
			),
			title=_("Period Closed"),
		)


def validate_academic_period(doc):
	period = doc.get("period")
	if period and frappe.db.get_value("Academic Period", period, "is_closed"):
		frappe.throw(_("Period {0} is closed. Choose an open period.").format(period), title=_("Period Closed"))
