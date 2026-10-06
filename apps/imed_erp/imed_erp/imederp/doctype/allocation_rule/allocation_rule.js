// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Allocation Rule", {
	setup(frm) {
		// The same choices ERPNext's Cost Center Allocation accepts.
		frm.set_query("main_cost_center", () => ({ filters: { is_group: 0 } }));
		frm.set_query("cost_center", "businesses", () => ({
			filters: {
				is_group: 0,
				company: frm.doc.company || "",
				name: ["!=", frm.doc.main_cost_center || ""],
			},
		}));
	},
});
