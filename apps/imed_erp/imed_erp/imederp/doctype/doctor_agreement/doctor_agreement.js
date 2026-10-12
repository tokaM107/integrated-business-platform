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
	// The type gives the usual direction; a negative balance runs the other way (DOC-20: a books doctor charged
	// more than he earned owes the group).
	const balance = flt(frm.doc.balance);
	const amount = format_currency(Math.abs(balance));
	const owed_to_doctor = (frm.doc.balance_direction === "Owed to Doctor") === balance >= 0;
	const summary = owed_to_doctor
		? __("We owe the doctor {0} under this agreement.", [amount])
		: __("The doctor owes us {0} under this agreement.", [amount]);
	// DOC-29: when it is next settled, the end of the settlement period the accountant entered.
	const next = frm.doc.next_settlement_date
		? __("Next settlement: {0}.", [frappe.datetime.str_to_user(frm.doc.next_settlement_date)])
		: __("Enter the settlement period's dates.");
	frm.dashboard.clear_headline();
	frm.dashboard.set_headline_alert(`${summary} ${next}`, owed_to_doctor ? "orange" : "blue");
}
