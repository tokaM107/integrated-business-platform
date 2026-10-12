// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Doctor Agreement", {
	setup(frm) {
		// Only doctors (customers in the doctor group) can be picked; the server checks it too.
		frm.set_query("doctor", () => ({ filters: { customer_group: "طبيب" } }));
	},
});
