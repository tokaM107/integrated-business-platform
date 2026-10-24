// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["App Payments"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{
			fieldname: "kind",
			label: __("Paid"),
			fieldtype: "Select",
			options: [
				{ value: "", label: __("All") },
				{ value: "Cash", label: __("In Cash") },
				{ value: "Electronic", label: __("Electronically") },
			],
		},
		{ fieldname: "treasury", label: __("Paid Into"), fieldtype: "Link", options: "Account" },
		{ fieldname: "branch", label: __("Collecting Branch"), fieldtype: "Link", options: "Cost Center" },
		{ fieldname: "doctor", label: __("Doctor"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "not_cleared", label: __("Not Yet Matched With the Statement"), fieldtype: "Check" },
	],
};
