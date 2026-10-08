// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Reorder Alerts"] = {
	filters: [
		{
			// A group (e.g. Mawasah) covers the warehouses under it.
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
	],
};
