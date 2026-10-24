// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("App Payment", {
	setup(frm) {
		frm.set_query("subscription", () => ({ filters: { docstatus: 1 } }));
		frm.set_query("branch", () => ({ filters: { is_group: 0 } }));
		// Cash goes into a cash box, an electronic payment into a bank account or wallet (the server checks which).
		frm.set_query("treasury", () => ({
			filters: { is_group: 0, account_type: frm.doc.payment_method === "Cash" ? "Cash" : "Bank" },
		}));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 2 && frm.doc.cancel_reason) {
			frm.set_intro(__("Cancelled: {0}", [frm.doc.cancel_reason]), "red");
		} else if (frm.doc.docstatus === 1) {
			frm.set_intro(__("Held for the doctor {0}; not the group's revenue.", [frm.doc.doctor]), "blue");
		}
		// Cancelled only with a reason, by the accountant.
		if (frm.doc.docstatus === 1) frm.page.clear_secondary_action();
		if (frm.doc.docstatus === 1 && frappe.user.has_role("Accounts Manager")) {
			frm.add_custom_button(__("Cancel with Reason"), () => {
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Why is it cancelled?"), reqd: 1 },
					({ reason }) =>
						frappe
							.call("imed_erp.imederp.doctype.app_payment.app_payment.cancel_payment", { name: frm.doc.name, reason })
							.then(() => frm.reload_doc()),
					__("Cancel Payment")
				);
			});
		}
	},
	payment_method(frm) {
		frm.set_value("treasury", null);
	},
});
