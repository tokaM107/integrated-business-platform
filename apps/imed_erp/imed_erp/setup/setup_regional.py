# Regional settings for Mohamed Mamdouh group: currency, fiscal year, date format, number format.
#
# Run from bench console:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_regional.py").read(), {"frappe": frappe})
#
# Idempotent: prints "exists" for values already set and "set" with old -> new for changes.

import frappe
from frappe.utils import getdate

# Hardcoded on purpose, like the other setup scripts.
COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
CURRENCY = "EGP"

# Fiscal year follows the academic year (September to August).
FISCAL_YEAR = "2026-2027"
FY_START = "2026-09-01"
FY_END = "2027-08-31"

SYSTEM_SETTINGS = {
	"country": "Egypt",
	"time_zone": "Africa/Cairo",
	"currency": CURRENCY,
	"date_format": "dd/mm/yyyy",
	"time_format": "HH:mm",
	"first_day_of_the_week": "Saturday",
	# 1,234,567.89: comma groups thousands, dot separates decimals.
	"number_format": "#,###.##",
	# Money to 2 decimals (piastres); quantities and rates keep 3.
	"currency_precision": "2",
	"float_precision": "3",
	# Half-up rounding (2.345 -> 2.35), as used in Egyptian invoices and tax returns.
	"rounding_method": "Commercial Rounding",
}

# Latin symbol: the default Arabic one breaks PDF export.
CURRENCY_SETTINGS = {
	"enabled": 1,
	"symbol": "EGP",
	"symbol_on_right": 0,
	"fraction": "Piastre",
	"fraction_units": 100,
	"number_format": "#,###.##",
}


def apply(doc, values, label):
	"""Set only the fields that differ, then save once so the doctype's own hooks run."""
	changed = False
	for field, value in values.items():
		old = doc.get(field)
		if str("" if old is None else old) == str(value):
			print(f"exists {label}.{field} = {value}")
		else:
			doc.set(field, value)
			print(f"set    {label}.{field}: {old!r} -> {value!r}")
			changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.save()


def run():
	# Safety check: stop if the company is missing or its abbreviation differs.
	if frappe.db.get_value("Company", COMPANY, "abbr") != ABBR:
		print(f"STOP   Company '{COMPANY}' with abbr '{ABBR}' not found. Nothing was changed.")
		return

	# ---------- 1) Currency ----------
	apply(frappe.get_doc("Currency", CURRENCY), CURRENCY_SETTINGS, "Currency EGP")
	apply(frappe.get_single("Global Defaults"), {"default_currency": CURRENCY, "country": "Egypt"}, "Global Defaults")

	company_currency = frappe.db.get_value("Company", COMPANY, "default_currency")
	if company_currency == CURRENCY:
		print(f"exists Company.default_currency = {CURRENCY}")
	else:
		# ERPNext locks the company currency once transactions exist, so only report it.
		print(f"WARN   Company.default_currency is {company_currency}, expected {CURRENCY} (not changed)")

	# ---------- 2) Fiscal year ----------
	if frappe.db.exists("Fiscal Year", FISCAL_YEAR):
		fy = frappe.get_doc("Fiscal Year", FISCAL_YEAR)
		if (getdate(fy.year_start_date), getdate(fy.year_end_date)) != (getdate(FY_START), getdate(FY_END)):
			print(f"WARN   Fiscal Year {FISCAL_YEAR} runs {fy.year_start_date} to {fy.year_end_date}, expected {FY_START} to {FY_END} (not changed)")
		else:
			print(f"exists Fiscal Year {FISCAL_YEAR} ({FY_START} to {FY_END})")
	else:
		fy = frappe.get_doc(
			{"doctype": "Fiscal Year", "year": FISCAL_YEAR, "year_start_date": FY_START, "year_end_date": FY_END}
		).insert()
		print(f"create Fiscal Year {FISCAL_YEAR} ({FY_START} to {FY_END})")

	# Link the year to the company explicitly (an empty list means "all companies").
	if COMPANY in [d.company for d in fy.companies]:
		print(f"exists Fiscal Year {FISCAL_YEAR} -> {COMPANY}")
	else:
		fy.append("companies", {"company": COMPANY})
		fy.save()
		print(f"set    Fiscal Year {FISCAL_YEAR} -> {COMPANY}")

	for other in frappe.get_all("Fiscal Year", filters={"name": ["!=", FISCAL_YEAR], "disabled": 0}, pluck="name"):
		print(f"note   Another active Fiscal Year exists: {other}")

	# ---------- 3) Date, time and number formats ----------
	apply(frappe.get_single("System Settings"), SYSTEM_SETTINGS, "System Settings")

	frappe.db.commit()
	frappe.clear_cache()
	print(f"DONE   Regional settings applied for {COMPANY}. Users must reload the page to see the new formats.")


run()
