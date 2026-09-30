// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inter Business Transfer", {
	setup(frm) {
		// Same rules as the server-side validate, so wrong choices are not offered at all.
		for (const field of ["from_business", "to_business"]) {
			frm.set_query(field, () => ({ filters: { is_group: 0 } }));
		}
		for (const field of ["from_treasury", "to_treasury"]) {
			frm.set_query(field, () => ({
				filters: { account_type: ["in", ["Cash", "Bank"]], is_group: 0 },
			}));
		}
	},
});
