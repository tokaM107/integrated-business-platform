// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// Booking (HAL-02, STU-01, STU-08). The checks, the price and the money are on the server (booking.py,
// booking_pricing.py, booking_accounts.py); this only helps the screen (docs/SCREEN_DESIGN_STANDARD.md):
//   - a card on top: on a new booking, the three steps; on a saved one, its total, paid and remaining, its status
//     and what to do next;
//   - the actions as buttons (Confirm Booking, Reschedule, Mark Completed, No Show, Cancel Booking), so nobody has
//     to know which status comes after which;
//   - on a hall, the fields the booking's type needs and no others (apply_layout), and whether the hall is free as
//     the day and times are typed (check_availability, the same rule as the save);
//   - the worked-out and technical fields stay in the collapsed sections below (booking.json).
//
// An IMED hall booking posts nothing when completed (27 Oct 2026): its invoice, or the collected amount of a
// revenue share, is posted by the explicit button once the amounts were checked (booking_accounts.py).

// The calendar's colours (booking_calendar.js), so a status looks the same everywhere.
const BOOKING_STATUS_COLORS = {
	Tentative: "orange",
	Confirmed: "green",
	"Confirmed with Deposit": "green",
	Completed: "blue",
	Cancelled: "gray",
	"No Show": "gray",
};
const BOOKING_OPEN = ["Tentative", "Confirmed", "Confirmed with Deposit"];

// What each hall booking type fixes (booking.py FORCED_MODEL) and which of the optional fields it needs.
const HALL_TYPES = {
	"Internal Course or Lecture": { model: "Not Billable", choose_model: true, fields: ["doctor", "course", "expected_attendees", "capacity"] },
	"External Lecturer": { model: null, choose_model: true, fields: ["doctor", "expected_attendees", "capacity"] },
	"Fixed-fee Rental": { model: "Fixed Rent", fields: ["expected_attendees", "capacity"] },
	"Revenue Share": { model: "Revenue Share", fields: ["doctor", "expected_attendees", "capacity"] },
	"Internal Meeting": { model: "Not Billable", fields: ["expected_attendees", "capacity"] },
	"Maintenance Block": { model: "Not Billable", fields: [] },
};
const HALL_OPTIONAL = ["doctor", "course", "expected_attendees", "capacity"];
const STUDIO_ONLY = ["hour_package", "package_hours", "extra_hours", "bill_extra_hours", "extra_hours_approved_by"];
const MONEY_SECTIONS = ["extras_section", "price_section", "amounts_section"];

frappe.ui.form.on("Booking", {
	setup(frm) {
		frm.set_query("resource", () => ({ filters: { disabled: 0 } }));
		frm.set_query("package", () => ({ filters: { resource: frm.doc.resource || "", disabled: 0 } }));
		// The teacher's own prepaid hours of this studio service, still active.
		frm.set_query("hour_package", () => ({
			filters: { customer: frm.doc.customer || "", resource: frm.doc.resource || "", docstatus: 1, status: ["in", ["Active", "Used Up"]] },
		}));
		frm.set_query("extra", "extras", () => ({
			filters: {
				disabled: 0,
				applies_to: ["in", ["Hall and Studio", frm.doc.resource_type || ""]],
			},
		}));
		frm.set_query("lecturer", () => ({ filters: { disabled: 0 } }));
	},

	refresh(frm) {
		imed.screen.apply(frm, { collapse: ["details_section", "source_section"] });
		apply_layout(frm);
		show_card(frm);
		show_availability(frm);
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
		// The type of what was chosen, before the server fills it on save: the hall's fields show at once.
		if (!frm.doc.resource) {
			frm.doc.resource_type = null;
			apply_layout(frm);
			return;
		}
		frappe.db.get_value("Booking Resource", frm.doc.resource, ["resource_type", "capacity"]).then((r) => {
			if (!r.message) return;
			frm.doc.resource_type = r.message.resource_type;
			frm.doc.capacity = cint(r.message.capacity);
			frm.refresh_field("capacity");
			apply_layout(frm);
			show_card(frm);
			check_availability(frm);
		});
	},
	booking_date: (frm) => check_availability(frm),
	from_time(frm) {
		set_hours(frm);
		check_availability(frm);
	},
	to_time(frm) {
		set_hours(frm);
		check_availability(frm);
	},
	hall_booking_type(frm) {
		const kind = HALL_TYPES[frm.doc.hall_booking_type];
		if (kind) {
			// The model the type fixes; where the type leaves a choice, it is asked on the form.
			if (kind.model) frm.set_value("rental_model", kind.model);
			else if (!["Fixed Rent", "Revenue Share"].includes(frm.doc.rental_model)) frm.set_value("rental_model", null);
			if (frm.doc.hall_booking_type === "Maintenance Block") {
				frm.set_value({ customer: null, doctor: null, course: null, expected_attendees: 0 });
				if (!frm.doc.activity) frm.set_value("activity", __("Maintenance"));
			}
		}
		apply_layout(frm);
	},
	rental_model: (frm) => apply_layout(frm),
	doctor(frm) {
		// The doctor is a customer: the lecture is billed to them unless another renter is named (booking.py).
		if (frm.doc.doctor && !frm.doc.customer) frm.set_value("customer", frm.doc.doctor);
	},
	attendees: (frm) => set_shares(frm),
	admission_price: (frm) => set_shares(frm),
	collected_amount: (frm) => set_shares(frm),
	lecturer_share_percent: (frm) => set_shares(frm),
});

