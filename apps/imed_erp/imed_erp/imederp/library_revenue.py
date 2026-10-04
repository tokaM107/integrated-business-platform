# Each library has its own revenue account, but an item has only one default income account per
# company (setup_core.py points the library items at Mawasah). This hook moves every library revenue
# row to the revenue account of the library the row is sold in, so nobody has to change it by hand.

import frappe

# Library cost center -> its revenue account (names without the company abbreviation).
LIBRARY_REVENUE = {
	"مكتبة الأزاريطة": "إيراد مكتبة الأزاريطة",
	"مكتبة المواساة": "إيراد مكتبة المواساة",
}


def set_library_income_account(doc, method=None):
	"""Sales Invoice / POS Invoice validate hook."""
	abbr = frappe.get_cached_value("Company", doc.company, "abbr")
	accounts = {f"{cc} - {abbr}": f"{account} - {abbr}" for cc, account in LIBRARY_REVENUE.items()}
	library_accounts = set(accounts.values())

	changed = False
	for row in doc.items:
		wanted = accounts.get(row.cost_center or doc.get("cost_center"))
		# Only swap one library's revenue for the other's; any other income account was chosen on purpose.
		if wanted and row.income_account in library_accounts and row.income_account != wanted:
			row.income_account = wanted
			changed = True

	# ERPNext summarises the item accounts on the invoice earlier in validate; refresh it.
	if changed and hasattr(doc, "set_against_income_account"):
		doc.set_against_income_account()
