// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The Booking calendar (HAL-10, STU-02; Bookings > Calendar): Frappe's own calendar view, opened on a week, with Day
// and Week (and Month) to switch and arrows to move. Bookings come from booking.get_events, which reads them as the
// Bookings list does, so each user sees only the bookings they may read; the list's filters (a resource, a status)
// apply here too.
//
// Each booking shows its resource, customer and status, by colour: a booking that holds its time is solid, a
// cancelled one or a no-show (which free their time) faded and struck through. Bookings at the same time sit side by
// side, so an occupied slot is seen at once; two of the same resource overlapping (refused on saving, so only from a
// change made around it) are red. Bookings are moved on their form, where the overlap check runs, not by dragging.

const BOOKING_COLORS = {
	Tentative: "orange",
	"Confirmed with Deposit": "green",
	Completed: "blue",
	Cancelled: "gray",
	"No Show": "gray",
};

const aspect_ratio = () => (window.innerWidth < 768 ? 0.6 : 1.35);

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
			].filter(Boolean);
			return event;
		});
	},

	setup_options(defaults) {
		frappe.views.Calendar.prototype.setup_options.call(this, defaults);
		const me = this;
		Object.assign(this.cal_options, {
			initialView: ["timeGridDay", "timeGridWeek"].includes(defaults.initialView)
				? defaults.initialView
				: "timeGridWeek",
			editable: false,
			slotEventOverlap: false,
			scrollTime: "08:00:00",
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
				info.el.title = [
					p.resource,
					p.customer,
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
		this.$state = $('<div class="imed-booking-state text-muted small px-4 pt-2"></div>').insertBefore(this.$cal);
		this.$legend = $('<div class="imed-booking-legend small px-4 pt-2"></div>')
			.html(
				Object.entries(BOOKING_COLORS)
					.map(
						([status, color]) =>
							`<span class="mr-3"><span class="indicator-pill ${color}">${__(status)}</span></span>`
					)
					.concat(`<span class="indicator-pill red">${__("Overlap")}</span>`)
					.join("")
			)
			.insertBefore(this.$cal);
		this.show_state();
		if (!document.getElementById("imed-booking-calendar-css")) {
			$(`<style id="imed-booking-calendar-css">
				.imed-booking-free { opacity: 0.55; text-decoration: line-through; }
				.imed-booking-conflict { box-shadow: inset 3px 0 0 var(--red-500); font-weight: 600; }
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
	},
};
