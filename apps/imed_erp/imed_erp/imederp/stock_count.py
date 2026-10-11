# Stock counts (LIB-03, PRN-06) on ERPNext's Stock Reconciliation. The library counts every day and the
# consumables (paper, ink) every 7-15 days; ERPNext works out the shortage or surplus, in quantity and
# value, and posts it to the stock differences account (فروقات الجرد). The app adds what kind of count it
# was and who counted (custom fields made by setup/setup_library.py), which the variance report reads. Who
# counted defaults to who made the count (the field's "__user" default, applied in code too) and can be
# changed.
#
# hooks.py runs on Stock Reconciliation validate:
#   check_count_type        an opening count is ERPNext's Opening Stock, and only that
#   set_branch_cost_center  the difference is the branch's: its cost center comes from the store counted

import frappe
from frappe import _

DAILY = "Daily"
PERIODIC = "Periodic (Consumables)"
OPENING = "Opening"
COUNT_TYPES = [DAILY, PERIODIC, OPENING]

# ERPNext's purpose for opening balances: posted to a temporary opening account, not to stock differences.
OPENING_STOCK = "Opening Stock"

# Each branch's group of stores (setup_core.py) -> the branch's cost center. ERPNext would otherwise post
# the difference on the company's default cost center, the head office.
BRANCH_OF_STORES = {
	"المخزن المركزي بالمواساة": "مكتبة المواساة",
	"مخزن الأزاريطة": "مكتبة الأزاريطة",
}


def check_count_type(doc, method=None):
	# An opening balance is not a shortage or a surplus: it must not land on the stock differences account.
	if doc.purpose == OPENING_STOCK:
		doc.custom_count_type = OPENING
	elif doc.get("custom_count_type") == OPENING:
		frappe.throw(
			_("An opening count records the opening balance: set Purpose to {0}.").format(_(OPENING_STOCK)),
			title=_("Opening Count"),
		)


def branch_of(warehouse):
	"""The cost center of the branch a store belongs to, or None for a store outside the branches."""
	from frappe.utils.nestedset import get_ancestors_of

	abbr = frappe.get_cached_value("Company", frappe.db.get_value("Warehouse", warehouse, "company"), "abbr")
	for store in [warehouse, *get_ancestors_of("Warehouse", warehouse)]:
		branch = BRANCH_OF_STORES.get(store.removesuffix(f" - {abbr}"))
		if branch:
			return f"{branch} - {abbr}"
	return None


def set_branch_cost_center(doc, method=None):
	# One count, one branch: its shortage or surplus is posted on that branch's cost center.
	branches = {branch_of(row.warehouse) for row in doc.items if row.warehouse}
	if len(branches) > 1:
		frappe.throw(
			_("A count covers one branch's stores. Count each branch separately: {0}.").format(
				", ".join(sorted(b for b in branches if b) + ([_("other stores")] if None in branches else []))
			),
			title=_("One Branch per Count"),
		)
	branch = next(iter(branches), None)
	if branch:
		doc.cost_center = branch
