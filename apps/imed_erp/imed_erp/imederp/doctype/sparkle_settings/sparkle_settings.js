// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sparkle Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Sync Now"), () =>
			frappe.call({ method: "imed_erp.imederp.sparkle.sync.sync_now", freeze: true }).then((r) => {
				const log = r.message || {};
				frappe.msgprint(__("{0}: {1} read, {2} inserted, {3} updated, {4} failed.", [log.status, log.rows_read, log.inserted, log.updated, log.failed]));
				frm.reload_doc();
			})
		);
	},
});
