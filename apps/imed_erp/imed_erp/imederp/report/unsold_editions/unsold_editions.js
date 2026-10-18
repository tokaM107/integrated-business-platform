// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Unsold Editions"] = {
	filters: [
		{
			// The start of the next module: what ended before it and still has copies is reviewed (DOC-21).
			fieldname: "before",
			label: __("Period Ended Before"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "library",
			label: __("Library"),
			fieldtype: "Link",
			options: "Cost Center",
		},
	],
};
