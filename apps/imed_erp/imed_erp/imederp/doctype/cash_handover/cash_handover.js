// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The weekly cash hand-over (ACC-09): record and submit, print the receipt, the receiver signs it by hand, attaches
// the scan and confirms. No electronic signature.
frappe.ui.form.on("Cash Handover", {
	setup(frm) {
		frm.set_query("treasury", () => ({ filters: { account_type: "Cash", is_group: 0 } }));
		frm.set_query("branch", () => ({ filters: { is_group: 0 } }));
		frm.set_query("receiver", () => ({
			query: "imed_erp.imederp.doctype.cash_handover.cash_handover.receivers",
			filters: { receiver_kind: frm.doc.receiver_kind },
		}));
	},
	refresh(frm) {
		const money = (v) => format_currency(v, frappe.defaults.get_default("currency"));
		if (frm.doc.status === "Pending Receipt") {
			frm.set_intro(
				frm.doc.signed_receipt
					? __("Signed receipt attached. {0} confirms after counting {1}.", [frm.doc.receiver, money(frm.doc.amount)])
					: __("Print the receipt, have {0} sign it by hand, then attach the scan or photo (Signed Receipt).", [frm.doc.receiver]),
				"orange"
			);
		} else if (frm.doc.status === "Received") {
			frm.set_intro(__("Received by {0} on {1}.", [frm.doc.received_by, frappe.datetime.str_to_user(frm.doc.received_on)]), "green");
		} else if (frm.doc.status === "Cancelled") {
			frm.set_intro(__("Cancelled by {0}: {1}", [frm.doc.cancelled_by, frm.doc.cancel_reason]), "red");
		}
		if (frm.doc.docstatus === 1) {
			frm.page.clear_secondary_action();
			frm.add_custom_button(__("Print Receipt"), () => frm.print_doc());
		}
		if (frm.doc.status === "Pending Receipt" && frm.doc.receiver === frappe.session.user) {
			frm.add_custom_button(__("Confirm Receipt"), () => {
				frappe.prompt(
					{ fieldname: "received_amount", fieldtype: "Currency", label: __("Cash Counted"), reqd: 1 },
					({ received_amount }) =>
						frappe
							.call("imed_erp.imederp.doctype.cash_handover.cash_handover.confirm_receipt", { name: frm.doc.name, received_amount })
							.then(() => frm.reload_doc()),
					__("Confirm Receipt")
				);
			}).addClass("btn-primary");
		}
		const canCancel =
			(frm.doc.status === "Pending Receipt" && (frm.doc.handed_over_by === frappe.session.user || frappe.user.has_role("Accounts Manager"))) ||
			(frm.doc.status === "Received" && frappe.user.has_role("Accounts Manager"));
		if (frm.doc.docstatus === 1 && canCancel) {
			frm.add_custom_button(__("Cancel with Reason"), () =>
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Why is it cancelled?"), reqd: 1 },
					({ reason }) =>
						frappe
							.call("imed_erp.imederp.doctype.cash_handover.cash_handover.cancel_handover", { name: frm.doc.name, reason })
							.then(() => frm.reload_doc()),
					__("Cancel Hand-over")
				)
			);
		}
	},
	receiver_kind(frm) {
		frm.set_value("receiver", null);
	},
});
