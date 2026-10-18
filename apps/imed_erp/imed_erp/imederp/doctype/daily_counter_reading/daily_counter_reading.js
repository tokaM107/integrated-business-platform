// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The day's counters of one library on one screen (PRN-01): pick the library (filled in for a branch manager) and
// type each machine's closing reading; the openings come from each machine's last reading.
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
	closing_reading(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "consumed", (row.closing_reading || 0) - (row.opening_reading || 0));
	},
});
