// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

const DISCREPANCY = "imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy.";

function act(frm, method, prompt) {
	const run = (args) =>
		frappe
			.call({ method: DISCREPANCY + method, args: { name: frm.doc.name, ...args }, freeze: true })
			.then(() => frm.reload_doc());
	if (!prompt) return frm.is_dirty() ? frm.save().then(() => run({})) : run({});
	frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: prompt, reqd: 1 }, run, prompt);
}

frappe.ui.form.on("Cash Discrepancy", {
	refresh(frm) {
		const open = ["Pending Investigation", "Responsibility Determined", "Recovery Recommended", "Pending Review"].includes(frm.doc.status);
		if (frm.doc.status === "Pending Investigation") {
			frm.set_intro(
				__("Nobody is charged until the investigation finds who is responsible. Nothing is split or deducted by itself."),
				"orange"
			);
		}
		if (frm.doc.payroll_status) {
			frm.set_intro(__("Approved for the payroll review. The system deducts nothing from a salary."), "blue");
		}
		if (frm.doc.status === "Recovery Recommended") {
			frm.set_intro(__("Recommended by {0}. Waiting for the owner's approval.", [frm.doc.recommended_by]), "orange");
			if (frappe.user.has_role("Super Admin")) {
				frm.add_custom_button(__("Approve Recovery"), () => act(frm, "approve_recovery"), __("Owner"));
				frm.add_custom_button(__("Return to the Accountant"), () => act(frm, "return_recommendation", __("Why is it returned?")), __("Owner"));
			}
		}
		if (frm.doc.kind === "Surplus" && frm.doc.status === "Pending Review") {
			frm.set_intro(__("Under review until the accountant finds where the extra cash came from. It is not revenue."), "orange");
		}
		if (!frappe.user.has_role("Accounts Manager")) return;
		if (frm.doc.kind === "Shortage" && open) {
			if (frm.doc.status !== "Recovery Recommended") {
				frm.add_custom_button(__("Responsibility Determined"), () => act(frm, "determine_responsibility"), __("Review"));
			}
			frm.add_custom_button(__("Write Off"), () => act(frm, "write_off", __("Why does the company bear it?")), __("Review"));
		}
		if (frm.doc.status === "Responsibility Determined") {
			frm.add_custom_button(__("Recommend Recovery"), () => act(frm, "recommend_recovery"), __("Review"));
		}
		if (frm.doc.status === "Recovery Approved" && !frm.doc.adjustment_entry) {
			frm.add_custom_button(__("Withdraw Recovery"), () => act(frm, "withdraw_recovery", __("Why is it withdrawn?")), __("Review"));
		}
		if (frm.doc.kind === "Surplus" && open) {
			frm.add_custom_button(__("Explained"), () => act(frm, "explain_surplus", __("Where did the extra cash come from?")), __("Review"));
		}
		if (["Recovery Approved", "Written Off", "Explained"].includes(frm.doc.status) && !frm.doc.adjustment_entry) {
			frm.add_custom_button(__("Post Adjustment"), () =>
				frappe.confirm(__("Bring the books to the cash counted, against Cash Differences?"), () => act(frm, "post_adjustment"))
			);
		}
	},
});
