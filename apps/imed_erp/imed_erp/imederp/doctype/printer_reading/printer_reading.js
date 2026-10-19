// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Printer Reading", {
	setup(frm) {
		// Machines in service only.
		frm.set_query("machine", () => ({ filters: { disabled: 0 } }));
	},

	machine(frm) {
		frm.trigger("set_opening");
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.machine) frm.trigger("set_opening");
	},

	set_opening(frm) {
		// The opening is the machine's last closing reading; only its first reading is typed.
		if (!frm.doc.machine) return;
		frappe
			.call("imed_erp.imederp.doctype.printer_reading.printer_reading.get_opening", { machine: frm.doc.machine })
			.then(({ message }) => {
				const known = message !== null && message !== undefined;
				if (known && frm.doc.opening_reading !== message) frm.set_value("opening_reading", message);
				frm.set_df_property("opening_reading", "read_only", known ? 1 : 0);
			});
	},
});
