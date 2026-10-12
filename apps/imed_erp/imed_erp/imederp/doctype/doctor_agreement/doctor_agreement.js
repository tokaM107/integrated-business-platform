// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Doctor Agreement", {
	setup(frm) {
		// Only doctors (customers in the doctor group) can be picked; the server checks it too.
		frm.set_query("doctor", () => ({ filters: { customer_group: "طبيب" } }));
	},

	refresh(frm) {
		show_balance(frm);
	},
});

// DOC-30: the balance with its direction, in a colour that cannot be missed. Orange: the group owes the
// doctor (books); blue: the doctor owes the group (app).
function show_balance(frm) {
	if (frm.is_new() || !frm.doc.balance_direction) return;
	const amount = format_currency(frm.doc.balance || 0);
	const owed_to_doctor = frm.doc.balance_direction === "Owed to Doctor";
	frm.dashboard.clear_headline();
	frm.dashboard.set_headline_alert(
		owed_to_doctor
			? __("We owe the doctor {0} under this agreement.", [amount])
			: __("The doctor owes us {0} under this agreement.", [amount]),
		owed_to_doctor ? "orange" : "blue"
	);
}