function set_hours(frm) {
	if (!frm.doc.from_time || !frm.doc.to_time) return;
	const seconds = (t) => t.split(":").reduce((total, part) => total * 60 + flt(part), 0);
	let length = (seconds(frm.doc.to_time) - seconds(frm.doc.from_time)) / 3600;
	// An end earlier than the start is the next day (booking.py check_times).
	if (length < 0) length += 24;
	frm.set_value("hours", length);
}

// ---------- The fields a hall booking needs, and no others ----------

function apply_layout(frm) {
	const doc = frm.doc;
	const hall = doc.resource_type === "Hall";
	const kind = hall ? HALL_TYPES[doc.hall_booking_type] : null;
	const not_billable = hall && doc.rental_model === "Not Billable";
	const maintenance = hall && doc.hall_booking_type === "Maintenance Block";
	const show = (fields, on) => fields.forEach((f) => frm.fields_dict[f] && frm.toggle_display(f, !!on));

	show(STUDIO_ONLY, !hall);
	show(["hall_section"], hall);
	// The type first; the rest of the hall's fields once it is chosen.
	show(["activity"], !hall || !!kind);
	show(["responsible_name", "responsible_phone"], !hall || (!!kind && !maintenance));
	if (hall) {
		HALL_OPTIONAL.forEach((f) => frm.toggle_display(f, !!kind && kind.fields.includes(f)));
		// The capacity is shown once the hall has one (booking_resource.js says when it has none).
		frm.toggle_display("capacity", !!kind && kind.fields.includes("capacity") && cint(doc.capacity) > 0);
		// The rental model where the type leaves a choice; a hall with no type yet is asked nothing else.
		frm.toggle_display("rental_model", !!kind && !!kind.choose_model);
	}
	// A customer: the renter, or the doctor's own record; an internal use or a maintenance block names none.
	show(["customer"], !hall || (!!kind && !not_billable) || (!!doc.customer && !maintenance));
	// The money: nothing to show on an internal use or a maintenance block; the revenue share where it applies.
	show(MONEY_SECTIONS, !not_billable);
	show(["revenue_share_section"], doc.rental_model === "Revenue Share");
	if (frm.fields_dict.amounts_section) frm.toggle_display("amounts_section", !not_billable && (!frm.is_new() || flt(doc.total_amount) > 0));
}

// ---------- Is it free? (as the day and times are typed) ----------

function check_availability(frm) {
	const doc = frm.doc;
	frm.imed_availability = null;
	if (!(doc.resource && doc.booking_date && doc.from_time && doc.to_time) || doc.source === "Imported") {
		show_availability(frm);
		return;
	}
	const key = [doc.resource, doc.booking_date, doc.from_time, doc.to_time].join("|");
	frm.imed_availability_key = key;
	frm.imed_availability = { state: "checking" };
	show_availability(frm);
	frappe.call({
		method: "imed_erp.imederp.doctype.booking.booking.check_availability",
		type: "GET",
		args: { resource: doc.resource, booking_date: doc.booking_date, from_time: doc.from_time, to_time: doc.to_time, name: frm.is_new() ? null : doc.name },
		callback(r) {
			if (frm.imed_availability_key !== key || !r.message) return;
			frm.imed_availability = { state: r.message.free ? "free" : "taken", message: r.message.message, booking: r.message.booking };
			show_availability(frm);
		},
		error() {
			if (frm.imed_availability_key !== key) return;
			frm.imed_availability = null;
			show_availability(frm);
		},
	});
}

