# Regional settings for Mohamed Mamdouh group: currency, fiscal years, date and number formats,
# interface language (Arabic for users, English for Administrator).
#
# Run from bench console (after setup_core.py, which creates the company):
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

# Invoices print with the app's own format (imederp/print_format/mmg_sales_invoice): fully Arabic for
# Arabic users, English for Administrator, amount in words always equal to the printed total.
INVOICE_PRINT_FORMAT = "MMG Sales Invoice"

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


def clear_conflicting_fiscal_years(name, start, end):
	"""Delete fiscal years that have our name with other dates, or overlap ours, if nothing is posted
	in them. Returns the companies they applied to, so the new year keeps them, or None (and changes
	nothing) if one of them already has ledger entries."""
	conflicts = frappe.get_all(
		"Fiscal Year",
		filters={"year_start_date": ["<=", end], "year_end_date": [">=", start], "disabled": 0},
		fields=["name", "year_start_date", "year_end_date"],
	)
	if frappe.db.exists("Fiscal Year", name):
		conflicts.append(frappe.db.get_value("Fiscal Year", name, ["name", "year_start_date", "year_end_date"], as_dict=True))

	wrong = {
		fy.name: fy
		for fy in conflicts
		if (getdate(fy.year_start_date), getdate(fy.year_end_date)) != (getdate(start), getdate(end))
	}
	for fy in wrong.values():
		posted = frappe.db.exists("GL Entry", {"fiscal_year": fy.name}) or frappe.db.exists(
			"GL Entry", {"posting_date": ["between", [fy.year_start_date, fy.year_end_date]]}
		)
		if posted:
			print(f"WARN   Fiscal Year {fy.name} ({fy.year_start_date} to {fy.year_end_date}) conflicts with {name} ({start} to {end}) but has ledger entries; fix it by hand (not changed)")
			return None
	carried = set()
	for fy in wrong.values():
		linked = frappe.get_all("Fiscal Year Company", filters={"parent": fy.name}, pluck="company")
		# An empty list means the year applied to every company.
		carried.update(linked or frappe.get_all("Company", pluck="name"))
		frappe.delete_doc("Fiscal Year", fy.name, ignore_permissions=True)
		print(f"delete Fiscal Year {fy.name} ({fy.year_start_date} to {fy.year_end_date}): conflicts with {name} ({start} to {end}), nothing posted in it")
	return carried


def run():
	# Safety check: stop if the company is missing or its abbreviation differs.
	if frappe.db.get_value("Company", COMPANY, "abbr") != ABBR:
		print(f"STOP   Company '{COMPANY}' with abbr '{ABBR}' not found; run setup_core.py first. Nothing was changed.")
		return

	# ---------- 1) Currency ----------
	apply(frappe.get_doc("Currency", CURRENCY), CURRENCY_SETTINGS, "Currency EGP")
	# disable_rounded_total: invoices are payable to the piastre (3,703.50 stays 3,703.50, not 3,704),
	# so the total, the amount due and the amount in words are the same number.
	apply(
		frappe.get_single("Global Defaults"),
		{"default_currency": CURRENCY, "country": "Egypt", "disable_rounded_total": 1},
		"Global Defaults",
	)

	company_currency = frappe.db.get_value("Company", COMPANY, "default_currency")
	if company_currency == CURRENCY:
		print(f"exists Company.default_currency = {CURRENCY}")
	else:
		# ERPNext locks the company currency once transactions exist, so only report it.
		print(f"WARN   Company.default_currency is {company_currency}, expected {CURRENCY} (not changed)")

	# ---------- 2) Fiscal years ----------
	for name, start, end in FISCAL_YEARS:
		# The browser setup wizard creates a Jul-Jun year for Egypt, which overlaps ours and would leave
		# a gap (e.g. Jul-Aug 2027 in no year). ERPNext cannot change a saved year's dates, so a wrong
		# year is deleted and recreated, but only while nothing has been posted in it.
		carried = clear_conflicting_fiscal_years(name, start, end)
		if carried is None:
			continue

		if frappe.db.exists("Fiscal Year", name):
			fy = frappe.get_doc("Fiscal Year", name)
			print(f"exists Fiscal Year {name} ({start} to {end})")
		else:
			fy = frappe.get_doc(
				{"doctype": "Fiscal Year", "year": name, "year_start_date": start, "year_end_date": end}
			).insert()
			print(f"create Fiscal Year {name} ({start} to {end})")

		# Link the year to the company explicitly (an empty list means "all companies"), plus any
		# company that used a year replaced above.
		for company in [COMPANY, *sorted(carried - {COMPANY})]:
			if company in [d.company for d in fy.companies]:
				print(f"exists Fiscal Year {name} -> {company}")
			else:
				fy.append("companies", {"company": company})
				fy.save()
				print(f"set    Fiscal Year {name} -> {company}")

	known = [name for name, _, _ in FISCAL_YEARS]
	for other in frappe.get_all("Fiscal Year", filters={"name": ["not in", known], "disabled": 0}, pluck="name"):
		print(f"note   Another active Fiscal Year exists: {other}")

	# ---------- 3) Date, time and number formats ----------
	apply(frappe.get_single("System Settings"), SYSTEM_SETTINGS, "System Settings")

	# ---------- 4) Default invoice print format ----------
	if not frappe.db.exists("Print Format", INVOICE_PRINT_FORMAT):
		print(f"SKIP   Print Format {INVOICE_PRINT_FORMAT} not found (run bench migrate to load it from the app)")
	elif frappe.get_meta("Sales Invoice").default_print_format == INVOICE_PRINT_FORMAT:
		print(f"exists Sales Invoice default print format = {INVOICE_PRINT_FORMAT}")
	else:
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		make_property_setter(
			"Sales Invoice", None, "default_print_format", INVOICE_PRINT_FORMAT, "Data", for_doctype=True
		)
		print(f"set    Sales Invoice default print format = {INVOICE_PRINT_FORMAT}")

	# ---------- 5) Interface language per user ----------
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
