// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Studio Hour Package", {
	setup(frm) {
		frm.set_query("resource", () => ({ filters: { resource_type: "Studio Service", disabled: 0 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.set_intro(
				__("{0} of {1} hours left.", [frappe.format(frm.doc.hours_remaining, { fieldtype: "Float", precision: 2 }), frm.doc.hours_purchased]),
				frm.doc.hours_remaining > 0 ? "blue" : "orange"
			);
			frm.page.clear_secondary_action();
			if (!frm.doc.sales_invoice) {
				frm.add_custom_button(__("Make Invoice"), () =>
					frappe
						.call("imed_erp.imederp.doctype.studio_hour_package.studio_hour_package.make_invoice", { name: frm.doc.name })
						.then(() => frm.reload_doc())
				);
			}
			if (frappe.user.has_role("Accounts Manager")) {
				frm.add_custom_button(__("Cancel with Reason"), () =>
					frappe.prompt(
						{ fieldname: "reason", fieldtype: "Small Text", label: __("Why is it cancelled?"), reqd: 1 },
						({ reason }) =>
							frappe
								.call("imed_erp.imederp.doctype.studio_hour_package.studio_hour_package.cancel_package", { name: frm.doc.name, reason })
								.then(() => frm.reload_doc()),
						__("Cancel Package")
					)
				);
			}
		}
	},
});
