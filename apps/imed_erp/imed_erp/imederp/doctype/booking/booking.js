// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// Booking (HAL-02, STU-01, STU-08). The checks, the price and the money are on the server (booking.py,
// booking_pricing.py, booking_accounts.py); this only helps the screen (docs/SCREEN_DESIGN_STANDARD.md):
//   - a card on top: on a new booking, the three steps; on a saved one, its total, paid and remaining, its status
//     and what to do next;
//   - the actions as buttons (Record Deposit, Mark Completed, No Show, Cancel Booking), so nobody has to know
//     which status comes after which;
//   - the worked-out and technical fields stay in the collapsed sections below (booking.json).

// The calendar's colours (booking_calendar.js), so a status looks the same everywhere.
const BOOKING_STATUS_COLORS = {
	Tentative: "orange",
	"Confirmed with Deposit": "green",
	Completed: "blue",
	Cancelled: "gray",
	"No Show": "gray",
};
const BOOKING_OPEN = ["Tentative", "Confirmed with Deposit"];

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
		imed.screen.apply(frm, {});
		show_card(frm);
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

// ---------- The card on top ----------

const esc = (value) => frappe.utils.escape_html(value == null ? "" : String(value));
const money = (value) => format_currency(flt(value), frappe.defaults.get_default("currency"));

function show_card(frm) {
	const field = frm.fields_dict.summary_html;
	if (!field) return;
	field.$wrapper.html(frm.is_new() ? steps_html() : card_html(frm));
}

function steps_html() {
	const steps = [
		__("Choose the hall or service, and the customer."),
		__("Set the day and the time. A hall also needs its activity, the person responsible and the rental model."),
		__("Add a package or extras if there are any, then Save: the price is worked out by itself."),
	];
	return `<div class="imed-booking-card imed-booking-steps">
		<div class="imed-booking-title">${esc(__("New booking in three steps"))}</div>
		<ol>${steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
	</div>`;
}

function card_html(frm) {
	const doc = frm.doc;
	const color = BOOKING_STATUS_COLORS[doc.status] || "gray";
	const when = [
		doc.booking_date ? frappe.datetime.str_to_user(doc.booking_date) : "",
		doc.from_time && doc.to_time ? `${doc.from_time.slice(0, 5)} – ${doc.to_time.slice(0, 5)}` : "",
	]
		.filter(Boolean)
		.join(" · ");
	const share = doc.rental_model === "Revenue Share";
	const tile = (label, value, kind = "") =>
		`<div class="imed-booking-tile ${kind}"><div class="imed-booking-tile-label">${esc(label)}</div>
		<div class="imed-booking-tile-value">${esc(value)}</div></div>`;

	const tiles = [
		share ? tile(__("Rent"), __("None: revenue share")) : tile(__("Booking Price"), money(doc.base_amount)),
		tile(__("Extras"), money(doc.extras_amount)),
		tile(__("Total"), money(doc.total_amount), "is-total"),
		tile(__("Paid"), money(doc.paid_amount)),
		tile(
			__("Remaining"),
			money(doc.outstanding_amount),
			flt(doc.outstanding_amount) > 0 ? "is-due" : "is-done"
		),
	];
	if (doc.source === "Imported") {
		// The booking system's amounts: only the total, paid and remaining mean something here.
		tiles.splice(0, 2);
	}

	let shares = "";
	if (share) {
		const percent = flt(doc.lecturer_share_percent)
			? tile(__("Lecturer's Share ({0}%)", [flt(doc.lecturer_share_percent)]), money(doc.lecturer_share))
			: tile(__("Lecturer's Share"), __("% not set yet"), "is-due");
		shares = `<div class="imed-booking-subtitle">${esc(__("Collected from the attendees"))}</div>
		<div class="imed-booking-tiles">
			${tile(__("Expected"), money(doc.expected_revenue))}
			${tile(__("Collected"), money(doc.collected_amount), "is-total")}
			${percent}
			${tile(__("Center's Share"), money(doc.center_share))}
		</div>`;
	}

	return `<div class="imed-booking-card">
		<div class="imed-booking-head">
			<span class="indicator-pill ${color}">${esc(__(doc.status))}</span>
			<span class="imed-booking-what">${esc(doc.resource || "")}</span>
			<span class="imed-booking-when">${esc(when)}</span>
		</div>
		<div class="imed-booking-tiles">${tiles.join("")}</div>
		${shares}
		${next_step_html(frm)}
	</div>`;
}

