// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Inter Business Transfers"] = {
	filters: [
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Link",
			options: "Academic Period",
		},
		{
			// Matches a transfer when the business is on either side, sender or receiver.
			fieldname: "business",
			label: __("Business"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: () => ({ filters: { is_group: 0 } }),
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Sent", "Received"],
		},
	],
};
