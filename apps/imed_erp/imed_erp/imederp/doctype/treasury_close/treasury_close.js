// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Treasury Close", {
	setup(frm) {
		frm.set_query("treasury", () => ({ filters: { account_type: "Cash", is_group: 0 } }));
		frm.set_query("business", () => ({ filters: { is_group: 0 } }));
	},
	refresh(frm) {
		const money = (value) => format_currency(Math.abs(value), frappe.defaults.get_default("currency"));
		if (frm.doc.needs_review) {
			frm.set_intro(__("Needs review: {0}", [frm.doc.review_note || ""]), "orange");
		} else if (frm.doc.docstatus === 1 && frm.doc.difference) {
			frm.set_intro(
				frm.doc.difference < 0
					? __("Short by {0}. The accountant reviews it with the week.", [money(frm.doc.difference)])
					: __("Over by {0}. The accountant reviews it with the week.", [money(frm.doc.difference)]),
				frm.doc.difference < 0 ? "red" : "orange"
			);
		} else if (frm.doc.docstatus === 2 && frm.doc.reopen_reason) {
			frm.set_intro(__("Reopened by {0}: {1}", [frm.doc.reopened_by, frm.doc.reopen_reason]), "blue");
		}
		// A close is cancelled only by reopening it, with a reason.
		if (frm.doc.docstatus === 1) frm.page.clear_secondary_action();
		if (frm.doc.docstatus === 1 && frappe.user.has_role("Accounts Manager")) {
			frm.add_custom_button(__("Reopen"), () => {
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Why is it reopened?"), reqd: 1 },
					({ reason }) => {
						frappe
							.call({
								method: "imed_erp.imederp.doctype.treasury_close.treasury_close.reopen",
								args: { name: frm.doc.name, reason },
								freeze: true,
							})
							.then((r) => r.message && frappe.set_route("Form", "Treasury Close", r.message));
					},
					__("Reopen the Close"),
					__("Reopen")
				);
			});
		}
	},
});
