// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Printing Machine", {
	setup(frm) {
		// A machine works in a library (PRN-01).
		frm.set_query("cost_center", () => ({ filters: { is_group: 0, parent_cost_center: ["like", "مكتبات 2Be Doctor%"] } }));
	},
});
