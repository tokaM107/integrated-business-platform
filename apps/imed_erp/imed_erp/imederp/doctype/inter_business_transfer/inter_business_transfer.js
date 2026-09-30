// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inter Business Transfer", {
	setup(frm) {
		// Same rules as the server-side validate, so wrong choices are not offered at all.
		for (const field of ["from_business", "to_business"]) {
			frm.set_query(field, () => ({ filters: { is_group: 0 } }));
		}
		for (const field of ["from_treasury", "to_treasury"]) {
			frm.set_query(field, () => ({
				filters: { account_type: ["in", ["Cash", "Bank"]], is_group: 0 },
			}));
		}
	},

	refresh(frm) {
		// The server checks the role again; hiding the button only keeps the form clean.
		if (frm.doc.docstatus === 1 && frm.doc.status === "Sent" && frappe.user.has_role("Accounts Manager")) {
			frm.add_custom_button(__("Confirm Receipt"), () => {
				frappe.confirm(
					__("Confirm that {0} was received in {1}?", [
						format_currency(frm.doc.amount),
						frm.doc.to_treasury,
					]),
					() => frm.call("confirm_receipt").then(() => frm.reload_doc())
				);
			}).addClass("btn-primary");
		}
	},
});
