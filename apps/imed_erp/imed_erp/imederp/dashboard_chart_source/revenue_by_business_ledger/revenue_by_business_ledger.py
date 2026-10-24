# Revenue by Business (QA-06): from the ledger, every income account, by cost center, for a stretch of dates
# (this month to today unless the chart's filters say otherwise).

import json

import frappe
from frappe.utils import get_first_day, today

from imed_erp.imederp.owner_dashboard import check_access, revenue_by_business


@frappe.whitelist()
def get(chart_name=None, chart=None, no_cache=None, filters=None, from_date=None, to_date=None, timespan=None,
		time_interval=None, heatmap_year=None):
	check_access()
	if isinstance(filters, str):
		filters = json.loads(filters)
	filters = frappe._dict(filters or {})
	revenue = revenue_by_business(filters.from_date or get_first_day(today()), filters.to_date or today())
	abbr = frappe.get_cached_value("Company", frappe.defaults.get_global_default("company"), "abbr")
	businesses = sorted(revenue, key=lambda name: -revenue[name])
	return {
		"labels": [name.removesuffix(f" - {abbr}") for name in businesses],
		"datasets": [{"name": "Revenue", "values": [revenue[name] for name in businesses]}],
	}
