// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The bookings list: each booking's status in its colour, the same as on its form and in the calendar.
frappe.listview_settings["Booking"] = {
	add_fields: ["status", "resource_type"],
	get_indicator(doc) {
		const colors = {
			Tentative: "orange",
			Confirmed: "green",
			"Confirmed with Deposit": "green",
			Completed: "blue",
			Cancelled: "gray",
			"No Show": "gray",
		};
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
