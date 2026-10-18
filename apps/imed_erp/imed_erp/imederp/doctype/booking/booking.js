// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// Booking (HAL-02, STU-01, STU-08). The checks are on the server (booking.py); this only helps the screen.
frappe.ui.form.on("Booking", {
	setup(frm) {
		frm.set_query("resource", () => ({ filters: { disabled: 0 } }));
	},

	refresh(frm) {
		imed.screen.apply(frm, { collapse_on_new: ["source_section"] });
		if (frm.doc.source === "Imported") {
			// Changed only in the booking system it came from (INT-01); the server refuses a change here.
			frm.set_intro(
				__("Imported from {0}: change it there, and the next import brings the change.", [
					frappe.utils.escape_html(frm.doc.source_system || ""),
				]),
				"blue"
			);
			frm.disable_form();
		}
	},

	from_time: (frm) => set_hours(frm),
	to_time: (frm) => set_hours(frm),
	total_amount: (frm) => set_remaining(frm),
	paid_amount: (frm) => set_remaining(frm),
});

function set_hours(frm) {
	if (!frm.doc.from_time || !frm.doc.to_time) return;
	const seconds = (t) => t.split(":").reduce((total, part) => total * 60 + flt(part), 0);
	frm.set_value("hours", Math.max(0, (seconds(frm.doc.to_time) - seconds(frm.doc.from_time)) / 3600));
}

function set_remaining(frm) {
	frm.set_value("outstanding_amount", flt(frm.doc.total_amount) - flt(frm.doc.paid_amount));
}
