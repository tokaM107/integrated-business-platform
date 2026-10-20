// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Treasury Balances"] = {
	filters: [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
	],
};
