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
		// Only the bills of the place chosen above.
		frm.set_query("recurring_expense", () => ({
			filters: { enabled: 1, activity: frm.doc.activity || "" },
		}));
	},

	activity(frm) {
		// A bill of the place picked before no longer applies.
		if (frm.doc.recurring_expense) frm.set_value("recurring_expense", "");
	},

	expense_type(frm) {
		if (frm.doc.expense_type !== "Every Month") frm.set_value("recurring_expense", "");
	},

	async recurring_expense(frm) {
		if (!frm.doc.recurring_expense) return;
		const bill = await frappe.db.get_doc("Recurring Expense", frm.doc.recurring_expense);
		await frm.set_value({
			expense_category: bill.expense_category,
			treasury: bill.treasury,
		});
		// The expected amount is only a starting point; one already typed in is kept.
		if (bill.amount && !frm.doc.amount) {
			await frm.set_value("amount", bill.amount);
		}
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
		frm.trigger("show_status");
		frm.trigger("add_approval_buttons");
	},

	receipt(frm) {
		frm.trigger("show_status");
	},

	show_status(frm) {
		// Only reminders: the server refuses a submit without a receipt or approval either way.
		const doc = frm.doc;
		if (doc.approval_status === "Rejected") {
			frm.set_intro(__("This expense was rejected and is closed. Make a new expense if it is still needed."), "red");
		} else if (doc.docstatus === 0 && !doc.receipt) {
			frm.set_intro(__("Attach the receipt before submitting this expense."), "orange");
		} else if (doc.approval_status === "Pending Approval") {
			frm.set_intro(__("Waiting for the owner's approval."), "blue");
		} else {
			frm.set_intro("");
		}
	},

	add_approval_buttons(frm) {
		const doc = frm.doc;
		const onload = doc.__onload || {};
		if (doc.docstatus !== 0 || frm.is_new() || frm.is_dirty()) return;

		if (doc.approval_status === "Pending Approval" && onload.is_approver) {
			frm.page.set_primary_action(__("Approve"), () => frm.call("approve").then(() => frm.reload_doc()));
			frm.add_custom_button(__("Reject"), () => {
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Rejection Reason") },
					({ reason }) => frm.call("reject", { reason }).then(() => frm.reload_doc()),
					__("Reject Expense"),
					__("Reject")
				);
			});
		} else if (!doc.approval_status && onload.needs_approval && !onload.is_approver) {
			// In place of Submit, which the server would refuse.
			frm.page.set_primary_action(__("Request Approval"), () =>
				frm.call("request_approval").then(() => frm.reload_doc())
			);
		} else if (doc.approval_status === "Pending Approval") {
			frm.page.clear_primary_action();
		}
	},
});
