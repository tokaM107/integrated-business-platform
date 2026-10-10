// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

/*
 * Purchase Invoice — the screen design standard on the accountant's purchase of paper and materials
 * (LIB-07, ACC-12). See docs/SCREEN_DESIGN_STANDARD.md. Attached via hooks.py `doctype_js`.
 *
 * The library buys directly: one invoice with Update Stock ticked receives the paper into the store and
 * records what is owed (setup/setup_buying.py). What stays on screen: supplier and date -> Update Stock
 * and the warehouse -> items (item, quantity, unit, rate) -> totals; paid now or not (Is Paid, with the
 * payment method and treasury on the Payments tab); the payment terms (cash or 30 days) on the Terms tab;
 * the supplier's invoice attached from the sidebar.
 *
 * UI-only: fields are hidden, never deleted; saving, stock and accounting are untouched.
 */

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		imed.screen.apply(frm, {
			// One Egyptian company, EGP only, domestic, no VAT or withholding, no e-invoicing.
			hide_groups: ["tax", "zatca", "international"],

			hide: [
				"currency_and_price_list", // currency, exchange rate, price list
				"taxes_section", // tax template, shipping rule, incoterm
				"section_break_51", // the Purchase Taxes and Charges table
				"totals", // tax totals row
				"sec_tax_breakup",
				"section_tax_withholding_entry",
				// Company-currency duplicates: the same as the invoice's own values in an EGP company.
				"base_total",
				"base_net_total",
				"base_totals_section",
				// Subcontracting and rejected goods: the library buys finished paper and materials.
				"is_subcontracted",
				"supplier_warehouse",
				"rejected_warehouse",
				"raw_materials_supplied",
				"pricing_rule_details",
				// Supplier address and shipping: not used for local purchases.
				"address_and_contact_tab",
				// Terms and Conditions text; the Terms tab keeps only the payment terms.
				"terms_section_break",
			],

			// Reachable in one click, not part of the everyday purchase.
			collapse: [
				"accounting_dimensions_section", // Cost Center / Project
				"section_break_44", // additional discount
			],
		});
	},
});
