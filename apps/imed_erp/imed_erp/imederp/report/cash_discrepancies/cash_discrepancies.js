// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Cash Discrepancies"] = {
	filters: [
		{
			fieldname: "view",
			label: __("Show"),
			fieldtype: "Select",
			options: [
				{ value: "Discrepancies", label: __("Discrepancies") },
				{ value: "Payroll Review", label: __("Payroll Review") },
			],
			default: "Discrepancies",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "business", label: __("Business"), fieldtype: "Link", options: "Cost Center" },
		{ fieldname: "unresolved", label: __("Still Open Only"), fieldtype: "Check" },
	],
};
