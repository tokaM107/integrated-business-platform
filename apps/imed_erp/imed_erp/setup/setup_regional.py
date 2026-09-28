# Regional settings for Mohamed Mamdouh group: currency, fiscal years, date and number formats,
# interface language (Arabic for users, English for Administrator).
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

# Fiscal years follow the academic year (September to August). The next year is created ahead of
# time so nothing stops on 1 September; add a line here each year.
FISCAL_YEARS = [
	("2026-2027", "2026-09-01", "2027-08-31"),
	("2027-2028", "2027-09-01", "2028-08-31"),
]

# Interface language: Arabic for everyone who uses the system, English for Administrator only.
# "language" in System Settings is the default for new users and the login page.
USER_LANGUAGE = "ar"
ADMIN_LANGUAGE = "en"

SYSTEM_SETTINGS = {
	"country": "Egypt",
	"language": USER_LANGUAGE,
	"time_zone": "Africa/Cairo",
	"currency": CURRENCY,
	"date_format": "dd-mm-yyyy",
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

	# ---------- 2) Fiscal years ----------
	for name, start, end in FISCAL_YEARS:
		if frappe.db.exists("Fiscal Year", name):
			fy = frappe.get_doc("Fiscal Year", name)
			if (getdate(fy.year_start_date), getdate(fy.year_end_date)) != (getdate(start), getdate(end)):
				print(f"WARN   Fiscal Year {name} runs {fy.year_start_date} to {fy.year_end_date}, expected {start} to {end} (not changed)")
			else:
				print(f"exists Fiscal Year {name} ({start} to {end})")
		else:
			fy = frappe.get_doc(
				{"doctype": "Fiscal Year", "year": name, "year_start_date": start, "year_end_date": end}
			).insert()
			print(f"create Fiscal Year {name} ({start} to {end})")

		# Link the year to the company explicitly (an empty list means "all companies").
		if COMPANY in [d.company for d in fy.companies]:
			print(f"exists Fiscal Year {name} -> {COMPANY}")
		else:
			fy.append("companies", {"company": COMPANY})
			fy.save()
			print(f"set    Fiscal Year {name} -> {COMPANY}")

	known = [name for name, _, _ in FISCAL_YEARS]
	for other in frappe.get_all("Fiscal Year", filters={"name": ["not in", known], "disabled": 0}, pluck="name"):
		print(f"note   Another active Fiscal Year exists: {other}")

	# ---------- 3) Date, time and number formats ----------
	apply(frappe.get_single("System Settings"), SYSTEM_SETTINGS, "System Settings")

	# ---------- 4) Interface language per user ----------
	for user in frappe.get_all("User", filters={"user_type": "System User"}, fields=["name", "language"]):
		if user.name == "Guest":
			continue
		wanted = ADMIN_LANGUAGE if user.name == "Administrator" else USER_LANGUAGE
		if user.language == wanted:
			print(f"exists User {user.name}.language = {wanted}")
		else:
			frappe.db.set_value("User", user.name, "language", wanted)
			print(f"set    User {user.name}.language: {user.language!r} -> {wanted!r}")

	frappe.db.commit()
	frappe.clear_cache()
	print(f"DONE   Regional settings applied for {COMPANY}. Users must reload the page to see the new formats.")


run()
