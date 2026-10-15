// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Doctor Statement"] = {
	filters: [
		{
			fieldname: "agreement",
			label: __("Agreement"),
			fieldtype: "Link",
			options: "Doctor Agreement",
			reqd: 1,
			get_query: () => ({ filters: { docstatus: 1 } }),
		},
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Link",
			options: "Academic Period",
			reqd: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// The opening and closing rows stand out from the movements between them.
		return data && data.is_total ? `<b>${value}</b>` : value;
	},
};
