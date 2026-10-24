// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Integration Status"] = {
	filters: [],
	onload(report) {
		report.page.add_inner_button(__("Import a Period Again"), () => {
			const dialog = new frappe.ui.Dialog({
				title: __("Import a Period Again"),
				fields: [
					{
						fieldname: "source_system",
						label: __("System"),
						fieldtype: "Select",
						options: [{ value: "ba_plus", label: __("BA Plus app") }],
						default: "ba_plus",
						reqd: 1,
						description: __("Only BA Plus's import reads files so far."),
					},
					{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.add_days(frappe.datetime.get_today(), -7) },
					{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
				],
				primary_action_label: __("Import Again"),
				primary_action(values) {
					frappe.call({
						method: "imed_erp.imederp.report.integration_status.integration_status.reimport_period",
						args: values,
						freeze: true,
						freeze_message: __("Importing..."),
						callback(r) {
							dialog.hide();
							const runs = r.message || [];
							const lines = runs.map((run) =>
								__("{0}: {1} imported, {2} skipped, {3} failed ({4})", [run.log, run.inserted, run.skipped, run.failed, __(run.status)])
							);
							frappe.msgprint(lines.join("<br>") || __("Nothing was run."), __("Imported Again"));
							report.refresh();
						},
					});
				},
			});
			dialog.show();
		});
	},
};
