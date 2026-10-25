// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("XStudio Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Sync Now"), () => {
			frappe.call({
				method: "imed_erp.imederp.xstudio.sync.sync_now",
				freeze: true,
				freeze_message: __("Reading XStudio..."),
				callback(r) {
					const log = r.message;
					if (!log) return;
					frappe.msgprint({
						title: __("Sync Finished"),
						message: __("{0}: {1} read, {2} inserted, {3} updated, {4} unchanged, {5} failed. Log {6}.", [
							__(log.status), log.rows_read, log.inserted, log.updated, log.skipped, log.failed,
							frappe.utils.get_form_link("Integration Import Log", log.name, true),
						]),
						indicator: log.status === "Completed" ? "green" : "orange",
					});
					frm.reload_doc();
				},
			});
		});
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({
				method: "imed_erp.imederp.xstudio.sync.test_connection",
				freeze: true,
				callback(r) {
					frappe.msgprint({ title: __("XStudio"), message: r.message, indicator: "green" });
					frm.reload_doc();
				},
			});
		});
		frm.set_query("resource", "hall_map", () => ({ filters: { resource_type: "Studio Service", disabled: 0 } }));
		frm.set_query("packages_resource", () => ({ filters: { resource_type: "Studio Service", disabled: 0 } }));
	},
});
