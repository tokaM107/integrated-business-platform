// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Doctor Ledger Entry", {
	setup(frm) {
		// A payout comes out of a cash box or a wallet.
		frm.set_query("treasury", () => ({
			filters: { account_type: ["in", ["Cash", "Bank"]], is_group: 0 },
		}));
	},

	refresh(frm) {
		// DOC-22: a deduction from the doctor waits for the owner or the accountant, like an expense. Only
		// reminders here: the server refuses the rest either way.
		const doc = frm.doc;
		if (doc.approval_status === "Rejected") {
			frm.set_intro(__("This deduction was rejected and is closed."), "red");
		} else if (doc.docstatus === 0 && doc.approval_status === "Pending Approval") {
			frm.set_intro(__("Waiting for approval."), "blue");
		} else {
			frm.set_intro("");
		}
		if (doc.docstatus !== 0 || frm.is_new() || frm.is_dirty()) return;
		if (doc.approval_status === "Rejected") {
			frm.page.clear_primary_action();
		} else if (doc.approval_status === "Pending Approval" && (doc.__onload || {}).is_approver) {
			frm.page.set_primary_action(__("Approve"), () => frm.call("approve").then(() => frm.reload_doc()));
			frm.add_custom_button(__("Reject"), () => {
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Rejection Reason") },
					({ reason }) => frm.call("reject", { reason }).then(() => frm.reload_doc()),
					__("Reject Deduction"),
					__("Reject")
				);
			});
		}
	},
});
