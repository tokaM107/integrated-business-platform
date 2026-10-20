frappe.provide("frappe.dashboards.chart_sources");

// QA-06: each business's revenue this month, from every income account in the ledger
// (imederp/owner_dashboard.py), so platform fees and the halls' revenue share are in.
frappe.dashboards.chart_sources["Revenue by Business (Ledger)"] = {
	method: "imed_erp.imederp.dashboard_chart_source.revenue_by_business_ledger.revenue_by_business_ledger.get",
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
