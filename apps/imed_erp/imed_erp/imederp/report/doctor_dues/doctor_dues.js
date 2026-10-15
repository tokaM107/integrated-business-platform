// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Doctor Dues"] = {
	filters: [
		{
			fieldname: "as_of",
			label: __("As Of"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "doctor",
			label: __("Doctor"),
			fieldtype: "Link",
			options: "Customer",
			get_query: () => ({ filters: { customer_group: "طبيب" } }),
		},
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Link",
			options: "Academic Period",
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Cost Center",
		},
	],
};
