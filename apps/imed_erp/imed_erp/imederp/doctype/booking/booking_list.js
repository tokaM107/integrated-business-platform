// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The bookings list: each booking's status in its colour, the same as on its form and in the calendar.
frappe.listview_settings["Booking"] = {
	add_fields: ["status", "resource_type", "xstudio_no_phone"],
	get_indicator(doc) {
		// An XStudio walk-in without a phone, in purple (owner, 5 Nov 2026).
		if (doc.xstudio_no_phone) return [`${__(doc.status)} · ${__("Without a Phone")}`, "purple", "xstudio_no_phone,=,1"];
		const colors = (frappe.boot.imed_booking || {}).colors || {};  // booking_rules.py
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
