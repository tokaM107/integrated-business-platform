// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Expense", {
	setup(frm) {
		// Same rules as the server-side validate, so wrong choices are not offered at all.
		frm.set_query("activity", () => ({ filters: { is_group: 0 } }));
		frm.set_query("expense_category", () => ({ filters: { is_group: 0 } }));
		frm.set_query("treasury", () => ({
			filters: { account_type: ["in", ["Cash", "Bank"]], is_group: 0 },
		}));
	},

	refresh(frm) {
		frm.trigger("show_receipt_reminder");
	},

	receipt(frm) {
		frm.trigger("show_receipt_reminder");
	},

	show_receipt_reminder(frm) {
		// Only a reminder: the server refuses to submit without a receipt either way.
		if (frm.doc.docstatus === 0 && !frm.doc.receipt) {
			frm.set_intro(__("Attach the receipt before submitting this expense."), "orange");
		} else {
			frm.set_intro("");
		}
	},
});
