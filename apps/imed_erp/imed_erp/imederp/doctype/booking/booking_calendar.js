// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The Booking calendar (HAL-10, STU-02; Bookings > Calendar): Frappe's own calendar view, opened on a week, with Day
// and Week (and Month) to switch and arrows to move. Bookings come from booking.get_events, which reads them as the
// Bookings list does, so each user sees only the bookings they may read; the list's filters (a resource, a status)
// apply here too.
//
// Each booking shows its hall, purpose, doctor or customer and type (booking.get_events), and its status by colour:
// a booking that holds its time is solid, a cancelled one or a no-show (which free their time) faded and struck
// through, a maintenance block hatched. The list's filters (hall, status, dates) apply here too, and the sidebar
// opens it on the halls or on the studio (?resource_type=...). Bookings at the same time sit side by
// side, so an occupied slot is seen at once; two of the same resource overlapping (refused on saving, so only from a
// change made around it) are red. Bookings are moved on their form, where the overlap check runs, not by dragging.

const BOOKING_COLORS = (frappe.boot.imed_booking || {}).colors || {}; // booking_rules.py, sent at login

const aspect_ratio = () => (window.innerWidth < 768 ? 0.6 : 1.35);

// The look (the owner, 4 Nov 2026: "not nice at all"; theme §33): a header with the calendar's name and the week's
// figures, each booking a card in its status's colour (time, hall or service, doctor or customer, status), day
// headers with the date in a circle and today filled, no all-day row (a booking always has hours).
const CALENDAR_KINDS = {
	Hall: ["presentation", __("Hall Calendar")],
	"Studio Service": ["clapperboard", __("Studio Calendar")],
};
const esc_cal = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

function calendar_kind() {
	const type = new URLSearchParams(window.location.search).get("resource_type");
	return CALENDAR_KINDS[type] || ["calendar-days", __("Bookings Calendar")];
}

function event_card(arg) {
	const p = arg.event.extendedProps;
	const who = p.doctor || p.customer || "";
	const kind = p.hall_booking_type && p.hall_booking_type !== "Maintenance Block" ? __(p.hall_booking_type) : "";
	return {
		html: `<div class="imed-ev">
				<span class="imed-ev__time" dir="ltr">${esc_cal(arg.timeText)}</span>
				<b class="imed-ev__what">${esc_cal(p.resource || arg.event.title)}</b>
				${who ? `<span class="imed-ev__who">${esc_cal(who)}</span>` : ""}
				<span class="imed-ev__foot"><span class="imed-ev__status">${esc_cal(p.hall_booking_type === "Maintenance Block" ? __("Maintenance") : __(p.status))}</span>${kind ? `<span class="imed-ev__kind">${esc_cal(kind)}</span>` : ""}</span>
			</div>`,
	};
}

function day_header(arg) {
	const lang = frappe.boot.lang || "en";
	const narrow = arg.view.type === "dayGridMonth" || (arg.view.type === "timeGridWeek" && window.innerWidth < 768);
	const weekday = arg.date.toLocaleDateString(lang, { weekday: narrow ? "short" : "long" });
	if (arg.view.type === "dayGridMonth") return { html: `<span class="imed-dh__day">${esc_cal(weekday)}</span>` };
	return {
		html: `<span class="imed-dh ${arg.isToday ? "is-today" : ""}">
				<span class="imed-dh__day">${esc_cal(weekday)}</span>
				<b class="imed-dh__num">${esc_cal(arg.date.toLocaleDateString(lang, { day: "numeric" }))}</b>
			</span>`,
	};
}

