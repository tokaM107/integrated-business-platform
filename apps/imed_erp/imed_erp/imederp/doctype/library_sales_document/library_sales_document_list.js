// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The library documents list: a band of today's figures and the connector's heartbeat above the list (in the
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

	function render(listview, s) {
		const net = flt(s.sales_value - s.returns_value, 2);
		const beat = heartbeat(s.last_synced_at);
		const html = `<div class="imed-ov-kpis imed-lib-band">
				${tile("green", "shopping-cart", __("Sales today"), esc(money(s.sales_value, s.currency)), esc(__("{0} invoices", [s.sales_count])))}
				${tile("red", "undo-2", __("Returns today"), esc(money(s.returns_value, s.currency)), esc(__("{0} returns", [s.returns_count])))}
				${tile("teal", "wallet", __("Net today"), esc(money(net, s.currency)), esc(__("Sales less returns")))}
				${tile(beat.tone, "wifi", __("Library connection"), `<span class="imed-lib-beat ${beat.live ? "is-live" : ""}"></span>${esc(beat.state)}`, beat.note, "imed-lib-kpi--beat")}
			</div>`;
		let $band = listview.page.main.find(".imed-lib-band");
		if ($band.length) $band.replaceWith(html);
		else listview.page.main.prepend(html);
	}

	// The library the list is filtered to (the sidebar's "Azarita Invoices" / "Mawasah Invoices"), if one.
	function library_of(listview) {
		const f = listview.filter_area.get().find((x) => x[1] === "cost_center" && x[2] === "=");
		return f ? f[3] : null;
	}

	function load(listview, force) {
		const now = Date.now();
		const library = library_of(listview);
		// A change of library refetches at once; otherwise at most every REFETCH_MS.
		if (!force && library === listview.__imed_lib_for && listview.__imed_lib_at && now - listview.__imed_lib_at < REFETCH_MS) return;
		listview.__imed_lib_at = now;
		listview.__imed_lib_for = library;
		frappe
			.xcall("imed_erp.imederp.doctype.library_sales_document.library_sales_document.list_summary", { cost_center: library })
			.then((s) => render(listview, s))
			.catch(() => listview.page.main.find(".imed-lib-band").remove());
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
		},
	};
})();
