// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

/*
 * Material Request — a branch's request from the main warehouse and Raghad's approval
 * (imederp/material_issue.py). Attached via hooks.py `doctype_js`.
 *
 * Only shows the right action to the right person: the server refuses a submit without approval, and
 * approval or rejection by anyone without the Stock Request Approver role, whatever the form shows.
 * Issuing stays ERPNext's own "Create > Material Transfer" on the approved request.
 */

frappe.ui.form.on("Material Request", {
	refresh(frm) {
		imed.screen.apply(frm, { hide_groups: ["tax", "zatca", "international"] });
		frm.trigger("show_approval");
	},

	show_approval(frm) {
		const doc = frm.doc;
		const onload = doc.__onload || {};
		if (!onload.is_branch_request || frm.is_new()) return;

		const status = doc.custom_approval_status;
		if (doc.docstatus === 0 && status === "Rejected") {
			frm.set_intro(
				__("This request was rejected and is closed: {0}", [doc.custom_rejection_reason || __("no reason given")]),
				"red"
			);
			frm.disable_save();
			return;
		}
		if (doc.docstatus === 0 && status === "Pending Approval") {
			frm.set_intro(__("Waiting for Raghad's approval. Nothing has left the warehouse yet."), "blue");
			if (onload.is_stock_approver) {
				frm.page.set_primary_action(__("Approve"), () => call(frm, "approve"));
				frm.add_custom_button(__("Reject"), () => {
					frappe.prompt(
						{ fieldname: "reason", fieldtype: "Small Text", label: __("Rejection Reason") },
						({ reason }) => call(frm, "reject", { reason }),
						__("Reject Request"),
						__("Reject")
					);
				});
			} else {
				frm.page.clear_primary_action();
			}
			return;
		}
		if (doc.docstatus === 0 && !status && !frm.is_dirty()) {
			frm.set_intro(__("Save the items, then send the request to Raghad for approval."), "blue");
			frm.page.set_primary_action(__("Request Store Approval"), () => call(frm, "request_approval"));
			return;
		}
		if (doc.docstatus === 1 && status === "Approved") {
			frm.set_intro(
				__("Approved by {0} on {1}. The store issues it with Create > Material Transfer.", [
					frappe.user.full_name(doc.custom_approved_by),
					frappe.datetime.str_to_user(doc.custom_approved_on),
				]),
				"green"
			);
		}
	},
});

function call(frm, method, args = {}) {
	return frappe
		.call({
			method: `imed_erp.imederp.material_issue.${method}`,
			args: { name: frm.doc.name, ...args },
			freeze: true,
		})
		.then(() => frm.reload_doc());
}
