// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Printing Machine", {
	setup(frm) {
		frm.set_query("cost_center", () => ({ filters: { is_group: 0 } }));
	},
});
