# Stock Value by Warehouse for the Owner Dashboard: the value held in each warehouse of the group's company, from Bin
# joined to Warehouse on its company (audit of 1 Nov 2026: a Bin has no company, and a chart grouped on Bin alone drew
# ERPNext's _Test companies' stock on the owner's dashboard; a name filter is not a company filter).

import frappe
from frappe.utils import flt

from imed_erp.imederp.owner_dashboard import check_access
from imed_erp.imederp.owner_figures import COMPANY


def stock_value_by_warehouse(company=COMPANY):
	"""{warehouse: stock value} for the leaf warehouses of `company` that hold anything, by value descending."""
	rows = frappe.db.sql(
		"""select bin.warehouse, sum(bin.stock_value) as value
		from `tabBin` bin join `tabWarehouse` wh on wh.name = bin.warehouse
		where wh.company = %(company)s
		group by bin.warehouse having abs(sum(bin.stock_value)) >= 0.005
		order by value desc""",
		{"company": company},
		as_dict=True,
	)
	return {row.warehouse: flt(row.value, 2) for row in rows}


@frappe.whitelist()
def get(chart_name=None, chart=None, no_cache=None, filters=None, from_date=None, to_date=None, timespan=None,
		time_interval=None, heatmap_year=None):
	check_access()
	values = stock_value_by_warehouse()
	abbr = frappe.get_cached_value("Company", COMPANY, "abbr")
	return {
		"labels": [name.removesuffix(f" - {abbr}") for name in values],
		"datasets": [{"name": frappe._("Stock Value"), "values": list(values.values())}],
	}
