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
});
