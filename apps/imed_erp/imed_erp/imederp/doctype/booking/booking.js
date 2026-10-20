// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// Booking (HAL-02, STU-01, STU-08). The checks, the price and the money are on the server (booking.py,
// booking_pricing.py, booking_accounts.py); this only helps the screen.
frappe.ui.form.on("Booking", {
	setup(frm) {
		frm.set_query("resource", () => ({ filters: { disabled: 0 } }));
		frm.set_query("package", () => ({ filters: { resource: frm.doc.resource || "", disabled: 0 } }));
		frm.set_query("extra", "extras", () => ({
			filters: {
				disabled: 0,
				applies_to: ["in", ["Hall and Studio", frm.doc.resource_type || ""]],
			},
		}));
		frm.set_query("lecturer", () => ({ filters: { disabled: 0 } }));
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
			return;
		}
		show_amounts(frm);
		add_buttons(frm);
	},

	resource(frm) {
		frm.set_value("package", null);
	},
	from_time: (frm) => set_hours(frm),
	to_time: (frm) => set_hours(frm),
	attendees: (frm) => set_shares(frm),
	admission_price: (frm) => set_shares(frm),
	collected_amount: (frm) => set_shares(frm),
	lecturer_share_percent: (frm) => set_shares(frm),
});

function set_hours(frm) {
	if (!frm.doc.from_time || !frm.doc.to_time) return;
	const seconds = (t) => t.split(":").reduce((total, part) => total * 60 + flt(part), 0);
	frm.set_value("hours", Math.max(0, (seconds(frm.doc.to_time) - seconds(frm.doc.from_time)) / 3600));
}

// What the server will work out, shown as it is typed; the server's figures are the ones kept.
function set_shares(frm) {
	frm.set_value("expected_revenue", cint(frm.doc.attendees) * flt(frm.doc.admission_price));
	const lecturer = flt((flt(frm.doc.collected_amount) * flt(frm.doc.lecturer_share_percent)) / 100, 2);
	frm.set_value("lecturer_share", lecturer);
	frm.set_value("center_share", flt(frm.doc.collected_amount) - lecturer);
}

function show_amounts(frm) {
	if (frm.is_new()) return;
	// One line, drawn again on every refresh (indicators would pile up).
	const money = (value) => format_currency(value, frappe.defaults.get_default("currency"));
	const owed = flt(frm.doc.outstanding_amount) > 0;
	frm.dashboard.clear_headline();
	// QA-35: a cancelled booking or a no-show owes nothing more; what was paid is the deposit kept.
	if (["Cancelled", "No Show"].includes(frm.doc.status)) {
		frm.dashboard.set_headline_alert(
			flt(frm.doc.paid_amount) ? __("Deposit held {0}", [money(frm.doc.paid_amount)]) : __("Nothing paid"),
			"gray"
		);
		return;
	}
	frm.dashboard.set_headline_alert(
		[
			__("Total {0}", [money(frm.doc.total_amount)]),
			__("Paid {0}", [money(frm.doc.paid_amount)]),
			__("Remaining {0}", [money(frm.doc.outstanding_amount)]),
		].join(" · "),
		owed ? "orange" : "green"
	);
}

function add_buttons(frm) {
	if (frm.is_new() || frm.is_dirty() || !frm.perm[0].write) return;
	const open = !["Cancelled", "No Show"].includes(frm.doc.status);
	// A hall takes no deposit: it is paid once its invoice is made.
	const can_pay = frm.doc.resource_type !== "Hall" || frm.doc.sales_invoice;
	if (open && can_pay && flt(frm.doc.outstanding_amount) > 0) {
		frm.add_custom_button(
			frm.doc.sales_invoice ? __("Record Payment") : __("Record Deposit"),
			() => record_payment(frm)
		);
	}
	if (frm.doc.status === "Completed" && !frm.doc.sales_invoice && flt(frm.doc.total_amount) > 0) {
		frm.add_custom_button(__("Make Invoice"), () =>
			frappe.call({
				method: "imed_erp.imederp.booking_accounts.make_booking_invoice",
				args: { booking: frm.doc.name },
				freeze: true,
				callback: () => frm.reload_doc(),
			})
		);
	}
}

function record_payment(frm) {
	// One id per dialog: the same click sent twice records one payment (booking_accounts.record_payment).
	const request_id = frappe.utils.get_random(20);
	const dialog = new frappe.ui.Dialog({
		title: frm.doc.sales_invoice ? __("Record Payment") : __("Record Deposit"),
		fields: [
			{
				fieldname: "amount",
				fieldtype: "Currency",
				label: __("Amount"),
				reqd: 1,
				default: frm.doc.outstanding_amount,
				description: __("At most {0}.", [format_currency(frm.doc.outstanding_amount)]),
			},
			{
				fieldname: "mode_of_payment",
				fieldtype: "Link",
				label: __("Mode of Payment"),
				options: "Mode of Payment",
				description: __("Empty: cash into {0}. A wallet (InstaPay, Vodafone Cash) needs its transaction number.", [
					frm.doc.treasury || "",
				]),
			},
			{ fieldname: "reference_no", fieldtype: "Data", label: __("Transaction Number") },
		],
		primary_action_label: __("Record"),
		primary_action(values) {
			dialog.disable_primary_action();
			frappe.call({
				method: "imed_erp.imederp.booking_accounts.record_payment",
				args: { booking: frm.doc.name, request_id, ...values },
				freeze: true,
				callback(r) {
					dialog.hide();
					frappe.show_alert({ message: __("Recorded: {0}", [r.message]), indicator: "green" });
					frm.reload_doc();
				},
				always: () => dialog.enable_primary_action(),
			});
		},
	});
	dialog.show();
}
