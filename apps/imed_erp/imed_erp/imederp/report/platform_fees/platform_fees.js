// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Platform Fees"] = {
	filters: [
		{
			fieldname: "period",
			label: __("Term"),
			fieldtype: "Link",
			options: "Academic Period",
			get_query: () => ({ filters: { period_type: "Term" } }),
		},
		{
			fieldname: "doctor",
			label: __("Doctor"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "agreement",
			label: __("App Agreement"),
			fieldtype: "Link",
			options: "Doctor Agreement",
			get_query: () => ({ filters: { agreement_type: "App" } }),
		},
	],
};
