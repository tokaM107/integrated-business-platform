// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Owner Share Plan vs Actual"] = {
	filters: [
		{
			fieldname: "library",
			label: __("Library"),
			fieldtype: "Link",
			options: "Cost Center",
		},
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Link",
			options: "Academic Period",
		},
	],
};