function next_step_html(frm) {
	const doc = frm.doc;
	if (doc.source === "Imported") return "";
	const hall = doc.resource_type === "Hall";
	const link = (doctype, name) =>
		name && frappe.model.can_read(doctype)
			? ` <a href="/desk/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${esc(name)}</a>`
			: "";
	let text, kind;
	if (doc.status === "Tentative") {
		kind = "is-todo";
		text = hall
			? __("Next: when the booking is over, press Mark Completed. A hall takes no deposit; it is paid after that.")
			: __("Next: record the customer's deposit (Record Deposit) to confirm the booking.");
	} else if (doc.status === "Confirmed with Deposit") {
		kind = "is-todo";
		text = __("Confirmed. Next: when the booking is over, press Mark Completed: its invoice is made and the deposit taken off it.");
	} else if (doc.status === "Completed") {
		if (!doc.sales_invoice && flt(doc.total_amount) > 0) {
			kind = "is-due";
			text = __("Completed, but its invoice was cancelled: press Make Invoice.");
		} else if (flt(doc.outstanding_amount) > 0) {
			kind = "is-due";
			text = __("Completed. {0} is still to be paid: press Record Payment.", [money(doc.outstanding_amount)]);
		} else {
			kind = "is-done";
			text = __("Completed and paid in full.");
		}
	} else if (doc.status === "Cancelled") {
		kind = "is-off";
		text = __("Cancelled: {0}", [doc.cancellation_reason || ""]);
		if (flt(doc.paid_amount) > 0) {
			text += " " + __("The deposit of {0} stays with the customer until the accountant pays it back.", [money(doc.paid_amount)]);
		}
	} else {
		kind = "is-off";
		text = __("The customer did not come.");
	}
	const documents = link("Sales Invoice", doc.sales_invoice) + link("Journal Entry", doc.journal_entry);
	return `<div class="imed-booking-next ${kind}">${esc(text)}${documents}</div>`;
}

// ---------- The actions ----------

function add_buttons(frm) {
	if (frm.is_new() || frm.is_dirty() || !frm.perm[0].write) return;
	const doc = frm.doc;
	const open = BOOKING_OPEN.includes(doc.status);
	const started = doc.booking_date && doc.from_time && frappe.datetime.str_to_obj(`${doc.booking_date} ${doc.from_time}`) <= new Date();

	// A hall takes no deposit: it is paid once its invoice is made.
	const can_pay = doc.resource_type !== "Hall" || doc.sales_invoice;
	if (!["Cancelled", "No Show"].includes(doc.status) && can_pay && flt(doc.outstanding_amount) > 0) {
		frm.add_custom_button(doc.sales_invoice ? __("Record Payment") : __("Record Deposit"), () => record_payment(frm));
	}
	if (open && started) {
		frm.add_custom_button(__("Mark Completed"), () => mark_completed(frm));
		frm.add_custom_button(__("No Show"), () => set_status(frm, "No Show"), __("More"));
	}
	if (open) {
		frm.add_custom_button(__("Cancel Booking"), () => cancel_booking(frm), __("More"));
	}
	if (doc.status === "Completed" && !doc.sales_invoice && flt(doc.total_amount) > 0) {
		frm.add_custom_button(__("Make Invoice"), () =>
			frappe.call({
				method: "imed_erp.imederp.booking_accounts.make_booking_invoice",
				args: { booking: doc.name },
				freeze: true,
				callback: () => frm.reload_doc(),
			})
		);
	}
}

function set_status(frm, status, values = {}) {
	frm.set_value({ status, ...values }).then(() => frm.save());
}

function mark_completed(frm) {
	const doc = frm.doc;
	const message =
		doc.rental_model === "Revenue Share"
			? __("The amount collected ({0}) goes into the cash box and is shared with the lecturer. Make sure the attendees, the collected amount and the lecturer's share are right.", [money(doc.collected_amount)])
			: __("The booking's invoice of {0} is made, and its deposit taken off it.", [money(doc.total_amount)]);
	frappe.confirm(`${esc(__("Mark this booking completed?"))}<br><br>${esc(message)}`, () => set_status(frm, "Completed"));
}

function cancel_booking(frm) {
	frappe.prompt(
		[{ fieldname: "reason", fieldtype: "Small Text", label: __("Why is it cancelled?"), reqd: 1 }],
		(values) => set_status(frm, "Cancelled", { cancellation_reason: values.reason }),
		__("Cancel Booking"),
		__("Cancel Booking")
	);
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
