// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Expense Category", {
	setup(frm) {
		// Same rules as the server-side validate, so wrong choices are not offered at all.
		frm.set_query("parent_expense_category", () => ({ filters: { is_group: 1 } }));
		frm.set_query("expense_account", () => ({
			filters: { root_type: "Expense", is_group: 0 },
		}));
	},
});
