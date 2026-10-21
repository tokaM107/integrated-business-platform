// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Treasury Close", {
	setup(frm) {
		frm.set_query("treasury", () => ({ filters: { account_type: ["in", ["Cash", "Bank"]], is_group: 0 } }));
		frm.set_query("business", () => ({ filters: { is_group: 0 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.difference) {
			const money = format_currency(Math.abs(frm.doc.difference), frappe.defaults.get_default("currency"));
			frm.set_intro(
				frm.doc.difference < 0 ? __("Short by {0}.", [money]) : __("Over by {0}.", [money]),
				frm.doc.difference < 0 ? "red" : "orange"
			);
		}
	},
});
