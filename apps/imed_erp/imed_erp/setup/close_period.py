# Month-end closing for Mohamed Mamdouh group (CORE-09): lock a finished month so nothing can be
# posted, edited or cancelled inside it.
#
# Run from bench console at month end:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/close_period.py").read(), {"frappe": frappe})
#
# It creates an ERPNext "Accounting Period" for the month with every period-closing document type
# closed (Sales/Purchase Invoice, Journal Entry, Payment Entry, Stock Entry, Purchase Receipt,
# Delivery Note, Stock Reconciliation, ...). ERPNext then rejects any of them dated in that month:
# "You cannot create a Sales Invoice within the closed Accounting Period ...".
#
# Idempotent: re-running for a month that is already closed only re-closes anything that was reopened.
# To reopen a month: Accounting > Accounting Period > open it > untick "Closed" (or tick "Disabled").

import calendar

import frappe
from frappe.utils import getdate, nowdate

# Hardcoded on purpose, like the other setup scripts.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"

# Month to close as "YYYY-MM". Leave empty to close the last fully finished month.
MONTH = ""


def month_bounds(month):
	if month:
		year, mon = (int(x) for x in month.split("-"))
	else:
		today = getdate(nowdate())
		year, mon = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
	start = getdate(f"{year}-{mon:02d}-01")
	end = getdate(f"{year}-{mon:02d}-{calendar.monthrange(year, mon)[1]:02d}")
	return f"{year}-{mon:02d}", start, end


def run():
	# Safety check: stop if the company is missing or its abbreviation differs.
	if frappe.db.get_value("Company", COMPANY, "abbr") != ABBR:
		print(f"STOP   Company '{COMPANY}' with abbr '{ABBR}' not found. Nothing was changed.")
		return

	period_name, start, end = month_bounds(MONTH)
	# ERPNext refuses Accounting Periods that end in the future.
	if end > getdate(nowdate()):
		print(f"STOP   {period_name} has not ended yet (ends {end}). Close it after month end. Nothing was changed.")
		return

	name = f"{period_name} - {ABBR}"
	closing_doctypes = frappe.get_hooks("period_closing_doctypes")

	# ---------- 1) Create the period, or re-close it if it was reopened ----------
	if not frappe.db.exists("Accounting Period", name):
		# closed_documents is passed explicitly: ERPNext v16's own auto-fill for an empty list crashes
		# ("'dict' object has no attribute 'document_type'").
		frappe.get_doc(
			{
				"doctype": "Accounting Period",
				"period_name": period_name,
				"start_date": start,
				"end_date": end,
				"company": COMPANY,
				"closed_documents": [{"document_type": d, "closed": 1} for d in closing_doctypes],
			}
		).insert()
		print(f"create Accounting Period {name} ({start} to {end}): {len(closing_doctypes)} document types closed")
	else:
		period = frappe.get_doc("Accounting Period", name)
		changes = []
		if period.disabled:
			period.disabled = 0
			changes.append("enabled")
		listed = {d.document_type: d for d in period.closed_documents}
		for doctype in closing_doctypes:
			if doctype not in listed:
				period.append("closed_documents", {"document_type": doctype, "closed": 1})
				changes.append(f"added {doctype}")
			elif not listed[doctype].closed:
				listed[doctype].closed = 1
				changes.append(f"closed {doctype}")
		if changes:
			period.save()
			print(f"update Accounting Period {name}: {', '.join(changes)}")
		else:
			print(f"exists Accounting Period {name}: already closed")

	# ---------- 2) Summary of all closed periods ----------
	print()
	for p in frappe.get_all(
		"Accounting Period",
		filters={"company": COMPANY, "disabled": 0},
		fields=["name", "start_date", "end_date"],
		order_by="start_date",
	):
		print(f"closed {p.name}: {p.start_date} to {p.end_date}")

	frappe.db.commit()
	print(f"DONE   {period_name} is closed for {COMPANY}. Posting dated {start} to {end} is now blocked.")


run()
