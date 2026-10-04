# Checks the financial settings: EGP currency, fiscal year, date and number formats, and that a closed
# accounting period blocks posting (CORE-09). Creates a test invoice and a test closed period, then
# ROLLS EVERYTHING BACK, so nothing is saved.
#
# Run from bench console (after setup_regional.py and setup_core.py):
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/check_financial.py").read(), {"frappe": frappe})

import frappe
from frappe.utils import add_days, flt, fmt_money, formatdate, getdate, nowdate

# Hardcoded on purpose, like the other setup scripts.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
CURRENCY = "EGP"
DATE_FORMAT = "dd-mm-yyyy"

results = []


def check(label, ok, detail=""):
	results.append(bool(ok))
	print(f"{'PASS' if ok else 'FAIL'}  {label}{'  -> ' + str(detail) if detail != '' else ''}")


def test_customer():
	group = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
	territory = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
	return (
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "Check Financial Student",
				"customer_group": group[0] if group else "All Customer Groups",
				"territory": territory[0] if territory else "All Territories",
			}
		)
		.insert()
		.name
	)


def make_invoice(customer, posting_date):
	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": COMPANY,
			"customer": customer,
			"set_posting_time": 1,
			"posting_date": posting_date,
			"due_date": posting_date,
			"cost_center": f"قاعات Imed - {ABBR}",
			"items": [{"item_code": "HALL-HOUR", "qty": 3, "rate": 1234.5, "cost_center": f"قاعات Imed - {ABBR}"}],
		}
	).insert()
	si.submit()
	return si


