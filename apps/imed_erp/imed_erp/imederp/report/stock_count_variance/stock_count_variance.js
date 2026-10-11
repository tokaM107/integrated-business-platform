// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Stock Count Variance"] = {
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
		{
			// A group (e.g. Libraries) includes every branch under it.
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Cost Center",
		},
		{
			fieldname: "store",
			label: __("Store"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({ filters: { is_group: 0 } }),
		},
		{
			fieldname: "count_type",
			label: __("Count Type"),
			fieldtype: "Select",
			options: ["", "Daily", "Periodic (Consumables)"],
		},
		{
			fieldname: "counted_by",
			label: __("Counted By"),
			fieldtype: "Link",
			options: "User",
		},
		{
			// Left unticked, items that matched are listed too, so every count shows.
			fieldname: "only_differences",
			label: __("Only Differences"),
			fieldtype: "Check",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (["difference_qty", "difference_value"].includes(column.fieldname) && data) {
			const difference = flt(data[column.fieldname]);
			if (difference < 0) value = `<span style="color: var(--red-600)">${value}</span>`;
			else if (difference > 0) value = `<span style="color: var(--green-600)">${value}</span>`;
		}
		return value;
	},
};
