// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Revenue by Period"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "periodicity",
			label: __("Period"),
			fieldtype: "Select",
			options: [
				{ value: "Daily", label: __("Daily") },
				{ value: "Weekly", label: __("Weekly") },
				{ value: "Monthly", label: __("Monthly") },
			],
			default: "Daily",
			reqd: 1,
		},
		{
			fieldname: "cost_center",
			label: __("Business"),
			fieldtype: "Link",
			options: "Cost Center",
			description: __("A group stands for every business under it."),
		},
	],
	tree: true,
	name_field: "cost_center",
	parent_field: "parent_cost_center",
	initial_depth: 3,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// The groups, which add up their branches, in bold.
		return data && data.is_group ? `<b>${value}</b>` : value;
	},
};
