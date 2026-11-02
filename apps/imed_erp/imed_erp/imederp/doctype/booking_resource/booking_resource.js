// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// A hall or a studio service. From a saved hall: book it (a new booking on this hall) or open its calendar.
frappe.ui.form.on("Booking Resource", {
	setup(frm) {
		frm.set_query("cost_center", () => ({ filters: { is_group: 0 } }));
		frm.set_query("item", () => ({ filters: { is_stock_item: 0, disabled: 0 } }));
	},

	refresh(frm) {
		if (frm.is_new()) return;
		if (frappe.model.can_create("Booking") && !frm.doc.disabled) {
			frm.add_custom_button(frm.doc.resource_type === "Hall" ? __("Book This Hall") : __("Book This Service"), () =>
				frappe.new_doc("Booking", { resource: frm.doc.name })
			).addClass("btn-primary");
		}
		if (frappe.model.can_read("Booking")) {
			frm.add_custom_button(__("Calendar"), () => {
				frappe.route_options = { resource: frm.doc.name };
				frappe.set_route("booking", "view", "calendar", "default");
			});
		}
		if (frm.doc.resource_type === "Hall" && !cint(frm.doc.capacity)) {
			frm.set_intro(__("Capacity not set yet: the number of attendees is not checked until it is."), "orange");
		}
	},
});
