// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Expense", {
	setup(frm) {
		// Same rules as the server-side validate, so wrong choices are not offered at all.
		frm.set_query("activity", () => ({ filters: { is_group: 0 } }));
		frm.set_query("expense_category", () => ({ filters: { is_group: 0 } }));
		// Company is fetched from the activity, so only that company's treasuries are offered.
		frm.set_query("treasury", () => ({
			filters: {
				account_type: ["in", ["Cash", "Bank"]],
				is_group: 0,
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
	},

	refresh(frm) {
		// Apply the screen design standard (see docs/SCREEN_DESIGN_STANDARD.md).
		// Expense is a lean custom doctype with no tax / currency fields, so the standard here is
		// about PROGRESSIVE DISCLOSURE, not hiding noise. Everyone fills the same few business fields
		// (date, activity, category, amount, treasury, supplier, description, receipt). The derived
		// "Accounting" section (company, expense account, journal entry) is all read-only and filled
		// in automatically on save, so:
		//   - branch staff (no accounting-manager role) never see it — a simpler screen;
		//   - accountants / managers see it, collapsed on a new expense.
		// This is UI only: the fields and the accounting logic are untouched (see the helper's SCOPE
		// note). Field order is set in expense.json.
		imed.screen.apply(frm, {
			collapse_on_new: ["accounting_section"],
			restrict: [
				{ unless: imed.screen.ROLE_GROUPS.accounting_manager, hide: ["accounting_section"] },
			],
		});
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
