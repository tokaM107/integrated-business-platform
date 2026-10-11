# Stock counts (LIB-03, PRN-06) on ERPNext's Stock Reconciliation. The library counts every day and the
# consumables (paper, ink) every 7-15 days; ERPNext works out the shortage or surplus, in quantity and
# value, and posts it to the stock differences account (فروقات الجرد). The app adds what kind of count it
# was and who counted (custom fields made by setup/setup_library.py), which the variance report reads. Who
# counted defaults to who made the count (the field's "__user" default, applied in code too) and can be
# changed.
#
# hooks.py runs check_count_type on Stock Reconciliation validate.

import frappe
from frappe import _

DAILY = "Daily"
PERIODIC = "Periodic (Consumables)"
OPENING = "Opening"
COUNT_TYPES = [DAILY, PERIODIC, OPENING]

# ERPNext's purpose for opening balances: posted to a temporary opening account, not to stock differences.
OPENING_STOCK = "Opening Stock"


def check_count_type(doc, method=None):
	# An opening balance is not a shortage or a surplus: it must not land on the stock differences account.
	if doc.purpose == OPENING_STOCK:
		doc.custom_count_type = OPENING
	elif doc.get("custom_count_type") == OPENING:
		frappe.throw(
			_("An opening count records the opening balance: set Purpose to {0}.").format(_(OPENING_STOCK)),
			title=_("Opening Count"),
		)
