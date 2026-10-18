// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Booking Resource", {
	setup(frm) {
		frm.set_query("cost_center", () => ({ filters: { is_group: 0 } }));
		frm.set_query("item", () => ({ filters: { is_stock_item: 0, disabled: 0 } }));
	},
});
