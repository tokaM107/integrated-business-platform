// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

/*
 * IMED ERP — reusable screen design standard.
 *
 * One global helper, `imed.screen.apply(frm, config)`, so every form follows the same rules without
 * copying the same Client Script into each doctype. Loaded on the desk by hooks.py (app_include_js).
 *
 * A doctype's own `.js` (its form controller) is our "Client Script": it calls this helper from
 * refresh() with a small config, then adds whatever is specific to that screen.
 *
 *   frappe.ui.form.on("Sales Invoice", {
 *     refresh(frm) {
 *       imed.screen.apply(frm, {
 *         hide_groups: ["tax", "zatca", "international"], // standard ERPNext noise we never use
 *         hide: ["some_field"],                          // screen-specific extras to hide
 *         collapse: ["more_info_section"],               // advanced sections, tucked away but reachable
 *         restrict: [                                    // progressive disclosure by role (UX only)
 *           { unless: imed.screen.ROLE_GROUPS.accounting, collapse: ["accounting_dimensions_section"] },
 *         ],
 *       });
 *       // ... screen-specific behaviour here ...
 *     }
 *   });
 *
 * SCOPE — read this before using `restrict`:
 *   `restrict` is PROGRESSIVE DISCLOSURE for a cleaner screen, NOT access control. Hiding a field in a
 *   Client Script only removes it from this form view; the data is still reachable through the API,
 *   list view, reports and other forms. Real per-role access control is server-side: Role Permissions,
 *   field-level permlevels, and User Permissions (this project already sets these up in
 *   setup_users.py). Use `restrict` only to simplify a screen, and only on fields that are safe to
 *   hide for that role — never to protect data, and never on a field that role must fill to save.
 *
 * What it does NOT do: reorder fields or rename labels. Field order and business-friendly labels are a
 * definition-time concern — `field_order` / labels in the `.json` for our own doctypes, or Customize
 * Form (a Property Setter) for standard doctypes — following docs/SCREEN_DESIGN_STANDARD.md. Reordering
 * or relabelling live in JavaScript fights the framework and breaks on upgrades, so we do not do it.
 *
 * Every field name is guarded with `frm.fields_dict[...]`, so a group that does not exist on a given
 * doctype is simply skipped — the same config is safe on any screen. Forms that never call the helper
 * are not affected by it at all.
 */

frappe.provide("imed.screen");

/*
 * Named groups of standard ERPNext fields that MMG (one Egyptian company, EGP only, no e-invoicing,
 * no foreign trade) never fills in. A screen opts into a group by name; absent fields are ignored.
 * Add a field here only after confirming the business does not use it; anything uncertain is left out
 * and marked "needs business confirmation" in the standard document, rather than hidden on a guess.
 */
imed.screen.FIELD_GROUPS = {
	// Sales/VAT tax machinery. MMG does not charge VAT or withhold tax on these screens today.
	// NOTE: tax_id / company_tax_id (tax-registration numbers) are deliberately NOT here — they may be
	// legally required on Egyptian invoices. Leave them visible (needs business confirmation).
	tax: [
		"taxes_and_charges",
		"taxes",
		"tax_category",
		"taxes_and_charges_added",
		"taxes_and_charges_deducted",
		"total_taxes_and_charges",
		"base_total_taxes_and_charges",
		"other_charges_calculation",
		"item_wise_tax_details",
		"tax_withholding_category",
		"tax_withholding_group",
		"apply_tds",
		"ignore_tax_withholding_threshold",
		"override_tax_withholding_entries",
		"tax_withholding_entries",
	],
	// Saudi ZATCA / e-invoicing. Not applicable to an Egyptian group. None of these exist on stock
	// doctypes, so this group is a no-op today; it documents intent for when such custom fields appear.
	zatca: ["custom_zatca_status", "custom_uuid", "ksa_einv_qr", "qr_code"],
	// Foreign-currency and cross-border workflow. Everything is EGP and domestic. The currency and
	// exchange-rate fields are mandatory but always auto-filled (EGP, rate 1), so hiding them is safe.
	international: [
		"currency",
		"conversion_rate",
		"price_list_currency",
		"plc_conversion_rate",
		"shipping_rule",
		"incoterm",
		"named_place",
		"shipping_address",
		"shipping_address_name",
		"dispatch_address",
		"dispatch_address_name",
	],
};

/*
 * Project role groups, for `restrict`. These are the real roles from setup_users.py (see the
 * Role / Screen matrix in docs/SCREEN_DESIGN_STANDARD.md). This is shared configuration (data), not
 * per-screen logic — the per-screen rules live in each screen's own file. The exact visibility lines
 * are a UX choice; confirm boundaries with the business.
 *   accounting        — sees GL / journal / accounting detail
 *   accounting_manager — the narrower set who own full financial detail
 */
imed.screen.ROLE_GROUPS = {
	accounting: ["Accountant", "Accounts Manager", "Accounts User", "Super Admin", "System Manager"],
	accounting_manager: ["Accountant", "Accounts Manager", "Super Admin", "System Manager"],
};

/* True if the current user has ANY of the given role(s). UX only — see the SCOPE note above. */
imed.screen.has_any_role = function (roles) {
	var list = Array.isArray(roles) ? roles : [roles];
	var mine = frappe.user_roles || [];
	return list.some(function (role) {
		return mine.indexOf(role) !== -1;
	});
};

/* Hide each field that exists on this form; skip the rest. Hiding a Section Break hides its section. */
imed.screen.hide = function (frm, fieldnames) {
	(fieldnames || []).forEach(function (fieldname) {
		if (frm.fields_dict[fieldname]) {
			frm.set_df_property(fieldname, "hidden", 1);
		}
	});
};

/* Collapse each Section Break that exists and can be collapsed; skip the rest. */
imed.screen.collapse = function (frm, sections) {
	(sections || []).forEach(function (fieldname) {
		var field = frm.fields_dict[fieldname];
		if (field && typeof field.collapse === "function") {
			field.collapse(true);
		}
	});
};

/*
 * Apply the standard to a form.
 *
 * config:
 *   hide_groups      Array of FIELD_GROUPS names to hide (e.g. ["tax", "zatca", "international"]).
 *   hide             Array of extra field / section names to hide on this screen.
 *   collapse         Array of Section Break names to collapse every time (advanced-but-reachable).
 *   collapse_on_new  Array of Section Break names to collapse only while the document is new.
 *   restrict         Progressive disclosure by role (UX only, see SCOPE note). Array of rules:
 *                      { unless: [roles], hide: [fields], collapse: [sections] }
 *                    When the current user has NONE of `unless`, the rule's hide/collapse are applied.
 *   screen           function(frm): screen-specific behaviour run last.
 */
imed.screen.apply = function (frm, config) {
	config = config || {};

	var to_hide = [];
	(config.hide_groups || []).forEach(function (group) {
		to_hide = to_hide.concat(imed.screen.FIELD_GROUPS[group] || []);
	});
	to_hide = to_hide.concat(config.hide || []);
	imed.screen.hide(frm, to_hide);

	imed.screen.collapse(frm, config.collapse);
	if (frm.is_new()) {
		imed.screen.collapse(frm, config.collapse_on_new);
	}

	(config.restrict || []).forEach(function (rule) {
		if (!imed.screen.has_any_role(rule.unless || [])) {
			imed.screen.hide(frm, rule.hide);
			imed.screen.collapse(frm, rule.collapse);
		}
	});

	if (typeof config.screen === "function") {
		config.screen(frm);
	}
};
