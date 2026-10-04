// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Recurring Expense", {
	setup(frm) {
		// Same choices as on Expense, which each month's draft must pass.
		frm.set_query("activity", () => ({ filters: { is_group: 0 } }));
		frm.set_query("expense_category", () => ({ filters: { is_group: 0 } }));
		frm.set_query("treasury", () => ({
			filters: { account_type: ["in", ["Cash", "Bank"]], is_group: 0 },
		}));
	},
});
