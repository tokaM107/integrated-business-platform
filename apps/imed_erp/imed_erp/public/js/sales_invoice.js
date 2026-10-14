// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

/*
 * Sales Invoice — worked example of the screen design standard on a standard ERPNext doctype.
 * See docs/SCREEN_DESIGN_STANDARD.md. Attached via hooks.py `doctype_js`.
 *
 * UI-only: fields are hidden, never deleted. Nothing here touches the database, the schema, or any
 * accounting/validation behaviour (e.g. library income account, set server-side, is untouched).
 *
 * It reuses the shared helper `imed.screen.apply` — no bespoke hide/collapse code of its own. The
 * generic field groups (tax / zatca / international) come from the helper; the few Sales-Invoice-
 * specific section headers below are listed here because those section names are specific to this
 * doctype.
 */

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		// The paper a printing sale issued (imederp/paper_use.py) goes back when the invoice is cancelled; the
		// Cancel button must not try to cancel that Stock Entry first, which is refused on its own.
		frm.ignore_doctypes_on_cancel_all = frm.ignore_doctypes_on_cancel_all || [];
		if (!frm.ignore_doctypes_on_cancel_all.includes("Stock Entry")) {
			frm.ignore_doctypes_on_cancel_all.push("Stock Entry");
		}

		imed.sales_cancellation.ask_reason_on_cancel(frm);

		imed.screen.apply(frm, {
			// Generic noise MMG never uses (one Egyptian company, EGP only, domestic, no e-invoicing):
			//   tax         — no VAT / withholding charged on these invoices
			//   zatca       — Saudi e-invoicing (no such fields on this doctype; no-op)
			//   international — foreign currency, exchange rate, shipping terms, shipping/dispatch address
			hide_groups: ["tax", "zatca", "international"],

			// Sales-Invoice-specific sections/fields to hide. Hiding a Section Break hides the whole
			// section, so the headers do not linger empty after their fields are hidden above.
			hide: [
				"taxes_section", // "Taxes and Charges" header (tax template, shipping rule, incoterm)
				"section_break_40", // the Sales Taxes and Charges table
				"section_break_43", // tax totals row
				"sec_tax_breakup", // "Tax Breakup"
				"section_tax_withholding_entry", // "Tax Withholding Entry"
				// Company-currency duplicates: identical to the transaction values in a single-currency
				// (EGP) company, so they only add noise.
				"base_total",
				"base_net_total",
				"base_totals_section", // "Totals (Company Currency)"
			],

			// Progressive disclosure: advanced blocks stay reachable but collapsed, so the primary
			// workflow (customer -> items -> totals) is what you see first.
			collapse: [
				"accounting_dimensions_section", // Cost Center / Project — advanced, set per workflow
				"additional_discount_section", // discount tools, used occasionally
			],

			// Keep visible, pending a business decision (documented in the standard):
			//   tax_id / company_tax_id — Egyptian tax-registration numbers may be legally required.
		});
	},

	// The reason is asked before anything is cancelled (see ask_reason_on_cancel); the invoice is then cancelled
	// with it on the server, so this stops Frappe's own cancel request, which would carry no reason.
	async before_cancel(frm) {
		const reason = frm.__imed_cancel_reason || (await imed.sales_cancellation.prompt_reason(frm));
		frm.__imed_cancel_reason = null;
		frappe.validated = false;
		if (!reason) return;
		let r;
		try {
			r = await frappe.call({
				method: "imed_erp.imederp.sales_cancellation.cancel_with_reason",
				args: { doctype: frm.doctype, name: frm.docname, reason },
				freeze: true,
				freeze_message: __("Cancelling"),
			});
		} catch (e) {
			// Refused on the server (no right, a closed month...): its message is already shown. Returning lets
			// Frappe end the cancel and enable the button again.
			return;
		}
		if (r && !r.exc) {
			frappe.utils.play_sound("cancel");
			frappe.show_alert({ message: __("Cancelled"), indicator: "red" });
			await frm.reload_doc();
		}
	},
});

/*
 * A sale is cancelled only with its reason (ACC-06; imederp/sales_cancellation.py, which also refuses a cancel
 * without one). Cancel first asks for the reason, before Frappe cancels any linked document, then goes on with
 * Frappe's own steps (linked documents, confirmation); before_cancel above sends the reason with the cancel.
 */
frappe.provide("imed.sales_cancellation");

/* Resolves with the reason typed, or null when the dialog is closed without one. */
imed.sales_cancellation.prompt_reason = function (frm) {
	return new Promise((resolve) => {
		let reason = null;
		const dialog = new frappe.ui.Dialog({
			title: __("Cancel {0}", [frm.docname]),
			fields: [
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Cancellation Reason"),
					description: __("Why is this sale cancelled? The reason is kept on the invoice."),
					reqd: 1,
				},
			],
			primary_action_label: __("Continue"),
			primary_action(values) {
				reason = (values.reason || "").trim();
				if (!reason) {
					frappe.msgprint(__("Give the reason for cancelling {0}.", [frm.docname]));
					return;
				}
				dialog.hide();
			},
		});
		dialog.onhide = () => resolve(reason || null);
		dialog.show();
	});
};

imed.sales_cancellation.ask_reason_on_cancel = function (frm) {
	if (frm.__imed_cancel_wrapped) return;
	frm.__imed_cancel_wrapped = true;
	const frappe_savecancel = frm.savecancel;
	frm.savecancel = async function (btn, callback, on_error) {
		const reason = await imed.sales_cancellation.prompt_reason(frm);
		if (!reason) return frm.handle_save_fail(btn, on_error);
		frm.__imed_cancel_reason = reason;
		return frappe_savecancel.call(frm, btn, callback, on_error);
	};
};
