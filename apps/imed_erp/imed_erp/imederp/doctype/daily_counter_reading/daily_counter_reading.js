// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The day's counters of one library on one screen (PRN-01), read twice: in the morning type each machine's counter
// and save; in the evening type each closing and submit. The machine's last closing is shown beside the morning
// reading; a difference needs its reason.
frappe.ui.form.on("Daily Counter Reading", {
	setup(frm) {
		frm.set_query("branch", () => ({ filters: { is_group: 0, parent_cost_center: ["like", "مكتبات 2Be Doctor%"] } }));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.branch) {
			// A branch manager's own library.
			frappe.db
				.get_list("User Permission", {
					filters: { user: frappe.session.user, allow: "Cost Center" },
					fields: ["for_value"],
				})
				.then((rows) => {
					if (rows.length === 1) frm.set_value("branch", rows[0].for_value);
				});
		}
	},

	refresh(frm) {
		// A branch manager types the closing readings and sees the sheets; the money is the accountant's and the
		// owner's (docs/SCREEN_DESIGN_STANDARD.md §2).
		imed.screen.apply(frm, {
			restrict: [{ unless: imed.screen.ROLE_GROUPS.accounting_manager, hide: ["money_section"] }],
		});
		if (frm.is_new()) {
			frm.set_intro(__("Morning: type each machine's counter as it shows now, then Save."), "blue");
		} else if (frm.doc.docstatus === 0) {
			frm.set_intro(__("Evening: type each machine's closing reading, then Submit. Tick Broke Down for a machine that stopped today."), "blue");
		}
		if (frm.doc.total_gap) {
			frm.dashboard.set_headline_alert(__("{0} sheets were printed while no reading was taken (Gap Since Last Closing).", [frm.doc.total_gap]), "orange");
		}
	},

	branch(frm) {
		frm.clear_table("machines");
		if (!frm.doc.branch) return frm.refresh_field("machines");
		frappe
			.call("imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading.get_machines", { branch: frm.doc.branch })
			.then(({ message }) => {
				(message || []).forEach((m) => frm.add_child("machines", m));
				frm.refresh_field("machines");
			});
	},
});

frappe.ui.form.on("Daily Counter Reading Item", {
	opening_reading(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.previous_closing != null) frappe.model.set_value(cdt, cdn, "gap", (row.opening_reading || 0) - row.previous_closing);
	},
	closing_reading(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "consumed", row.closing_reading ? row.closing_reading - (row.opening_reading || 0) : 0);
	},
});