frappe.views.calendar["Booking"] = {
	field_map: {
		id: "name",
		start: "start",
		end: "end",
		title: "title",
		allDay: "all_day",
		convertToUserTz: "convert_to_user_tz",
	},
	get_events_method: "imed_erp.imederp.doctype.booking.booking.get_events",

	get_css_class(event) {
		return event.conflict ? "red" : BOOKING_COLORS[event.status] || "blue";
	},

	prepare_events(events) {
		return frappe.views.Calendar.prototype.prepare_events.call(this, events).map((event) => {
			event.editable = false;
			event.classNames = [
				event.holding ? "imed-booking-holding" : "imed-booking-free",
					event.conflict ? "imed-booking-conflict" : "",
					event.hall_booking_type === "Maintenance Block" ? "imed-booking-maintenance" : "",
				].filter(Boolean);
			return event;
		});
	},

	setup_options(defaults) {
		frappe.views.Calendar.prototype.setup_options.call(this, defaults);
		const me = this;
		Object.assign(this.cal_options, {
			// A phone opens on one day: a week of seven columns is too narrow to read there.
			initialView: window.innerWidth < 768
				? "timeGridDay"
				: ["timeGridDay", "timeGridWeek"].includes(defaults.initialView)
				? defaults.initialView
				: "timeGridWeek",
			editable: false,
			slotEventOverlap: false,
			scrollTime: "08:00:00",
			allDaySlot: false,
			nowIndicator: true,
			// In Arabic the calendar reads right to left (the owner, 4 Nov 2026): the hours on the right, the week's
			// first day (Saturday) on the right, the arrows the right way round.
			direction: frappe.utils.is_rtl() ? "rtl" : "ltr",
			dayMaxEvents: 3,
			eventContent: event_card,
			dayHeaderContent: day_header,
			// On a phone the calendar's usual shape leaves a few hours showing: taller than wide there.
			aspectRatio: aspect_ratio(),
			windowResize: () => me.fullCalendar.setOption("aspectRatio", aspect_ratio()),
			events(info, success, failure) {
				frappe.call({
					method: me.get_events_method,
					type: "GET",
					args: me.get_args(info.start, info.end),
					callback(r) {
						me.load_failed = false;
						success(me.prepare_events(r.message || []));
					},
					error() {
						me.load_failed = true;
						failure(new Error("bookings not loaded"));
					},
				});
			},
			// The calendar fetches a range once and moves inside it without fetching again (a day of a week already
			// read): what it says is worked out from the day or week shown, after every move and every fetch.
			loading(is_loading) {
				me.is_loading = is_loading;
				me.show_state();
			},
			datesSet: () => me.show_state(),
			eventsSet: () => me.show_state(),
			eventDidMount(info) {
				const p = info.event.extendedProps;
				// The card's colour: its status's (booking_rules.py), red for an overlap, from Frappe's palette.
				const color = p.conflict ? "red" : BOOKING_COLORS[p.status] || "blue";
				info.el.style.setProperty("--ev", `var(--${color}-500)`);
				info.el.style.setProperty("--ev-fg", `var(--${color}-700)`);
				info.el.style.setProperty("--ev-on-dark", `var(--${color}-300)`);
					info.el.title = [
						p.resource,
						p.hall_booking_type ? __(p.hall_booking_type) : "",
						p.doctor || p.customer,
					frappe.datetime.str_to_user(info.event.startStr.slice(0, 10)),
					`${info.event.startStr.slice(11, 16)} – ${info.event.endStr.slice(11, 16)}`,
					__(p.status),
					p.conflict ? __("Overlaps another booking of {0}", [p.resource]) : "",
				]
					.filter(Boolean)
					.join("\n");
			},
			// Selecting free time opens a new booking on that day and those hours.
			select(info) {
				// Someone who may only read bookings is not sent to a form that would refuse them.
				if (!frappe.model.can_create("Booking")) return;
				const values = { booking_date: moment(info.start).format("YYYY-MM-DD") };
				if (!info.allDay) {
					values.from_time = moment(info.start).format("HH:mm:ss");
					values.to_time = moment(info.end).format("HH:mm:ss");
				}
				frappe.new_doc("Booking", values);
			},
		});
	},

	make() {
		frappe.views.Calendar.prototype.make.call(this);
		frappe.utils.set_footnote(this.footnote_area, this.$wrapper, __("Select free time to book it."));
		this.$wrapper.addClass("imed-cal");
		const [icon, name] = calendar_kind();
		// The header: the calendar's name, the figures of the days shown (show_state), the colours' legend.
		this.$head = $(`<div class="imed-cal-head">
				<div class="imed-cal-head__title"><span class="imed-cal-head__icon">${frappe.utils.icon(icon, "md")}</span><h3>${esc_cal(name)}</h3></div>
				<div class="imed-cal-head__stats"></div>
			</div>`).insertBefore(this.$cal);
		this.$state = $('<div class="imed-booking-state text-muted small"></div>').insertBefore(this.$cal);
		this.$legend = $('<div class="imed-booking-legend"></div>')
			.html(
				Object.entries(BOOKING_COLORS)
					.map(([status, color]) => `<span class="imed-cal-key" style="--ev: var(--${color}-500)">${esc_cal(__(status))}</span>`)
					.concat(`<span class="imed-cal-key imed-booking-maintenance" style="--ev: var(--gray-500)">${esc_cal(__("Maintenance"))}</span>`)
					.concat(`<span class="imed-cal-key" style="--ev: var(--red-500)">${esc_cal(__("Overlap"))}</span>`)
					.join("")
			)
			.appendTo(this.$head);
		this.show_state();
		if (!document.getElementById("imed-booking-calendar-css")) {
			$(`<style id="imed-booking-calendar-css">
				.imed-booking-free { opacity: 0.55; text-decoration: line-through; }
					.imed-booking-conflict { border-inline-start: 3px solid var(--red-500); font-weight: 600; }
					.imed-booking-maintenance { background-image: repeating-linear-gradient(135deg, transparent 0 6px, rgba(0,0,0,0.12) 6px 12px); }
				.imed-booking-legend .indicator-pill { margin-bottom: 4px; }
				@media (max-width: 767px) {
					#fc-calendar-wrapper .fc-header-toolbar { flex-wrap: wrap; gap: 8px; }
				}
			</style>`).appendTo("head");
		}
	},

	show_state() {
		if (!this.$state || !this.fullCalendar) return;
		const view = this.fullCalendar.view;
		let state = null;
		if (this.is_loading) state = "loading";
		else if (this.load_failed) state = "error";
		else if (!this.fullCalendar.getEvents().some((e) => e.start < view.activeEnd && e.end > view.activeStart))
			state = "empty";
		const messages = {
			loading: __("Loading bookings…"),
			empty: view.type === "timeGridDay" ? __("No bookings on this day.") : __("No bookings in this period."),
			error: __("The bookings could not be loaded. Move to another day and back, or reload the page."),
		};
		this.$state.toggleClass("text-danger", state === "error").text(messages[state] || "");
		this.show_stats();
	},

	// The days shown: how many bookings hold their time, how many hours, how many still tentative.
	show_stats() {
		if (!this.$head || !this.fullCalendar) return;
		const view = this.fullCalendar.view;
		const shown = this.fullCalendar
			.getEvents()
			.filter((e) => e.start < view.activeEnd && e.end > view.activeStart && e.extendedProps.holding && e.extendedProps.hall_booking_type !== "Maintenance Block");
		const hours = shown.reduce((sum, e) => sum + (e.end - e.start) / 3600000, 0);
		const tentative = shown.filter((e) => e.extendedProps.status === "Tentative").length;
		const stat = (icon, value, label, cls = "") =>
			`<span class="imed-cal-stat ${cls}">${frappe.utils.icon(icon, "sm")}<b>${esc_cal(value)}</b><small>${esc_cal(label)}</small></span>`;
		this.$head.find(".imed-cal-head__stats").html(
			stat("calendar-check", format_number(shown.length, null, 0), __("bookings")) +
				stat("clock", format_number(hours, null, hours % 1 ? 1 : 0), __("hours")) +
				(tentative ? stat("hourglass", format_number(tentative, null, 0), __("tentative"), "is-warn") : "")
		);
	},
};
