// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("App Subscription", {
	// The course is counted again once the subscription is submitted, and its fee written then (app_course.py):
	// the form shows it, not the 0 it was saved with (seen in the browser, 21 Oct 2026).
	on_submit(frm) {
		frm.reload_doc();
	},
});
