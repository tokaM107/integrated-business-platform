// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Daily Printing"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: () => ({ filters: { is_group: 0, parent_cost_center: ["like", "مكتبات 2Be Doctor%"] } }),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// The library's day under its machines; a shortfall in red.
		if (data && column.fieldname === "variance_value" && data.variance_value > 0) value = `<span style="color: var(--red-600)">${value}</span>`;
		return data && data.is_total ? `<b>${value}</b>` : value;
	},
};