def run():
	# ---------- 1) Currency ----------
	company = frappe.db.get_value("Company", COMPANY, ["abbr", "default_currency"], as_dict=True)
	if not company or company.abbr != ABBR:
		print(f"STOP  Company '{COMPANY}' with abbr '{ABBR}' not found.")
		return
	check("Company default currency is EGP", company.default_currency == CURRENCY, company.default_currency)
	gd = frappe.db.get_single_value("Global Defaults", "default_currency")
	check("Global Defaults currency is EGP", gd == CURRENCY, gd)
	symbol = frappe.db.get_value("Currency", CURRENCY, "symbol")
	check("EGP symbol is Latin 'EGP' (no £, no Arabic)", symbol == "EGP", repr(symbol))

	# ---------- 2) Fiscal year ----------
	fy = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ["<=", nowdate()], "year_end_date": [">=", nowdate()], "disabled": 0},
		["name", "year_start_date", "year_end_date"],
		as_dict=True,
	)
	check("A fiscal year covers today", fy, f"{fy.name}: {fy.year_start_date} to {fy.year_end_date}" if fy else "none")
	if fy:
		linked = frappe.get_all("Fiscal Year Company", filters={"parent": fy.name}, pluck="company")
		check("Fiscal year applies to the company", not linked or COMPANY in linked, linked or "all companies")

	# ---------- 3) Date and number formats ----------
	fmt = frappe.db.get_single_value("System Settings", "date_format")
	check(f"Date format is {DATE_FORMAT}", fmt == DATE_FORMAT, fmt)
	check("Dates print as 28-09-2026", formatdate("2026-09-28") == "28-09-2026", formatdate("2026-09-28"))
	money = fmt_money(1234567.5, currency=CURRENCY)
	check("Money prints as EGP 1,234,567.50", money == "EGP 1,234,567.50", money)
	check("Money rounds to 2 decimals, half-up", flt(2.345, 2) == 2.35, flt(2.345, 2))

	# Everything below writes test data, so commits are disabled and the whole block is rolled back.
	real_commit = frappe.db.commit
	frappe.db.commit = lambda *args, **kwargs: None
	try:
		customer = test_customer()

		# ---------- 4) Invoice comes out in EGP, not £ ----------
		si = make_invoice(customer, nowdate())
		check("Invoice currency is EGP", si.currency == CURRENCY, si.currency)
		check("Invoice is not rounded: amount due is 3,703.50", si.outstanding_amount == 3703.5, si.outstanding_amount)
		fmt = frappe.get_meta("Sales Invoice").default_print_format
		check("Invoices print with MMG Sales Invoice by default", fmt == "MMG Sales Invoice", fmt)
		html = frappe.get_print("Sales Invoice", si.name)
		check("Printed invoice shows 'EGP 3,703.50'", "EGP 3,703.50" in html)
		check("Printed invoice has no £ sign", "£" not in html)
		check("Printed invoice has no Arabic currency symbol", "ج.م" not in html)

		# Arabic print: every label in Arabic, amount in words equal to the total (not rounded to 3,704).
		lang = frappe.local.lang
		try:
			frappe.local.lang = "ar"
			html_ar = frappe.get_print("Sales Invoice", si.name)
		finally:
			frappe.local.lang = lang
		words = "فقط ثلاثة آلاف و سبعمائة و ثلاثة جنيه مصري وخمسون قرشًا لا غير"
		check("Arabic amount in words matches 3,703.50", words in html_ar)
		english = [w for w in ("Invoice Number", "Customer Name", "Grand Total", "In Words", "Amount") if w in html_ar]
		check("Arabic invoice has no English labels", not english, english or "")
		try:
			pdf = frappe.get_print("Sales Invoice", si.name, as_pdf=True)
			check("Invoice PDF is generated", pdf[:4] == b"%PDF", f"{len(pdf)} bytes")
		except Exception as e:
			check("Invoice PDF is generated", False, str(e)[:80])

		# ---------- 5) CORE-09: a closed period blocks posting ----------
		# A test period inside the current fiscal year that has already ended (ERPNext refuses future ones).
		if fy and getdate(fy.year_start_date) < getdate(nowdate()):
			end = add_days(nowdate(), -1)
			start = max(getdate(fy.year_start_date), getdate(add_days(end, -9)))
			period = frappe.get_doc(
				{
					"doctype": "Accounting Period",
					"period_name": "CHECK-FINANCIAL",
					"start_date": start,
					"end_date": end,
					"company": COMPANY,
					# Same list close_period.py uses; ERPNext v16's auto-fill for an empty list crashes.
					"closed_documents": [
						{"document_type": d, "closed": 1} for d in frappe.get_hooks("period_closing_doctypes")
					],
				}
			).insert()
			check(
				"Closed period covers invoices, journal entries, payments and stock",
				{"Sales Invoice", "Journal Entry", "Payment Entry", "Stock Entry"}
				<= {d.document_type for d in period.closed_documents if d.closed},
				f"{len(period.closed_documents)} document types",
			)

			try:
				make_invoice(customer, start)
				check(f"Invoice dated {start} (closed period) is blocked", False, "was accepted")
			except Exception as e:
				blocked = type(e).__name__ == "ClosedAccountingPeriod"
				check(f"Invoice dated {start} (closed period) is blocked", blocked, str(e)[:90])

			try:
				je = frappe.get_doc(
					{
						"doctype": "Journal Entry",
						"company": COMPANY,
						"posting_date": start,
						"accounts": [
							{"account": f"خزينة سنتر Imed - {ABBR}", "debit_in_account_currency": 10, "cost_center": f"قاعات Imed - {ABBR}"},
							{"account": f"إيراد القاعات - {ABBR}", "credit_in_account_currency": 10, "cost_center": f"قاعات Imed - {ABBR}"},
						],
					}
				).insert()
				je.submit()
				check(f"Journal Entry dated {start} (closed period) is blocked", False, "was accepted")
			except Exception as e:
				blocked = type(e).__name__ == "ClosedAccountingPeriod"
				check(f"Journal Entry dated {start} (closed period) is blocked", blocked, str(e)[:90])

			after = make_invoice(customer, nowdate())
			check(f"Invoice dated today ({nowdate()}, open period) is accepted", after.docstatus == 1)
		else:
			print("SKIP  Closed-period test: the fiscal year starts today, so there is no past date inside it yet.")
	finally:
		frappe.db.rollback()
		frappe.db.commit = real_commit

	print()
	print(f"{sum(results)}/{len(results)} checks passed. [test data rolled back, nothing saved]")


run()
