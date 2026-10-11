// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

/*
 * Stock Entry — the issue of an approved branch request (imederp/material_issue.py). Attached via
 * hooks.py `doctype_js`. Reminders only: the server requires the recipient, the machine for paper and
 * the approved quantities whatever the form shows.
 */

frappe.ui.form.on("Stock Entry", {
	setup(frm) {
		// Machines that can take paper: not disabled. The server also checks the machine is at the branch.
		frm.set_query("custom_printing_machine", "items", () => ({ filters: { disabled: 0 } }));
	},

	refresh(frm) {
		const from_request = (frm.doc.items || []).some((d) => d.material_request);
		frm.toggle_reqd("custom_received_by", from_request && frm.doc.docstatus === 0);
		if (from_request && frm.doc.docstatus === 0) {
			frm.set_intro(
				__("Issue of an approved request: enter who received the materials, and the printing machine for paper rows. Stock leaves the warehouse only when you submit."),
				"blue"
			);
		}
	},
});
