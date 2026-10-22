// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Profit Before and After Shared Costs"] = {
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
			default: frappe.datetime.month_end(),
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
		if (!data) return value;
		const amount = data[column.fieldname];
		// Green a profit, red a loss; orange what the shared premises spent that was not split.
		if (["profit_before", "profit_after"].includes(column.fieldname) && amount) {
			value = `<span style="color: var(${amount > 0 ? "--text-on-green" : "--text-on-red"})">${value}</span>`;
		} else if (column.fieldname === "shared_unallocated" && amount) {
			value = `<span style="color: var(--text-on-orange)">${value}</span>`;
		}
		return data.is_group ? `<b>${value}</b>` : value;
	},
};
