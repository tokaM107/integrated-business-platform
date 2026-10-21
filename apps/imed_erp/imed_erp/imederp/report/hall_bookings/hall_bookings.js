// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Hall Bookings"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.month_end(), reqd: 1 },
		{
			fieldname: "hall",
			label: __("Hall"),
			fieldtype: "Link",
			options: "Booking Resource",
			get_query: () => ({ filters: { resource_type: "Hall" } }),
		},
	],
};
