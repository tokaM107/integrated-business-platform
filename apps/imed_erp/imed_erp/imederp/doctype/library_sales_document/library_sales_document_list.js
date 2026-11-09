// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The library documents list: a band of the figures of the dates it shows (today's when it shows them all) and the connector's heartbeat above the list (in the
// Owner Dashboard's tinted cards), each row's state in its colour, the kind as a coloured pill and the amount
// signed by the way the money went (a return in red). Look only: the list's columns and filters are unchanged.
(() => {
	const KIND_TONE = {
		"Retail Sale": "green",
		"Wholesale Sale": "teal",
		"Retail Return": "red",
		"Wholesale Return": "red",
		Purchase: "blue",
		"Purchase Return": "orange",
	};
	// The connector runs every 10 minutes: under 25 minutes it is live, under 2 hours late, beyond that stopped.
	const LIVE_MINUTES = 25;
	const LATE_MINUTES = 120;
	const REFETCH_MS = 20 * 1000;

	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	const money = (v, currency) => format_currency(v || 0, currency, 0);

	function tile(tone, icon, label, value, note, extra_class = "") {
		return `<section class="imed-ov-kpi imed-lib-kpi tone-${tone} ${extra_class}">
				<div class="imed-ov-kpi__top">
					<span class="imed-ov-kpi__icon">${frappe.utils.icon(icon, "md")}</span>
					<span class="imed-ov-kpi__label">${esc(label)}</span>
				</div>
				<b class="imed-ov-kpi__value imed-ov-num">${value}</b>
				<span class="imed-lib-kpi__note">${note}</span>
			</section>`;
	}

	function heartbeat(at) {
		if (!at) return { tone: "gray", state: __("Not connected yet"), note: __("No document has arrived from the library") };
		const minutes = (Date.now() - frappe.datetime.str_to_obj(at).getTime()) / 60000;
		const when = esc(frappe.datetime.prettyDate(at));
		if (minutes <= LIVE_MINUTES) return { tone: "green", state: __("Connected"), note: __("Last update {0}", [when]), live: true };
		if (minutes <= LATE_MINUTES) return { tone: "amber", state: __("Late"), note: __("Last update {0}", [when]) };
		return { tone: "red", state: __("Stopped"), note: __("Last update {0}: is the connector window open on the library PC?", [when]) };
	}

	// The dates the list shows, as words: "from 01-10-2026 to 09-10-2026", "on 07-10-2026", "this week".
	const user_day = (d) => `\u2066${frappe.datetime.str_to_user(String(d).slice(0, 10))}\u2069`;
	function period_words(f) {
		if (!f) return __("Today");
		const [op, v] = [String(f[0]).toLowerCase(), f[1]];
		if (op === "timespan") return __(frappe.utils.to_title_case ? frappe.utils.to_title_case(String(v)) : String(v));
		if (op === "between" && Array.isArray(v)) {
			const [a, b] = [String(v[0]).slice(0, 10), String(v[1]).slice(0, 10)];
			return a === b ? __("On {0}", [user_day(a)]) : __("From {0} to {1}", [user_day(a), user_day(b)]);
		}
		if (op === ">=" || op === ">") return __("From {0}", [user_day(v)]);
		if (op === "<=" || op === "<") return __("Up to {0}", [user_day(v)]);
		return __("On {0}", [user_day(v)]);
	}

	function render(listview, s, f) {
		const net = flt(s.sales_value - s.returns_value, 2);
		const beat = heartbeat(s.last_synced_at);
		const today = s.is_today;
		const when = esc(period_words(f));
		const html = `<div class="imed-lib-band-wrap">
				<div class="imed-lib-period">${frappe.utils.icon("calendar-days", "sm")}<span>${esc(__("Revenue"))}</span><b>${when}</b></div>
				<div class="imed-ov-kpis imed-lib-band">
				${tile("green", "shopping-cart", today ? __("Sales today") : __("Sales"), esc(money(s.sales_value, s.currency)), esc(__("{0} invoices", [s.sales_count])))}
				${tile("red", "undo-2", today ? __("Returns today") : __("Returns"), esc(money(s.returns_value, s.currency)), esc(__("{0} returns", [s.returns_count])))}
				${tile("teal", "wallet", today ? __("Net today") : __("Net"), esc(money(net, s.currency)), esc(__("Sales less returns")))}
				${tile(beat.tone, "wifi", __("Library connection"), `<span class="imed-lib-beat ${beat.live ? "is-live" : ""}"></span>${esc(beat.state)}`, beat.note, "imed-lib-kpi--beat")}
				</div>
			</div>`;
		let $band = listview.page.main.find(".imed-lib-band-wrap");
		if ($band.length) $band.replaceWith(html);
		else listview.page.main.prepend(html);
	}

	// The list's date filter as [condition, value] (the bar above the table, a chip, a link), or null for every date.
	function dates_of(listview) {
		const f = listview.filter_area.get().find((x) => x[1] === "reg_date");
		return f ? [f[2], f[3]] : null;
	}

	// The library the list is filtered to (the sidebar's "Azarita Invoices" / "Mawasah Invoices"), if one.
	function library_of(listview) {
		const f = listview.filter_area.get().find((x) => x[1] === "cost_center" && x[2] === "=");
		return f ? f[3] : null;
	}

	// The sidebar's "فواتير الأزاريطة" and "فواتير المواساة" open this list filtered to their library, but Frappe
	// drops the filter from the address and lit the last of them whatever the list showed (the owner, 5 Nov 2026):
	// the item of the library the list is filtered to is lit here, after each refresh; none when it shows both.
	function light_sidebar(listview) {
		const library = library_of(listview);
		const $links = $(".body-sidebar a[href]").filter((_, a) => /^\/desk\/library-sales-document(\/|\?|$)/.test(a.getAttribute("href") || ""));
		if (!$links.length) return;
		const $hit = $links.filter((_, a) => new URL(a.getAttribute("href"), window.location.origin).searchParams.get("cost_center") === library).first();
		$(".body-sidebar .active-sidebar").removeClass("active-sidebar");
		if ($hit.length) {
			$hit.parent().addClass("active-sidebar");
			if (frappe.app && frappe.app.sidebar) frappe.app.sidebar.active_item = $hit.parent();
		}
	}
	// Lit here, so unlit here: on leaving the list, its items lose the light Frappe does not know it gave them.
	function unlight_on_leave() {
		if (unlight_on_leave.bound || !frappe.router || !frappe.router.on) return;
		unlight_on_leave.bound = true;
		frappe.router.on("change", () => {
			if (frappe.get_route()[1] === "Library Sales Document") return;
			$(".body-sidebar a[href]")
				.filter((_, a) => /^\/desk\/library-sales-document(\/|\?|$)/.test(a.getAttribute("href") || ""))
				.parent()
				.removeClass("active-sidebar");
		});
	}

	function load(listview, force) {
		const now = Date.now();
		const library = library_of(listview);
		const dates = dates_of(listview);
		const key = JSON.stringify([library, dates]);
		// A change of library or of dates refetches at once; otherwise at most every REFETCH_MS.
		if (!force && key === listview.__imed_lib_for && listview.__imed_lib_at && now - listview.__imed_lib_at < REFETCH_MS) return;
		listview.__imed_lib_at = now;
		listview.__imed_lib_for = key;
		frappe
			.xcall("imed_erp.imederp.doctype.library_sales_document.library_sales_document.list_summary", {
				cost_center: library,
				date_filter: dates ? JSON.stringify(dates) : null,
			})
			.then((s) => {
				// Only the answer for what the list still shows (the dates may have changed meanwhile).
				if (listview.__imed_lib_for === key) render(listview, s, dates);
			})
			.catch(() => listview.page.main.find(".imed-lib-band-wrap").remove());
	}

	// The day with its weekday and, under it, the time the cashier saved the invoice (mappers.day_and_time). A
	// document read before the time was sent stays at 00:00: its day alone.
	function day(value) {
		const d = frappe.datetime.str_to_obj(value);
		if (!d || isNaN(d)) return esc(value);
		const lang = frappe.boot.lang || "en";
		const has_time = d.getHours() || d.getMinutes() || d.getSeconds();
		const time = has_time ? `<i dir="ltr">${esc(d.toLocaleTimeString(lang, { hour: "numeric", minute: "2-digit" }))}</i>` : "";
		return `<span class="imed-lib-day"><b>${esc(d.toLocaleDateString(lang, { day: "numeric", month: "short", year: "numeric" }))}</b><small>${esc(d.toLocaleDateString(lang, { weekday: "long" }))}${time}</small></span>`;
	}

	// Quick filters inside the filter card: a period and a kind, one click each, the active one filled.
	const DOCTYPE = "Library Sales Document";
	const PERIODS = [
		["", "layers", __("All")],
		["today", "sun", __("Today")],
		["yesterday", "history", __("Yesterday")],
		["this week", "calendar-range", __("This Week")],
		["this month", "calendar-days", __("This Month")],
	];
	const KINDS = [
		["", "layers", __("All kinds")],
		["sales", "shopping-cart", __("Sales")],
		["returns", "undo-2", __("Returns")],
		["cancelled", "ban", __("Cancelled")],
	];
	const SALES = ["Retail Sale", "Wholesale Sale"];
	const RETURNS = ["Retail Return", "Wholesale Return"];

	function current(listview) {
		const f = listview.filter_area.get();
		const period = (f.find((x) => x[1] === "reg_date" && x[2] === "Timespan") || [])[3] || "";
		const kind_f = f.find((x) => x[1] === "document_kind");
		const kind = f.some((x) => x[1] === "is_cancelled" && String(x[3]) === "1")
			? "cancelled"
			: kind_f && JSON.stringify(kind_f[3]) === JSON.stringify(SALES)
			? "sales"
			: kind_f && JSON.stringify(kind_f[3]) === JSON.stringify(RETURNS)
			? "returns"
			: "";
		return { period, kind };
	}

	function chips(group, items, active) {
		return `<div class="imed-lib-quick__group" role="group" data-group="${group}">
				${items
					.map(([value, icon, label]) => `<button type="button" class="imed-lib-chip ${value === active ? "is-active" : ""}" data-value="${esc(value)}">${frappe.utils.icon(icon, "xs")}<span>${esc(label)}</span></button>`)
					.join("")}
			</div>`;
	}

	function render_quick(listview) {
		const form = listview.page.page_form;
		if (!form || !form.length) return;
		const now = current(listview);
		const html = `<div class="imed-lib-quick">
				<span class="imed-lib-quick__title">${frappe.utils.icon("sliders-horizontal", "sm")}${esc(__("Show"))}</span>
				${chips("period", PERIODS, now.period)}
				<span class="imed-lib-quick__sep"></span>
				${chips("kind", KINDS, now.kind)}
			</div>`;
		const $old = form.find(".imed-lib-quick");
		if ($old.length) $old.replaceWith(html);
		else form.prepend(html);
	}

	async function apply(listview, group, value) {
		const area = listview.filter_area;
		if (group === "period") {
			await area.remove("reg_date");
			if (value) await area.add([[DOCTYPE, "reg_date", "Timespan", value]]);
		} else {
			await area.remove("document_kind");
			await area.remove("is_cancelled");
			if (value === "sales") await area.add([[DOCTYPE, "document_kind", "in", SALES], [DOCTYPE, "is_cancelled", "=", 0]]);
			if (value === "returns") await area.add([[DOCTYPE, "document_kind", "in", RETURNS], [DOCTYPE, "is_cancelled", "=", 0]]);
			if (value === "cancelled") await area.add([[DOCTYPE, "is_cancelled", "=", 1]]);
		}
		render_quick(listview);
	}

	frappe.listview_settings["Library Sales Document"] = {
		add_fields: ["document_kind", "is_final", "is_cancelled", "status_name", "money_direction", "total", "cost_center"],
		// The internal name (LIB-2026-...) says nothing here: the library's own number is the title.
		hide_name_column: true,
		formatters: {
			reg_date(value) {
				return value ? day(value) : "";
			},
			// The cost center without the company's abbreviation: "مكتبة الأزاريطة".
			cost_center(value) {
				if (!value) return `<span class="text-muted">—</span>`;
				return `<span class="imed-lib-place">${frappe.utils.icon("store", "xs")}${esc(value.replace(/\s+-\s+[^-]+$/, ""))}</span>`;
			},
			// The list's own Status column, as a coloured pill: issued green, cancelled red, anything else (under
			// issue, held) orange.
			status_name(value, df, doc) {
				const color = cint(doc.is_cancelled) ? "red" : cint(doc.is_final) ? "green" : "orange";
				return `<span class="indicator-pill ${color} imed-lib-state">${esc(value || __("Not issued yet"))}</span>`;
			},
			document_kind(value) {
				if (!value) return "";
				return `<span class="imed-lib-kind tone-${KIND_TONE[value] || "gray"}">${esc(__(value))}</span>`;
			},
			total(value, df, doc) {
				const out = doc.money_direction === "Out";
				const amount = format_currency(flt(value), frappe.defaults.get_default("currency"), 2);
				// Left to right inside, so the minus stays in front of the amount in the Arabic (RTL) page.
				return `<span class="imed-lib-amount ${out ? "is-out" : ""} ${cint(doc.is_cancelled) ? "is-void" : ""}" dir="ltr">${out && flt(value) ? "− " : ""}${esc(amount)}</span>`;
			},
		},
		onload(listview) {
			load(listview, true);
			render_quick(listview);
			listview.page.page_form.on("click", ".imed-lib-chip", function () {
				const $chip = $(this);
				apply(listview, $chip.closest("[data-group]").data("group"), String($chip.data("value") || ""));
			});
			// The heartbeat's "minutes ago" ages while the page stays open: fetched again every minute while shown.
			clearInterval(listview.__imed_lib_timer);
			listview.__imed_lib_timer = setInterval(() => {
				if (frappe.get_route()[1] === "Library Sales Document") load(listview);
			}, 60 * 1000);
		},
		refresh(listview) {
			load(listview);
			// Filters also change from the filter button or a column click: the chips follow them.
			render_quick(listview);
			light_sidebar(listview);
			unlight_on_leave();
		},
	};
})();