function show_availability(frm) {
	const a = frm.imed_availability;
	const field = frm.fields_dict.summary_html;
	if (!field) return;
	field.$wrapper.find(".imed-booking-availability").remove();
	if (!a || !BOOKING_OPEN.includes(frm.doc.status || "Tentative")) return;
	const kind = { checking: "is-checking", free: "is-free", taken: "is-taken" }[a.state];
	const text = a.state === "checking" ? __("Checking whether it is free…") : a.message;
	const link = a.booking && frappe.model.can_read("Booking") ? ` <a href="/desk/booking/${encodeURIComponent(a.booking)}">${esc(a.booking)}</a>` : "";
	$(`<div class="imed-booking-availability ${kind}">${esc(text)}${link}</div>`).appendTo(field.$wrapper);
	inject_css();
}

function inject_css() {
	if (document.getElementById("imed-booking-form-css")) return;
	$(`<style id="imed-booking-form-css">
		.imed-booking-availability { margin: 0 0 var(--margin-md); padding: 8px 12px; border-radius: var(--border-radius-md); font-weight: 500; }
		.imed-booking-availability.is-checking { background: var(--bg-light-gray); color: var(--text-muted); }
		.imed-booking-availability.is-free { background: var(--bg-green); color: var(--text-on-green); }
		.imed-booking-availability.is-taken { background: var(--bg-red); color: var(--text-on-red); }
	</style>`).appendTo("head");
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
		__("Choose the hall (or the studio service)."),
		__("Set the day, the start and the end time: you are told at once whether it is free."),
		__("Choose the booking type and its purpose, name the doctor or the renter, then Save: the price is worked out by itself."),
		__("Then Confirm the booking; Reschedule or Cancel it from the same buttons when needed."),
	];
	return `<div class="imed-booking-card imed-booking-steps">
		<div class="imed-booking-title">${esc(__("New booking, step by step"))}</div>
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
	const not_billable = doc.resource_type === "Hall" && doc.rental_model === "Not Billable";
	const tile = (label, value, kind = "") =>
		`<div class="imed-booking-tile ${kind}"><div class="imed-booking-tile-label">${esc(label)}</div>
		<div class="imed-booking-tile-value">${esc(value)}</div></div>`;

	const tiles = [
		share ? tile(__("Rent"), __("None: revenue share")) : tile(__("Booking Price"), money(doc.base_amount)),
		tile(__("Extras"), money(doc.extras_amount)),
		tile(__("Total"), money(doc.total_amount), "is-total"),
		tile(__("Paid"), money(doc.paid_amount)),
		// QA-35: a cancelled booking or a no-show owes nothing more; what was paid is the deposit kept.
		["Cancelled", "No Show"].includes(doc.status)
			? tile(__("Deposit held"), flt(doc.paid_amount) ? money(doc.paid_amount) : __("Nothing paid"))
			: tile(
					__("Remaining"),
					money(doc.outstanding_amount),
					flt(doc.outstanding_amount) > 0 ? "is-due" : "is-done"
			  ),
	];
	if (doc.source === "Imported") {
		// The booking system's amounts: only the total, paid and remaining mean something here.
		tiles.splice(0, 2);
	}
	if (not_billable) {
		// An internal use of the hall: nothing is priced, so no figures; the hours and the type say what it is.
		tiles.splice(0, tiles.length, tile(__("Fee"), __("None (not billable)")), tile(__("Hours"), flt(doc.hours)), tile(__("Booking Type"), __(doc.hall_booking_type || "")));
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
			<span class="imed-booking-what">${esc(doc.resource || "")}${doc.activity ? esc(" · " + doc.activity) : ""}</span>
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
	} else if (doc.status === "Confirmed") {
		text = __("Confirmed by the halls' staff (no deposit). Next: when the session is over, press Mark Completed.");
	} else if (doc.status === "Confirmed with Deposit") {
		kind = "is-todo";
		text = __("Confirmed. Next: when the booking is over, press Mark Completed: its invoice is made and the deposit taken off it.");
	} else if (doc.status === "Completed") {
		const share = hall && doc.rental_model === "Revenue Share";
		if (hall && doc.rental_model === "Not Billable") {
			kind = "is-done";
			text = __("Completed. An internal use of the hall: nothing is invoiced.");
		} else if (share && !doc.journal_entry) {
			kind = "is-due";
			text = __("Completed. The collected amount is not posted yet: check the attendees, the collected amount and the lecturer's share, then press Post the Collected Amount.");
		} else if (hall && !doc.sales_invoice && flt(doc.total_amount) > 0) {
			kind = "is-due";
			text = __("Completed. Its invoice is not made yet: check the price, then press Make Invoice.");
		} else if (!doc.sales_invoice && flt(doc.total_amount) > 0) {
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
		frm.add_custom_button(__("Reschedule"), () => reschedule(frm));
		frm.add_custom_button(__("Cancel Booking"), () => cancel_booking(frm), __("More"));
	}
	// IMED's halls take no deposit: the halls' staff confirm a booking; that is not a payment.
	if (doc.resource_type === "Hall" && doc.status === "Tentative" && doc.source === "Manual") {
		frm.add_custom_button(__("Confirm Booking"), () => set_status(frm, "Confirmed")).addClass("btn-primary");
	}
	// Completed and not posted yet: on a hall this is the one step that posts (27 Oct 2026); on the studio the
	// invoice is made on completion, and this remakes one that was cancelled.
	const share = doc.resource_type === "Hall" && doc.rental_model === "Revenue Share";
	const unposted = (!doc.sales_invoice && flt(doc.total_amount) > 0) || (share && !doc.journal_entry);
	if (doc.status === "Completed" && unposted && doc.rental_model !== "Not Billable") {
		const label = share && !doc.journal_entry ? __("Post the Collected Amount") : __("Make Invoice");
		frm.add_custom_button(label, () => post_booking(frm)).addClass("btn-primary");
	}
}

function post_booking(frm) {
	const doc = frm.doc;
	const share = doc.resource_type === "Hall" && doc.rental_model === "Revenue Share";
	const message = share
		? __("The amount collected ({0}) goes into the cash box and is shared with the lecturer ({1}%). Make sure the attendees, the collected amount and the lecturer's share are right.", [money(doc.collected_amount), flt(doc.lecturer_share_percent)])
		: __("The booking's invoice of {0} is made, and its deposit taken off it.", [money(doc.total_amount)]);
	frappe.confirm(`${esc(__("Post this booking's money now?"))}<br><br>${esc(message)}`, () =>
		frappe.call({
			method: "imed_erp.imederp.booking_accounts.make_booking_invoice",
			args: { booking: doc.name },
			freeze: true,
			callback: () => frm.reload_doc(),
		})
	);
}

function set_status(frm, status, values = {}) {
	frm.set_value({ status, ...values }).then(() => frm.save());
}

function mark_completed(frm) {
	const doc = frm.doc;
	let message;
	if (doc.rental_model === "Not Billable") {
		message = __("Nothing is invoiced: an internal use of the hall.");
	} else if (doc.resource_type === "Hall") {
		// A hall posts nothing here: the next step is explicit (post_booking).
		message = __("Nothing is posted yet. Next, check the amounts and press {0}.", [doc.rental_model === "Revenue Share" ? __("Post the Collected Amount") : __("Make Invoice")]);
	} else if (doc.rental_model === "Revenue Share") {
		message = __("The amount collected ({0}) goes into the cash box and is shared with the lecturer. Make sure the attendees, the collected amount and the lecturer's share are right.", [money(doc.collected_amount)]);
	} else {
		message = __("The booking's invoice of {0} is made, and its deposit taken off it.", [money(doc.total_amount)]);
	}
	frappe.confirm(`${esc(__("Mark this booking completed?"))}<br><br>${esc(message)}`, () => set_status(frm, "Completed"));
}

function reschedule(frm) {
	// The new day and times are saved through the form, where the overlap check runs (never by dragging).
	frappe.prompt(
		[
			{ fieldname: "booking_date", fieldtype: "Date", label: __("Booking Date"), reqd: 1, default: frm.doc.booking_date },
			{ fieldname: "from_time", fieldtype: "Time", label: __("Start Time"), reqd: 1, default: frm.doc.from_time },
			{ fieldname: "to_time", fieldtype: "Time", label: __("End Time"), reqd: 1, default: frm.doc.to_time, description: __("An end earlier than the start means the next day.") },
		],
		(values) => frm.set_value(values).then(() => frm.save()),
		__("Reschedule"),
		__("Save the new time")
	);
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
