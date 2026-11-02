// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Hall Price Tier", {
	setup(frm) {
		frm.set_query("resource", () => ({ filters: { resource_type: "Hall", disabled: 0 } }));
		frm.set_query("price_list", () => ({ filters: { selling: 1, enabled: 1 } }));
	},
});
