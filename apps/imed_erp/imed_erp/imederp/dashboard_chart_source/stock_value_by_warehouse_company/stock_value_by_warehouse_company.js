frappe.provide("frappe.dashboards.chart_sources");

// The group's warehouses only, by the Warehouse's company (imederp/dashboard_chart_source/stock_value_by_warehouse_company).
frappe.dashboards.chart_sources["Stock Value by Warehouse Company"] = {
	method: "imed_erp.imederp.dashboard_chart_source.stock_value_by_warehouse_company.stock_value_by_warehouse_company.get",
	filters: [],
};
