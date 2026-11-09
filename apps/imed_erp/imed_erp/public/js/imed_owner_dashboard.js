// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The Owner Dashboard's look (owner's request of 21 Oct 2026: "more creative and easy on the eye"). It only adds and
// marks elements on Frappe's own workspace: a welcome band on top, yesterday's figures under it (5.1), an icon and a
// meaning (in, out, attention...) on each money card, negative amounts marked, the approvals calm when nothing waits.
// The figures themselves are the server's (imederp/owner_figures.py, imederp/owner_yesterday.py,
// setup/setup_dashboard.py). Styles: imed_theme.css §22 and §25. Loaded by hooks.py.
(() => {
	const ROUTE = "Workspaces/Owner Dashboard";
	const on_dashboard = () => document.body.dataset.route === ROUTE;
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

	// Each card by its label (the Number Card's, translated as Frappe shows it): its icon and what it means.
	//   in: money coming in · out: money going out · due: owed, to follow · count: not money
	const CARDS = {
		"Cash in the Cash Boxes": ["wallet", "cash"],
		"Revenue This Month": ["trending-up", "in"],
		"Expenses This Month": ["trending-down", "out"],
		"Net This Month": ["scale", "net"],
		"Owed to Us": ["hand-coins", "due"],
		"We Owe": ["receipt", "owe"],
		"Platform Fees This Month": ["smartphone", "in"],
		"Collected from Doctors This Month": ["hand-coins", "in"],
		"Cash Shortages This Month": ["triangle-alert", "out"],
		"Open Cash Discrepancies": ["scale", "due"],
		"Studio Bookings This Month": ["clapperboard", "count"],
		"Studio Hours This Month": ["clock", "count"],
		"Hall Bookings This Month": ["presentation", "count"],
		"Unpaid on Bookings": ["hourglass", "due"],
		"Due on Studio Bookings (XStudio)": ["clapperboard", "due"],
	};
	// The cards read from the ledger (owner_figures.py): zero for lack of any record is said on them.
	const LEDGER_CARDS = ["Cash in the Cash Boxes", "Revenue This Month", "Expenses This Month", "Net This Month", "Owed to Us", "We Owe"];
	// The section headers are written in Arabic on the workspace (setup_dashboard.py).
	const HEADERS = {
		"محتاج موافقتك": "bell-ring",
		الفلوس: "coins",
		الحجوزات: "calendar-days",
		"الإيرادات والمخزون": "chart-line",
	};

	const by_title = () => {
		const map = {};
		for (const [label, value] of Object.entries(CARDS)) map[__(label)] = value;
		return map;
	};

	function greeting() {
		const hour = new Date().getHours();
		if (hour < 12) return [__("Good morning"), "sunrise"];
		if (hour < 18) return [__("Good afternoon"), "sun"];
		return [__("Good evening"), "moon"];
	}

	function add_welcome($page) {
		if ($page.find(".imed-dash-welcome").length) return;
		// Before the workspace's editor, not among its blocks, so its edit mode is untouched.
		const $editor = $page.find(".codex-editor").first();
		if (!$editor.length) return;
		const [hello, icon] = greeting();
		const name = (frappe.session.user_fullname || "").trim();
		const today = new Date().toLocaleDateString(frappe.boot.lang || "en", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
		$(`<div class="imed-dash-welcome">
				<div class="imed-dash-welcome__text">
					<div class="imed-dash-welcome__date">${frappe.utils.icon(icon, "sm")}<span>${esc(today)}</span></div>
					<h1>${esc(name ? __("{0}, {1}", [hello, name]) : hello)}</h1>
					<p class="imed-dash-welcome__note"></p>
				</div>
				<div class="imed-dash-welcome__art" aria-hidden="true">${frappe.utils.icon("piggy-bank", "lg")}</div>
			</div>`).insertBefore($page.find(".imed-slot-top").first().length ? $page.find(".imed-slot-top").first() : $editor);
	}

	function mark_headers($page) {
		$page.find(".ce-header").each(function () {
			const $h = $(this);
			if ($h.find(".imed-dash-head-icon").length) return;
			const icon = HEADERS[$h.text().trim()];
			if (!icon) return;
			$h.addClass("imed-dash-head").prepend(`<span class="imed-dash-head-icon">${frappe.utils.icon(icon, "sm")}</span>`);
		});
	}

	// The list each custom card opens when clicked (a Frappe "Custom" card opens nothing by itself).
	function card_route(label) {
		const month = ["Between", [frappe.datetime.month_start(), frappe.datetime.month_end()]];
		const held = ["not in", ["Cancelled", "No Show"]];
		const studio = { resource_type: "Studio Service", booking_date: month, status: held };
		switch (label) {
			case "Studio Bookings This Month":
			case "Studio Hours This Month":
				return ["Booking", studio];
			case "Hall Bookings This Month":
				return ["Booking", { resource_type: "Hall", booking_date: month, status: held }];
			case "Due on Studio Bookings (XStudio)":
				return ["Booking", { source_system: "xstudio", resource_type: "Studio Service", booking_date: month, status: held, xstudio_amount_due: [">", 0] }];
			case "Unpaid on Bookings":
				return ["Booking", { status: ["in", ["Confirmed with Deposit", "Completed"]], booking_date: ["<=", frappe.datetime.get_today()], outstanding_amount: [">", 0] }];
			case "Owed to Us":
				return ["Sales Invoice", { docstatus: 1, outstanding_amount: [">", 0] }];
			case "We Owe":
				return ["Purchase Invoice", { docstatus: 1, outstanding_amount: [">", 0] }];
			case "Cash in the Cash Boxes":
				// The report the chart under it draws, one row per cash box (there is no "Treasury" list: that route
				// opened an empty "not found" page; audit of 1 Nov 2026).
				return ["query-report", "Cash Box Balances"];
			default:
				return null;
		}
	}

	function mark_cards($page) {
		const map = by_title();
		$page.find(".widget.number-widget-box").each(function () {
			const $card = $(this);
			const title = $card.find(".widget-title").first().text().trim();
			const entry = map[title];
			if (entry && !$card.attr("data-imed-kind")) {
				$card.attr("data-imed-kind", entry[1]).addClass("imed-dash-card");
				$card.find(".widget-label").first().prepend(`<span class="imed-dash-card-icon">${frappe.utils.icon(entry[0], "md")}</span>`);
				const label = Object.keys(CARDS).find((key) => __(key) === title);
				const route = card_route(label);
				if (route) {
					$card.addClass("imed-dash-card-link").attr("title", __("Open the list")).on("click", (e) => {
						if ($(e.target).closest(".widget-control, .dropdown").length) return;
						open_route(route);
					});
				}
			}
			// On a site with no ledger entry at all, each money card says "no records yet" next to its zero
			// (decision of 1 Nov 2026); the badge is put back whenever Frappe redraws the card.
			const is_ledger_card = LEDGER_CARDS.some((label) => __(label) === title);
			if (ledger_empty && is_ledger_card && !$card.find(".imed-dash-norecords").length) {
				$card.find(".widget-label, .widget-title").first().append(`<span class="imed-dash-norecords">${esc(__("no records yet"))}</span>`);
			}
			// A negative amount (cash short, a month at a loss) shows in red; it changes when the card reloads.
			const value = $card.find(".number").first().text();
			$card.toggleClass("is-negative", /-\s*[\d٠-٩]/.test(value));
		});
	}

	function mark_approvals($page) {
		let waiting = 0;
		let seen = 0;
		$page.find(".widget.shortcut-widget-box").each(function () {
			const $box = $(this);
			const text = $box.find(".indicator-pill").first().text();
			if (!text) return;
			seen += 1;
			const count = parseInt((text.match(/[\d٠-٩]+/) || ["0"])[0].replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d)), 10) || 0;
			waiting += count;
			$box.addClass("imed-dash-approval").toggleClass("is-waiting", count > 0).toggleClass("is-clear", count === 0);
		});
		const note = !seen
			? ""
			: waiting
			? __("{0} waiting for your approval.", [waiting])
			: __("Nothing waits for your approval. Here is where the money stands.");
		$page.find(".imed-dash-welcome__note").text(note);
	}

	// ---------------- Yesterday (requirements 5.1; imederp/owner_yesterday.py) ----------------
	// Under the welcome band: each business's money, the bookings, the app's fees, the printing and the systems, for
	// the day before. Fetched when the dashboard opens, again after five minutes away.
	const REFRESH_MS = 30 * 1000; // the live state: fetched again on every visit after half a minute
	let yesterday = null;
	let ledger_empty = false; // no GL entry on the site at all: the money cards' zeros are "no records yet"
	let fetched_at = 0;
	let fetching = false;

	const money = (value, currency) => format_currency(value || 0, currency);
	const number = (value) => format_number(value || 0, null, 0);
	// Hours keep their half (2.5 h was shown as "2 h"; audit of 1 Nov 2026).
	const hours_text = (value) => __("{0} h", [format_number(value || 0, null, (value || 0) % 1 ? 1 : 0)]);
	const tone = (value) => (value > 0 ? "is-positive" : value < 0 ? "is-negative" : "");

	// Each card and figure in its colour (imed_theme.css §27): a card by its icon, a figure by what it counts. A
	// figure not named here takes the brand's teal.
	const CARD_TONES = {
		"chart-column": "tone-green",
		"calendar-days": "tone-blue",
		presentation: "tone-violet",
		smartphone: "tone-cyan",
		printer: "tone-amber",
		plug: "tone-purple",
	};
	const STAT_TONES = Object.fromEntries(
		[
			["tone-blue", ["Held", "Booked", "Bookings", "Studio hours booked"]],
			["tone-cyan", ["Hours today", "Hours", "Charged today"]],
			["tone-green", ["Completed", "Studio hours delivered", "Paid in XStudio", "Occupied now", "Collected today", "Sheets sold"]],
			["tone-red", ["Cancelled"]],
			["tone-amber", ["No Show", "Due in XStudio", "Fixed rents (not yet invoiced)", "Still owed by doctors", "Difference"]],
			["tone-violet", ["Booked today (any date)", "Next 7 days", "Revenue shares", "New students"]],
			["tone-blue", ["Sheets printed"]],
			["tone-gray", ["Hall resources", "Active halls"]],
		].flatMap(([tone, labels]) => labels.map((label) => [__(label), tone]))
	);

	function card(icon, title, body, extra_class = "") {
		return `<section class="imed-yday-card ${CARD_TONES[icon] || "tone-teal"} ${extra_class}">
				<h3>${frappe.utils.icon(icon, "sm")}<span>${esc(title)}</span></h3>
				${body}
			</section>`;
	}

	// The day's revenue and expenses by business: names and figures only (the owner, 5 Nov 2026: no notes, no English).
	function money_card(data) {
		const c = data.currency;
		const rows = data.money.rows
			.filter((row) => row.revenue || row.expenses)
			.map(
				(row) => `<tr class="${row.revenue || row.expenses ? "" : "is-quiet"}">
					<td>${esc(row.external ? __("X Studio (XStudio)") : row.business)}</td>
					<td class="is-num">${whole(row.revenue, c)}</td>
					<td class="is-num">${whole(row.expenses, c)}</td>
					<td class="is-num ${tone(row.net)}">${whole(row.net, c)}</td>
				</tr>`
			)
			.join("");
		const t = data.money.total;
		return `<section class="imed-sec">
				<header class="imed-sec__head"><h2>${frappe.utils.icon("chart-column", "sm")}<span>${esc(__("Today's revenue and expenses by business"))}</span></h2></header>
				${rows ? `<div class="imed-table-wrap"><table class="imed-yday-table">
					<thead><tr><th>${esc(__("Business"))}</th><th class="is-num">${esc(__("Revenue"))}</th>
						<th class="is-num">${esc(__("Expenses"))}</th><th class="is-num">${esc(__("Net"))}</th></tr></thead>
					<tbody>${rows}</tbody>
					<tfoot><tr><td>${esc(__("Total"))}</td><td class="is-num">${whole(t.revenue, c)}</td>
						<td class="is-num">${whole(t.expenses, c)}</td><td class="is-num ${tone(t.net)}">${whole(t.net, c)}</td></tr></tfoot>
				</table></div>` : `<p class="imed-sec__empty">${esc(__("No revenue or expenses today yet."))}</p>`}
			</section>`;
	}

	// Every figure opens the list behind it: route = [doctype, filters] (a Frappe list view with those filters).
	function stat(label, value, cls = "", route = null) {
		cls = `${STAT_TONES[label] || "tone-teal"} ${cls}`;
		const inner = `<span>${esc(label)}</span><b>${value}</b>`;
		return route
			? `<a class="imed-yday-stat imed-yday-link ${cls}" href="#" data-route="${esc(JSON.stringify(route))}" title="${esc(__("Open the list"))}">${inner}</a>`
			: `<div class="imed-yday-stat ${cls}">${inner}</div>`;
	}

	const open_route = (route) =>
		route[0] === "query-report" ? frappe.set_route("query-report", route[1]) : frappe.set_route("List", route[0], route[1]);
	const HELD = ["not in", ["Cancelled", "No Show"]];

	function bookings_card(b, day, currency) {
		const list = (resource_type, status) => ["Booking", { booking_date: day, resource_type, status }];
		// What XStudio never reported (a completed booking, a payment) is said so, never shown as 0 (decision of
		// 1 Nov 2026): the studio's bookings come from XStudio, where the staff do not record these yet.
		const tracks = b.xstudio_tracks || { completion: true, payments: true };
		const untracked = `<span class="imed-yday-untracked">${esc(__("Not tracked in XStudio"))}</span>`;
		const kind = (title, s, resource_type, studio = false) =>
			`<div class="imed-yday-sub">${esc(title)}</div>
			<div class="imed-yday-stats">
				${stat(__("Held"), number(s.held), "", list(resource_type, HELD))}
				${studio && !tracks.completion ? stat(__("Completed"), untracked, "is-untracked") : stat(__("Completed"), number(s.completed), "", list(resource_type, "Completed"))}
				${stat(__("Cancelled"), number(s.cancelled), s.cancelled ? "is-warning" : "", list(resource_type, "Cancelled"))}
				${studio && !tracks.completion ? stat(__("No Show"), untracked, "is-untracked") : stat(__("No Show"), number(s.no_show), s.no_show ? "is-warning" : "", list(resource_type, "No Show"))}
			</div>`;
		const hours = hours_text(b.studio_hours_booked);
		const delivered = tracks.completion ? hours_text(b.studio_hours_delivered) : untracked;
		const made = ["Booking", { creation: ["Between", [`${day} 00:00:00`, `${day} 23:59:59`]] }];
		// The same statuses the server counts (owner_yesterday.OPEN_STATUSES; "Confirmed" was missing: audit of 1 Nov 2026).
		const open = ["Booking", { booking_date: day, status: ["in", ["Tentative", "Confirmed", "Confirmed with Deposit"]], source_system: ["is", "not set"] }];
		return card(
			"calendar-days",
			__("Halls and studio"),
			`${kind(__("Halls"), b.halls, "Hall")}${kind(__("Studio"), b.studio, "Studio Service", true)}
			<div class="imed-yday-stats">
				${stat(__("Studio hours booked"), hours, "", list("Studio Service", HELD))}
				${tracks.completion ? stat(__("Studio hours delivered"), delivered, "", list("Studio Service", "Completed")) : stat(__("Studio hours delivered"), untracked, "is-untracked")}
				${stat(__("Booked today (any date)"), number(b.made_yesterday), "", made)}
			</div>
			<div class="imed-yday-sub">${esc(__("The studio's money, as XStudio says it (not posted here)"))}</div>
			<div class="imed-yday-stats">
				${stat(__("Due in XStudio"), money(b.xstudio_due, currency), b.xstudio_due ? "is-negative" : "", ["Booking", { booking_date: day, source_system: "xstudio", status: HELD, xstudio_amount_due: [">", 0] }])}
				${tracks.payments ? stat(__("Paid in XStudio"), money(b.xstudio_paid, currency), b.xstudio_paid ? "is-positive" : "", ["Booking", { booking_date: day, source_system: "xstudio", xstudio_amount_paid: [">", 0] }]) : stat(__("Paid in XStudio"), untracked, "is-untracked")}
			</div>
			${
				b.still_open
					? `<p class="imed-yday-warn"><a href="#" class="imed-yday-link" data-route="${esc(JSON.stringify(open))}">${esc(
							__("{0} booking(s) of today are neither completed nor cancelled.", [b.still_open])
					  )}</a></p>`
					: ""
			}`
		);
	}

	// IMED's lecture halls, apart from the studio's rooms and from XStudio: today, the week ahead, what needs action.
	function halls_card(h, currency) {
		const day = frappe.datetime.get_today();
		const held = ["not in", ["Cancelled", "No Show"]];
		const hall = (extra) => ["Booking", Object.assign({ resource_type: "Hall" }, extra)];
		const month = ["Between", [frappe.datetime.month_start(), frappe.datetime.month_end()]];
		if (h.configured === false) {
			// No hall of type Hall is set up yet (decision of 1 Nov 2026: say so, never zeros; XStudio's rooms are not halls).
			return card(
				"presentation",
				__("IMED hall bookings"),
				`<p class="imed-yday-warn">${esc(__("Not configured yet: no IMED hall is set up as a booking resource. The figures appear once the halls, their capacities and prices are entered."))}</p>
				${stat(__("Hall resources"), number(h.active_halls), "", ["Booking Resource", { resource_type: "Hall" }])}`
			);
		}
		return card(
			"presentation",
			__("IMED hall bookings"),
			`<div class="imed-yday-sub">${esc(__("Today"))}</div>
			<div class="imed-yday-stats">
				${stat(__("Booked"), number(h.today.held), "", hall({ booking_date: day, status: held }))}
				${stat(__("Completed"), number(h.today.completed), "", hall({ booking_date: day, status: "Completed" }))}
				${stat(__("Cancelled"), number(h.today.cancelled), h.today.cancelled ? "is-warning" : "", hall({ booking_date: day, status: "Cancelled" }))}
				${stat(__("Hours today"), hours_text(h.today_hours), "", hall({ booking_date: day, status: held }))}
			</div>
			<div class="imed-yday-stats">
				${stat(__("Next 7 days"), number(h.upcoming), "", hall({ booking_date: ["Between", [frappe.datetime.add_days(day, 1), frappe.datetime.add_days(day, 7)]], status: held }))}
				${stat(__("Active halls"), number(h.active_halls), "", ["Booking Resource", { resource_type: "Hall", disabled: 0 }])}
				${stat(__("Occupied now"), `${number(h.occupied_now)} / ${number(h.active_halls)}`, h.occupied_now ? "is-positive" : "", hall({ status: held, booking_date: day }))}
			</div>
			<div class="imed-yday-sub">${esc(__("This month"))}</div>
			<div class="imed-yday-stats">
				${stat(__("Bookings"), number(h.month_held), "", hall({ booking_date: month, status: held }))}
				${stat(__("Hours"), hours_text(h.month_hours), "", hall({ booking_date: month, status: held }))}
				${stat(__("Cancelled"), number(h.month_cancelled), h.month_cancelled ? "is-warning" : "", hall({ booking_date: month, status: "Cancelled" }))}
				${stat(__("Fixed rents (not yet invoiced)"), money(h.month_fixed_rent, currency), "", hall({ booking_date: month, status: held, rental_model: "Fixed Rent" }))}
				${stat(__("Revenue shares"), number(h.month_revenue_share), "", hall({ booking_date: month, status: held, rental_model: "Revenue Share" }))}
			</div>
			${
				h.past_open || h.financial_review
					? `<p class="imed-yday-warn">
						${h.past_open ? `<a href="#" class="imed-yday-link" data-route="${esc(JSON.stringify(hall({ status: ["in", ["Tentative", "Confirmed", "Confirmed with Deposit"]], booking_date: ["<=", day] })))}">${esc(__("{0} past hall booking(s) neither completed nor cancelled.", [h.past_open]))}</a>` : ""}
						${h.financial_review ? ` <a href="#" class="imed-yday-link" data-route="${esc(JSON.stringify(hall({ financial_review: 1, status: held })))}">${esc(__("{0} revenue share(s) with no share agreed yet.", [h.financial_review]))}</a>` : ""}
					  </p>`
					: ""
			}`
		);
	}

	function app_card(a, currency, day) {
		if (a.state !== "ok") {
			return card("smartphone", __("Platform fees"), `<p class="imed-yday-warn">${esc(__("No app agreement yet."))}</p>`);
		}
		const ledger = (types) => ["Doctor Ledger Entry", { docstatus: 1, entry_date: day, entry_type: ["in", types] }];
		return card(
			"smartphone",
			__("Platform fees"),
			`<div class="imed-yday-stats">
				${stat(__("Charged today"), money(a.charged, currency), "", ledger(["Accrual", "Adjustment"]))}
				${stat(__("Collected today"), money(a.collected, currency), a.collected ? "is-positive" : "", ledger(["Collection"]))}
				${stat(
					__("Still owed by doctors"),
					a.outstanding == null ? esc(__("Not configured")) : money(a.outstanding, currency),
					a.outstanding > 0 ? "is-negative" : "",
					["Doctor Ledger Entry", { docstatus: 1 }]
				)}
				${stat(__("New students"), number(a.subscriptions), "", ["App Subscription", { docstatus: 1, subscription_date: day }])}
			</div>`
		);
	}

	function warnings(list) {
		return list.length
			? `<ul class="imed-yday-warnings">${list.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>`
			: "";
	}

	function printing_card(p, day) {
		if (p.state !== "ok") return "";
		const libraries = p.libraries
			.map((lib) => {
				if (!lib.reading) return "";
				// The figures are the library's submitted Daily Counter Reading of the day (owner_yesterday.printing),
				// not a Printer Reading (audit of 1 Nov 2026: the links opened the wrong, empty list).
				const reading = ["Daily Counter Reading", { name: lib.reading }];
				const machines = lib.machines
					.map(
						(m) => `<tr><td>${esc(m.machine)}${m.fault ? ` <span class="imed-yday-flag">${esc(__("breakdown"))}</span>` : ""}</td>
							<td class="is-num">${number(m.opening)}</td><td class="is-num">${number(m.closing)}</td>
							<td class="is-num">${number(m.consumed)}</td></tr>`
					)
					.join("");
				return `<div class="imed-yday-sub">${esc(lib.library)}</div>
					<table class="imed-yday-table is-compact">
						<thead><tr><th>${esc(__("Machine"))}</th><th class="is-num">${esc(__("Opening"))}</th>
							<th class="is-num">${esc(__("Closing"))}</th><th class="is-num">${esc(__("Sheets"))}</th></tr></thead>
						<tbody>${machines}</tbody>
					</table>
					<div class="imed-yday-stats">
						${stat(__("Sheets printed"), number(lib.consumed), "", reading)}
						${stat(__("Sheets sold"), number(lib.sold), "", reading)}
						${stat(__("Difference"), number(lib.variance), lib.variance ? "is-warning" : "", reading)}
					</div>`;
			})
			.join("");
		if (!libraries) return "";
		return `<section class="imed-sec">
				<header class="imed-sec__head"><h2>${frappe.utils.icon("printer", "sm")}<span>${esc(__("Paper and counters"))}</span></h2></header>
				${libraries}
			</section>`;
	}

	// The integrations and imports are not on the owner's page (the owner, 2 Nov 2026): their state is on the
	// Integration Status screen, in the sidebar.

	function render_yesterday($page) {
		const $slot = slot($page, "today");
		if (!yesterday || !$slot.length) return;
		const d = yesterday;
		$slot.html(`<div class="imed-yday">${money_card(d)}${printing_card(d.printing, d.day)}</div>`);
		$slot.off("click").on("click", ".imed-yday-link", function (e) {
			e.preventDefault();
			open_route(JSON.parse($(this).attr("data-route")));
		});
		ledger_empty = d.ledger_entries_all_time === 0;
		mark_cards($page);
	}

	// The server refuses anyone else (owner_yesterday.check_owner); not asking spares them an error.
	const is_owner = () => frappe.session.user === "Administrator" || frappe.user.has_role("Super Admin");

	function add_yesterday($page) {
		if (!is_owner()) return;
		if (Date.now() - fetched_at < REFRESH_MS) {
			if (yesterday && !$page.find('[data-slot="today"] .imed-yday').length) render_yesterday($page);
			return;
		}
		if (fetching) return;
		fetching = true;
		frappe
			.xcall("imed_erp.imederp.owner_yesterday.get_yesterday")
			.then((data) => {
				yesterday = data;
				fetched_at = Date.now();
				if (on_dashboard()) render_yesterday($(".page-container:visible .layout-main-section, .page-container:visible").first());
			})
			.catch(() => {
				// Shown by Frappe; asked again on the next visit after the wait, not on every redraw.
				fetched_at = Date.now();
			})
			.finally(() => (fetching = false));
	}

	// ---------------- The overview (imederp/owner_overview.py; the owner's picture of 2 Nov 2026) ----------------
	// Under the welcome band, above the day's figures: four figures with how they moved since last month, the
	// bookings' path this month, the next bookings, the bookings' money and the reports. Every figure is the
	// server's; only a difference and a percentage between two of them are worked out here. Styles: §28.
	let overview = null;
	let overview_at = 0;
	let overview_busy = false;
	// "Go there" points forward: left in Arabic, right in English.
	const forward = () => (frappe.utils.is_rtl() ? "arrow-left" : "arrow-right");
	const pct = (value) => `${format_number(Math.abs(value), null, Math.abs(value) < 10 ? 1 : 0)}%`;
	const short_day = (value) => {
		const d = new Date(`${value}T00:00:00`);
		return [d.toLocaleDateString(frappe.boot.lang || "en", { day: "numeric" }), d.toLocaleDateString(frappe.boot.lang || "en", { month: "short" })];
	};
	// The four figures: icon, name and amount only (the owner, 2 Nov 2026: no "vs last month" line).
	function kpi(tone, icon, label, value) {
		return `<section class="imed-ov-kpi tone-${tone}">
				<div class="imed-ov-kpi__top">
					<span class="imed-ov-kpi__icon">${frappe.utils.icon(icon, "md")}</span>
					<span class="imed-ov-kpi__label">${esc(label)}</span>
				</div>
				<b class="imed-ov-kpi__value imed-ov-num ${value < 0 ? "is-negative" : ""}">${esc(format_currency(value || 0, overview.currency, 0))}</b>
			</section>`;
	}

	function kpis_html(k) {
		return `<div class="imed-ov-kpis">
				${kpi("green", "scale", __("Net profit this month"), k.month.net)}
				${kpi("blue", "trending-up", __("Revenue this month"), k.month.revenue)}
				${kpi("orange", "trending-down", __("Expenses this month"), k.month.expenses)}
				${kpi("violet", "wallet", __("In the cash boxes"), k.cash)}
			</div>`;
	}

	// Today's sales of each library as its own system sent them, first on the page (the owner, 4 Nov 2026): the
	// sales, how many invoices, the returns, and whether the library's connector is delivering (every 10 minutes:
	// live under 25 minutes, late under 2 hours, stopped beyond). A library not linked yet says so, not a zero.
	const LIBRARY_TONES = ["teal", "cyan"];

	function library_tile(l, i) {
		const tone = LIBRARY_TONES[i % LIBRARY_TONES.length];
		if (!l.linked) {
			return `<section class="imed-ov-kpi imed-lib-kpi imed-ov-lib is-unlinked tone-gray">
					<div class="imed-ov-kpi__top">
						<span class="imed-ov-kpi__icon">${frappe.utils.icon("store", "md")}</span>
						<span class="imed-ov-kpi__label">${esc(l.name)}</span>
					</div>
					<b class="imed-ov-kpi__value">${esc(__("Not linked yet"))}</b>
					<span class="imed-lib-kpi__note">${esc(__("Its sales show here once its system is linked"))}</span>
				</section>`;
		}
		const minutes = (Date.now() - frappe.datetime.str_to_obj(l.last_synced_at).getTime()) / 60000;
		const beat = minutes <= 25 ? ["is-live", __("Connected")] : minutes <= 120 ? ["is-late", __("Late")] : ["is-stopped", __("Stopped")];
		const returns = l.returns_count ? ` · ${__("Returns {0}", [format_currency(l.returns_value, overview.currency, 0)])}` : "";
		const href = `/desk/library-sales-document?cost_center=${encodeURIComponent(l.cost_center)}`;
		return `<a class="imed-ov-kpi imed-lib-kpi imed-ov-lib tone-${tone}" href="${href}">
				<div class="imed-ov-kpi__top">
					<span class="imed-ov-kpi__icon">${frappe.utils.icon("store", "md")}</span>
					<span class="imed-ov-kpi__label">${esc(l.name)}</span>
					<span class="imed-ov-lib__beat ${beat[0]}" title="${esc(__("Last update {0}", [frappe.datetime.prettyDate(l.last_synced_at)]))}"><i class="imed-lib-beat ${beat[0] === "is-live" ? "is-live" : ""}"></i>${esc(beat[1])}</span>
				</div>
				<b class="imed-ov-kpi__value imed-ov-num">${esc(format_currency(l.sales_value, overview.currency, 0))}</b>
				<span class="imed-lib-kpi__note">${esc(__("{0} invoices", [number(l.sales_count)]) + returns)}</span>
			</a>`;
	}

	function libraries_html(libs) {
		if (!libs || !libs.rows.length) return "";
		return `<section class="imed-ov-libs">
				<h3>${frappe.utils.icon("store", "sm")}${esc(__("The libraries' sales today"))}</h3>
				<div class="imed-ov-libs__grid">${libs.rows.map(library_tile).join("")}</div>
			</section>`;
	}

	// The halls and the studio apart (the owner, 2 Nov 2026), each booking tentative or completed.
	const KINDS = {
		halls: ["presentation", "tone-blue", __("Halls")],
		studio: ["clapperboard", "tone-violet", __("Studio")],
	};

	function pipeline_html(p) {
		const blocks = p.kinds
			.map((k) => {
				const [icon, tone, name] = KINDS[k.kind];
				const total = k.tentative + k.completed;
				const done = total ? (k.completed / total) * 100 : 0;
				const apart = k.cancelled || k.no_show
					? `<span class="imed-ov-muted">${esc(__("Cancelled {0} · No show {1}", [number(k.cancelled), number(k.no_show)]))}</span>`
					: "";
				return `<div class="imed-ov-kind ${tone}">
						<div class="imed-ov-kind__head">
							<span class="imed-ov-kind__icon">${frappe.utils.icon(icon, "sm")}</span>
							<b>${esc(name)}</b>
							<span class="imed-ov-kind__total"><b class="imed-ov-num">${esc(number(total))}</b><small>${esc(__("Total"))}</small></span>
						</div>
						<div class="imed-ov-kind__bar ${total ? "" : "is-empty"}" role="img" aria-label="${esc(`${__("Completed")} ${number(k.completed)} / ${number(total)}`)}">
							<i class="is-done" style="inline-size:${done}%"></i><i class="is-open" style="inline-size:${total ? 100 - done : 0}%"></i>
						</div>
						<div class="imed-ov-kind__counts">
							<span class="is-open">${esc(__("Tentative"))} <b class="imed-ov-num">${esc(number(k.tentative))}</b></span>
							<span class="is-done">${esc(__("Completed"))} <b class="imed-ov-num">${esc(number(k.completed))}</b></span>
							${apart}
						</div>
					</div>`;
			})
			.join("");
		return `<section class="imed-ov-card imed-ov-pipeline">
				<h3>${esc(__("Bookings this month"))}</h3>
				<div class="imed-ov-kinds">${blocks}</div>
			</section>`;
	}

	function upcoming_html(u) {
		const rows = u.rows
			.map((r) => {
				const [day, month] = short_day(r.booking_date);
				const time = r.from_time ? `${r.from_time.slice(0, 5)}${r.to_time ? " – " + r.to_time.slice(0, 5) : ""}` : "";
				return `<li><a href="/desk/booking/${encodeURIComponent(r.name)}">
						<span class="imed-ov-date"><b>${esc(day)}</b><small>${esc(month)}</small></span>
						<span class="imed-ov-upcoming__text"><b>${esc(r.resource || r.name)}</b>
							<small>${r.customer_name ? `<bdi>${esc(r.customer_name)}</bdi>` : ""}${r.customer_name && time ? " · " : ""}${time ? `<bdi dir="ltr">${esc(time)}</bdi>` : ""}</small></span>
					</a></li>`;
			})
			.join("");
		return `<section class="imed-ov-card imed-ov-upcoming">
				<h3>${esc(__("Upcoming bookings"))}</h3>
				${rows ? `<ul>${rows}</ul>` : `<p class="imed-ov-empty">${frappe.utils.icon("calendar-days", "md")}<span>${esc(__("No booking in the next {0} days.", [u.days]))}</span></p>`}
				<a class="imed-ov-more" href="/desk/booking/view/calendar">${esc(__("View calendar"))}${frappe.utils.icon(forward(), "xs")}</a>
			</section>`;
	}

	function collection_html(c) {
		const pending = Math.max(flt(c.outstanding - c.overdue, 2), 0);
		const share = (v) => (c.total ? Math.max(0, Math.min(100, (v / c.total) * 100)) : 0);
		const paid = share(c.paid);
		const due = share(pending);
		const ring = c.total
			? `conic-gradient(var(--ov-paid) 0 ${paid}%, var(--ov-pending) ${paid}% ${paid + due}%, var(--ov-overdue) ${paid + due}% 100%)`
			: "conic-gradient(var(--ov-empty) 0 100%)";
		const line = (cls, label, value) => `<li class="${cls}"><span>${esc(label)}</span><b class="imed-ov-num">${esc(money(value, overview.currency))}</b></li>`;
		return `<section class="imed-ov-card imed-ov-collection">
				<h3>${esc(__("Bookings' money"))} <small>${esc(__("(This month)"))}</small></h3>
				<div class="imed-ov-collection__body">
					<div class="imed-ov-ring" style="background:${ring}">
						<div><b class="imed-ov-num">${c.total ? esc(pct(paid)) : "—"}</b><small>${esc(__("Collected"))}</small></div>
					</div>
					<ul class="imed-ov-legend">
						${line("tone-green", __("Collected"), c.paid)}
						${line("tone-amber", __("Pending"), pending)}
						${line("tone-red", __("Overdue"), c.overdue)}
						<li class="is-total"><span>${esc(__("Total"))}</span><b class="imed-ov-num">${esc(money(c.total, overview.currency))}</b></li>
					</ul>
				</div>
			</section>`;
	}

	const REPORTS = [
		["Revenue by Period", "chart-column", "blue"],
		["Profit Before and After Shared Costs", "scale", "green"],
		["Outstanding Receivables", "hand-coins", "amber"],
		["Cash Box Balances", "wallet", "violet"],
	];

	function reports_html() {
		const tiles = REPORTS.map(
			([report, icon, tone]) => `<a class="imed-ov-report tone-${tone}" href="/desk/query-report/${encodeURIComponent(report)}">
					<span class="imed-ov-report__icon">${frappe.utils.icon(icon, "md")}</span><span>${esc(__(report))}</span>
				</a>`
		).join("");
		return `<section class="imed-ov-card imed-ov-reports">
				<h3>${esc(__("Reports"))}</h3>
				<div class="imed-ov-reports__grid">${tiles}</div>
			</section>`;
	}

	function render_overview($page) {
		const $slot = slot($page, "overview");
		if (!overview || !$slot.length) return;
		$slot.html(`<div class="imed-ov">${reports_html()}</div>`);
	}

	function add_overview($page) {
		if (!is_owner()) return;
		if (Date.now() - overview_at < REFRESH_MS) {
			if (overview && !$page.find('[data-slot="overview"] .imed-ov').length) render_overview($page);
			return;
		}
		if (overview_busy) return;
		overview_busy = true;
		frappe
			.xcall("imed_erp.imederp.owner_overview.get_overview")
			.then((data) => {
				overview = data;
				overview_at = Date.now();
				if (on_dashboard()) render_overview($(".page-container:visible .layout-main-section, .page-container:visible").first());
			})
			// Shown by Frappe; asked again on the next visit after the wait, not on every redraw.
			.catch(() => (overview_at = Date.now()))
			.finally(() => (overview_busy = false));
	}

	// ---------------- The owner's page, simplified (the owner, 5 Nov 2026) ----------------
	// "Simple as possible, big clear numbers, mostly seen on a phone, lots of animation": today, the week and the
	// month (owner_periods.get_periods) under the welcome band; under the workspace's own blocks (approvals, the
	// money cards), the cash in each box, the supplies with their arrows (owner_periods.get_boxes_and_stock), the
	// day's revenue and expenses by business and the counters (owner_yesterday), the next bookings and the reports.
	// Each section has its slot, so the order holds whichever answer comes first. Styles: theme §40.
	let by_period = null;
	let by_period_at = 0;
	let by_period_busy = false;
	let boxes = null;
	let boxes_at = 0;
	let boxes_busy = false;
	const whole = (value, currency) => format_currency(value || 0, currency, 0);
	const reduced_motion = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

	// The slots: one after the welcome band, the others after the workspace's blocks.
	function slot($page, name) {
		const $editor = $page.find(".codex-editor").first();
		if (!$editor.length) return $();
		if (!$page.find(".imed-slot-top").length) {
			const $top = $(`<div class="imed-slot-top"><div data-slot="periods">${skeleton(4, "is-cards")}${skeleton(1, "is-wide")}</div></div>`);
			const $welcome = $page.find(".imed-dash-welcome").first();
			$welcome.length ? $top.insertAfter($welcome) : $top.insertBefore($editor);
		}
		if (!$page.find(".imed-slot-after").length) {
			$(`<div class="imed-slot-after">
					<div data-slot="boxes">${skeleton(1, "is-wide")}</div><div data-slot="stock">${skeleton(4, "is-cards")}</div><div data-slot="requests"></div><div data-slot="today"></div><div data-slot="overview"></div>
				</div>`).insertAfter($editor);
		}
		return $page.find(`[data-slot="${name}"]`).first();
	}

	// A number counts up to its value when it comes into view: data-to, and data-cur for money.
	// Each section and card comes in as it scrolls into view, and its numbers count up then, not before (the owner,
	// 9 Nov 2026: "lots of animation").
	const REVEAL = ".imed-sec, .imed-pd-band, .imed-tm-col, .imed-mo-tile, .imed-stock, .imed-req li, .imed-wk-row, .imed-pd-card";
	const seen = "IntersectionObserver" in window
		? new IntersectionObserver(
				(entries) =>
					entries.forEach((e) => {
						if (!e.isIntersecting) return;
						e.target.classList.add("is-in");
						seen.unobserve(e.target);
						if (e.target.matches("[data-to]")) run_count(e.target);
					}),
				{ threshold: 0.15 }
		  )
		: null;
	function run_count(el) {
		const to = Number(el.dataset.to) || 0;
		const cur = el.dataset.cur;
		const dec = Number(el.dataset.dec) || 0;
		const show = (v) => (el.textContent = cur ? whole(v, cur) : format_number(v, null, dec));
		if (reduced_motion() || !to) return show(to);
		const start = performance.now();
		const run = (t) => {
			const k = Math.min(1, (t - start) / 900);
			show(to * (1 - Math.pow(1 - k, 3)));
			if (k < 1) requestAnimationFrame(run);
			else show(to);
		};
		show(0);
		requestAnimationFrame(run);
	}
	function count_up($root) {
		$root.find(REVEAL).addClass("imed-reveal").each(function () {
			seen ? seen.observe(this) : this.classList.add("is-in");
		});
		$root.find("[data-to]").each(function () {
			seen ? seen.observe(this) : run_count(this);
		});
	}
	// While the figures are on their way: a shimmering outline of what comes.
	const skeleton = (cards, cls = "") => `<div class="imed-skel ${cls}">${'<span></span>'.repeat(cards)}</div>`;

	// A quantity: one decimal when it is not whole (0.1 of a box of paper is not 0).
	const qty = (value) => format_number(value || 0, null, (value || 0) % 1 ? 1 : 0);
	const big = (value, currency) => `<b class="imed-pd-num" data-to="${Number(value) || 0}"${currency ? ` data-cur="${esc(currency)}"` : ""}>${currency ? whole(value, currency) : number(value)}</b>`;

	// Each business's own logo in place of an icon (the owner, 5 Nov 2026); the app has none yet.
	const LOGOS = {
		studio: "/assets/imed_erp/images/logos/x-studio.jpg",
		halls: "/assets/imed_erp/images/logos/imed-academy.jpg",
		libraries: "/assets/imed_erp/images/logos/doctor-2-be.jpg",
		app: "/assets/imed_erp/images/logos/ba-plus.jpg",
	};
	const logo = (b, cls) =>
		LOGOS[b.key] ? `<img class="${cls}" src="${LOGOS[b.key]}" alt="" loading="lazy">` : `<span class="${cls} is-icon">${frappe.utils.icon(b.icon, "md")}</span>`;

	// ---- Today, the week, the month: four cards each, two to a row, one big figure and one line under it ----
	// The list behind a business's figure for a period: its bookings, its sales, its students' fees.
	function route_for(key, p) {
		const span = ["between", [p.from, p.to]];
		if (key === "studio" || key === "halls") return ["Booking", { resource_type: key === "studio" ? "Studio Service" : "Hall", booking_date: span }];
		if (key === "libraries") return ["Library Sales Document", { reg_date: ["between", [`${p.from} 00:00:00`, `${p.to} 23:59:59`]] }];
		return ["Doctor Ledger Entry", { entry_date: span }];
	}

	// Today: four cards side by side, a logo, the business, one figure and its line.
	function period_card(b, p, c, i) {
		const a = b.activity || {};
		const span = ["between", [p.from, p.to]];
		let figure = "";
		let caption = "";
		let route = null;
		if (b.key === "studio" || b.key === "halls") {
			route = ["Booking", { resource_type: b.key === "studio" ? "Studio Service" : "Hall", booking_date: span }];
			figure = big(a.bookings);
			caption = `${esc(__("bookings"))} · ${esc(hours_text(a.hours))}`;
		} else if (b.key === "libraries") {
			// Azarita's and Mawasah's apart (the owner, 9 Nov 2026).
			route = ["Library Sales Document", { reg_date: ["between", [`${p.from} 00:00:00`, `${p.to} 23:59:59`]] }];
			figure = `<span class="imed-pd-libs">${(a.rows || [])
				.map((r) => `<span><small>${esc(r.name.replace(/^مكتبة\s+/, ""))}</small>${big(r.net)}</span>`)
				.join("")}</span>`;
			caption = esc(__("pounds"));
		} else {
			route = ["Doctor Ledger Entry", { entry_date: span }];
			figure = a.state === "ok" ? big(a.charged) : `<b class="imed-pd-num">—</b>`;
			caption = a.state === "ok" ? `${esc(__("pounds"))} · ${esc(__("{0} new subscriptions", [number(a.subscriptions)]))}` : esc(__("Not set up yet"));
		}
		return `<a class="imed-pd-card tone-${b.key}" style="--i:${i}" href="#" data-route="${esc(JSON.stringify(route))}">
				${logo(b, "imed-pd-card__logo")}
				<span class="imed-pd-card__label">${esc(b.label)}</span>
				${figure}
				<span class="imed-pd-card__caption">${caption}</span>
			</a>`;
	}

	// Tomorrow's bookings, the halls' and the studio's side by side (the owner, 9 Nov 2026).
	function tomorrow_html(t) {
		if (!t) return "";
		const list = (rows, icon_key, title) => `<div class="imed-tm-col tone-${icon_key}">
				<h3>${logo({ key: icon_key, icon: icon_key === "halls" ? "presentation" : "clapperboard" }, "imed-tm-logo")}<span>${esc(title)}</span><b>${number(rows.length)}</b></h3>
				${
					rows.length
						? `<ul>${rows
								.map(
									(r, i) => `<li style="--i:${i}"><a href="/desk/booking/${encodeURIComponent(r.name)}">
										<span class="imed-tm-time">${esc(r.from_time || "")}<small>${esc(r.to_time || "")}</small></span>
										<span class="imed-tm-text"><b>${esc(r.resource)}</b><small>${esc(r.who || r.activity || "")}</small></span>
									</a></li>`
								)
								.join("")}</ul>`
						: `<p class="imed-sec__empty">${esc(__("Nothing booked"))}</p>`
				}
			</div>`;
		return `<section class="imed-pd-band is-tomorrow" style="--n:1">
				<header class="imed-pd-band__head">
					<h2>${frappe.utils.icon("calendar-clock", "sm")}<span>${esc(__("Tomorrow's bookings"))}</span></h2>
					<span class="imed-pd-band__dates">${esc(frappe.datetime.str_to_user(t.date))}</span>
				</header>
				<div class="imed-tm">${list(t.halls, "halls", __("Halls"))}${list(t.studio, "studio", __("Studio"))}</div>
			</section>`;
	}

	// The week: each business's days as bars, Saturday to Friday, today marked, the days to come faint.
	const weekday = (d) => new Date(`${d}T00:00:00`).toLocaleDateString(frappe.boot.lang || "en", { weekday: "narrow" });
	function week_html(p, c) {
		const today = by_period.today;
		const dates = p.days.dates;
		const rows = p.businesses
			.map((b, i) => {
				const values = p.days[b.key] || [];
				const top = Math.max(...values, 0) || 1;
				const total = values.reduce((t, v) => t + v, 0);
				const money_kind = b.key === "libraries" || b.key === "app";
				const bars = dates
					.map((d, k) => {
						const v = values[k] || 0;
						const state = d > today ? "is-future" : d === today ? "is-today" : "";
						const label = money_kind ? whole(v, c) : number(v);
						return `<span class="imed-wk-bar ${state}" title="${esc(`${frappe.datetime.str_to_user(d)}: ${label}`)}">
								<i style="--h:${Math.round((v / top) * 100)}%; --k:${k}"></i><small>${esc(weekday(d))}</small>
							</span>`;
					})
					.join("");
				return `<a class="imed-wk-row tone-${b.key}" style="--i:${i}" href="#" data-route="${esc(JSON.stringify(route_for(b.key, p)))}">
						${logo(b, "imed-wk-logo")}
						<span class="imed-wk-name"><span>${esc(b.label)}</span>${money_kind ? big(total, c) : big(total)}<small>${esc(money_kind ? (b.key === "app" ? __("students' fees") : __("sales")) : __("bookings"))}</small></span>
						<span class="imed-wk-bars">${bars}</span>
					</a>`;
			})
			.join("");
		return `<div class="imed-wk">${rows}</div>`;
	}

	// The month: each business against the same days of last month, an arrow and the change.
	function month_html(p, c) {
		const tiles = p.businesses
			.map((b, i) => {
				const money_kind = b.key === "libraries" || b.key === "app";
				const now = b.main || 0;
				const before = b.previous || 0;
				const dir = now > before ? "up" : now < before ? "down" : "flat";
				const change = before ? Math.round(((now - before) / before) * 100) : null;
				const fmt = (v) => (money_kind ? whole(v, c) : number(v));
				const pill =
					dir === "flat"
						? `<span class="imed-mo-pill is-flat">${frappe.utils.icon("minus", "xs")}<span>${esc(__("Same as last month"))}</span></span>`
						: `<span class="imed-mo-pill is-${dir}">${frappe.utils.icon(dir === "up" ? "arrow-up" : "arrow-down", "xs")}<span>${
								change === null ? esc(__("New this month")) : `${Math.abs(change)}%`
						  }</span></span>`;
				const top = Math.max(now, before) || 1;
				return `<a class="imed-mo-tile tone-${b.key}" style="--i:${i}" href="#" data-route="${esc(JSON.stringify(route_for(b.key, p)))}">
						<div class="imed-mo-tile__head">${logo(b, "imed-mo-logo")}<span>${esc(b.label)}</span>${pill}</div>
						${money_kind ? big(now, c) : big(now)}
						<div class="imed-mo-compare">
							<span class="imed-mo-compare__row"><small>${esc(__("This month"))}</small><span class="imed-mo-track"><i style="--w:${Math.round((now / top) * 100)}%"></i></span></span>
							<span class="imed-mo-compare__row is-before"><small>${esc(__("Last month"))}</small><span class="imed-mo-track"><i style="--w:${Math.round((before / top) * 100)}%"></i></span><b>${fmt(before)}</b></span>
						</div>
					</a>`;
			})
			.join("");
		return `<div class="imed-mo">${tiles}</div>`;
	}

	function render_periods($page) {
		const $slot = slot($page, "periods");
		if (!by_period || !$slot.length) return;
		const c = by_period.currency;
		$slot.html(
			by_period.periods
				.map((p, n) => (n === 1 ? tomorrow_html(by_period.tomorrow) : "") + band_html(p, n, c))
				.join("")
		);
		$slot.off("click").on("click", ".imed-pd-card, .imed-wk-row, .imed-mo-tile", function (e) {
			e.preventDefault();
			const route = JSON.parse($(this).attr("data-route") || "null");
			if (route) open_route(route);
		});
		count_up($slot);
	}

	// A period's band: today's cards, the week's bars or the month's comparison.
	function band_html(p, n, c) {
		const icons = { today: "sun", week: "calendar-range", month: "calendar-days" };
		const from = frappe.datetime.str_to_user(p.from);
		const to = frappe.datetime.str_to_user(p.to);
		const body =
			p.key === "week"
				? week_html(p, c)
				: p.key === "month"
				? month_html(p, c)
				: `<div class="imed-pd-grid">${p.businesses.map((b, i) => period_card(b, p, c, i)).join("")}</div>`;
		return `<section class="imed-pd-band is-${p.key}" style="--n:${n}">
				<header class="imed-pd-band__head">
					<h2>${p.key === "today" ? `<span class="imed-live" aria-hidden="true"></span>` : frappe.utils.icon(icons[p.key], "sm")}<span>${esc(p.label)}</span></h2>
					<span class="imed-pd-band__dates">${esc(p.from === p.to ? from : `${from} – ${to}`)}</span>
				</header>
				${body}
			</section>`;
	}

	// ---- The cash in each box: its whole name and a bar, the largest first ----
	function render_boxes($page) {
		const $slot = slot($page, "boxes");
		if (!boxes || !$slot.length) return;
		const c = boxes.currency;
		const rows = boxes.boxes.filter((b) => b.balance);
		const top = Math.max(1, ...rows.map((b) => Math.abs(b.balance)));
		const total = rows.reduce((t, b) => t + b.balance, 0);
		$slot.html(`<section class="imed-sec">
				<header class="imed-sec__head"><h2>${frappe.utils.icon("wallet", "sm")}<span>${esc(__("Cash in each box"))}</span></h2>${big(total, c)}</header>
				${
					rows.length
						? `<ul class="imed-boxes">${rows
								.map(
									(b, i) => `<li style="--i:${i}"><a href="/desk/query-report/General Ledger?account=${encodeURIComponent(b.account)}">
										<span class="imed-boxes__name">${esc(b.name)}</span>
										<b class="imed-boxes__value ${b.balance < 0 ? "is-out" : ""}">${whole(b.balance, c)}</b>
										<span class="imed-boxes__bar"><i style="--w:${Math.round((Math.abs(b.balance) / top) * 100)}%"></i></span>
									</a></li>`
								)
								.join("")}</ul>`
						: `<p class="imed-sec__empty">${esc(__("The boxes are empty."))}</p>`
				}
			</section>`);
		count_up($slot);
	}

	// ---- The supplies, each library apart: what is left, the week's arrow, how long it lasts; the Epson colours ----
	function stock_tile(s, i) {
		if (!s.counted) {
			return `<a class="imed-stock is-uncounted" style="--i:${i}" href="/desk/query-report/Stock Balance?item_code=${encodeURIComponent(s.item_code)}">
					<span class="imed-stock__name">${esc(s.name)}</span>
					<span class="imed-stock__qty"><b class="imed-pd-num">—</b></span>
					<span class="imed-stock__lasts">${frappe.utils.icon("clock", "xs")}<span>${esc(__("Not counted yet"))}</span></span>
				</a>`;
		}
		const unit = s.unit ? ` ${esc(s.unit)}` : "";
		const dir = s.change > 0 ? "up" : s.change < 0 ? "down" : "flat";
		const arrow = { up: "arrow-up", down: "arrow-down", flat: "minus" }[dir];
		const low = s.days_left !== null && s.days_left !== undefined && s.days_left <= 7;
		const lasts =
			s.days_left === null || s.days_left === undefined
				? esc(__("Not used this week"))
				: s.days_left === 0
				? esc(__("Runs out today"))
				: esc(__("Lasts about {0} days", [number(s.days_left)]));
		return `<a class="imed-stock ${low ? "is-low" : ""} ${s.qty <= 0 ? "is-empty" : ""}" style="--i:${i}" href="/desk/query-report/Stock Balance?item_code=${encodeURIComponent(s.item_code)}">
				<span class="imed-stock__name">${esc(s.name)}</span>
				<span class="imed-stock__qty"><b class="imed-pd-num" data-to="${Number(s.qty) || 0}" data-dec="${s.qty % 1 ? 1 : 0}">${qty(s.qty)}</b>${unit}</span>
				<span class="imed-stock__trend is-${dir}" title="${esc(__("A week ago: {0}", [qty(s.week_ago)]))}">${frappe.utils.icon(arrow, "xs")}<span>${dir === "flat" ? esc(__("No change this week")) : `${qty(Math.abs(s.change))}${unit} ${esc(dir === "up" ? __("more than last week") : __("less than last week"))}`}</span></span>
				<span class="imed-stock__lasts">${frappe.utils.icon(low ? "triangle-alert" : "clock", "xs")}<span>${lasts}</span></span>
			</a>`;
	}

	// The Epson set's four colours on one tile: what each holds, the one that finished most this month first.
	const EPSON_DOTS = { "INK-EPSON-BK": "#1f2937", "INK-EPSON-C": "#06b6d4", "INK-EPSON-M": "#db2777", "INK-EPSON-Y": "#eab308" };
	function epson_tile(colours, i) {
		if (!colours.length) return "";
		const first = colours[0];
		const rows = colours
			.map(
				(c) => `<span class="imed-epson__row ${c.qty <= 0 ? "is-empty" : ""}">
						<i style="--dot:${EPSON_DOTS[c.item_code] || "#64748b"}"></i>
						<span>${esc(c.name.replace(/^حبر إبسون\s*/, ""))}</span>
						<b>${qty(c.qty)}</b>
						${c.finished_month ? `<small>${esc(__("finished {0} this month", [qty(c.finished_month)]))}</small>` : ""}
					</span>`
			)
			.join("");
		const note = first.finished_month
			? `<span class="imed-stock__lasts is-first">${frappe.utils.icon("triangle-alert", "xs")}<span>${esc(__("Runs out first: {0}", [first.name.replace(/^حبر إبسون\s*/, "")]))}</span></span>`
			: "";
		return `<a class="imed-stock imed-epson" style="--i:${i}" href="/desk/query-report/Stock Balance?item_group=${encodeURIComponent("أحبار")}">
				<span class="imed-stock__name">${esc(__("Epson inks"))}</span>
				<span class="imed-epson__rows">${rows}</span>
				${note}
			</a>`;
	}

	function render_stock($page) {
		const $slot = slot($page, "stock");
		if (!boxes || !$slot.length) return;
		const stores = boxes.stock || [];
		const html = stores
			.map(
				(st) => `<div class="imed-stock-store">
						<h3>${frappe.utils.icon("store", "sm")}<span>${esc(st.name)}</span></h3>
						<div class="imed-stock-grid">${st.items.map((s, i) => stock_tile(s, i)).join("")}${epson_tile(st.epson || [], st.items.length)}</div>
					</div>`
			)
			.join("");
		$slot.html(`<section class="imed-sec">
				<header class="imed-sec__head"><h2>${frappe.utils.icon("package", "sm")}<span>${esc(__("Stock"))}</span></h2></header>
				${html || `<p class="imed-sec__empty">${esc(__("No supplies are set up."))}</p>`}
			</section>`);
		count_up($slot);
	}

	// ---- The libraries' requests for supplies, still open, the newest first ----
	function render_requests($page) {
		const $slot = slot($page, "requests");
		if (!boxes || !$slot.length) return;
		const rows = boxes.requests || [];
		// A request's own words (Frappe's "Pending" reads "not paid yet" elsewhere in the app).
		const STATES = {
			"Pending Approval": __("Waiting for approval"),
			Approved: __("Approved"),
			Pending: __("Not done yet"),
			"Partially Ordered": __("Partly bought"),
			Ordered: __("Bought"),
			"Partially Received": __("Partly received"),
			Draft: __("Draft"),
			Rejected: __("Rejected"),
		};
		const state = (r) => STATES[r.state] || STATES[r.status] || __(r.state || r.status);
		$slot.html(`<section class="imed-sec">
				<header class="imed-sec__head"><h2>${frappe.utils.icon("clipboard-list", "sm")}<span>${esc(__("Libraries' requests"))}</span></h2>${rows.length ? `<b class="imed-req-count">${number(rows.length)}</b>` : ""}</header>
				${
					rows.length
						? `<ul class="imed-req">${rows
								.map(
									(r, i) => `<li style="--i:${i}"><a href="/desk/material-request/${encodeURIComponent(r.name)}">
										<span class="imed-req__store">${esc(r.store)}<small>${esc(frappe.datetime.str_to_user(r.transaction_date))}</small></span>
										<span class="imed-req__items">${r.items.map((it) => `<span><b>${qty(it.qty)}${it.unit ? " " + esc(it.unit) : ""}</b> ${esc(it.name)}</span>`).join("")}</span>
										<span class="imed-req__state">${esc(state(r))}</span>
									</a></li>`
								)
								.join("")}</ul>`
						: `<p class="imed-sec__empty">${esc(__("No open request."))}</p>`
				}
			</section>`);
	}

	function fetch_once(state, method, done) {
		if (!is_owner()) return;
		if (Date.now() - state.at() < REFRESH_MS) return state.data() && done();
		if (state.busy()) return;
		state.set_busy(true);
		frappe
			.xcall(method)
			.then((data) => {
				state.set(data);
				if (on_dashboard()) done();
			})
			.catch(() => state.set(state.data()))
			.finally(() => state.set_busy(false));
	}
	const page_now = () => $(".page-container:visible .layout-main-section, .page-container:visible").first();

	function add_periods($page) {
		if ($page.find('[data-slot="periods"] .imed-pd-band').length && Date.now() - by_period_at < REFRESH_MS) return;
		fetch_once(
			{ at: () => by_period_at, data: () => by_period, busy: () => by_period_busy, set_busy: (v) => (by_period_busy = v), set: (d) => ((by_period = d), (by_period_at = Date.now())) },
			"imed_erp.imederp.owner_periods.get_periods",
			() => render_periods(page_now())
		);
	}

	function add_boxes($page) {
		if ($page.find('[data-slot="boxes"] .imed-sec').length && Date.now() - boxes_at < REFRESH_MS) return;
		fetch_once(
			{ at: () => boxes_at, data: () => boxes, busy: () => boxes_busy, set_busy: (v) => (boxes_busy = v), set: (d) => ((boxes = d), (boxes_at = Date.now())) },
			"imed_erp.imederp.owner_periods.get_boxes_and_stock",
			() => {
				render_boxes(page_now());
				render_stock(page_now());
				render_requests(page_now());
			}
		);
	}

	function decorate() {
		if (!on_dashboard()) return;
		const $page = $(".page-container:visible .layout-main-section, .page-container:visible").first();
		if (!$page.length) return;
		add_welcome($page);
		// The slots, with their shimmer, before any answer comes.
		if (is_owner()) slot($page, "periods");
		add_periods($page);
		add_boxes($page);
		add_overview($page);
		add_yesterday($page);
		mark_headers($page);
		mark_cards($page);
		mark_approvals($page);
	}

	// The workspace draws its widgets, then fills each card and count when its data arrives: decorate on each
	// change while the dashboard is open (every step only does what is not done yet).
	let timer = null;
	const observer = new MutationObserver(() => {
		if (!on_dashboard()) return;
		clearTimeout(timer);
		timer = setTimeout(decorate, 120);
	});
	$(() => {
		observer.observe(document.body, { childList: true, subtree: true, characterData: true });
		decorate();
	});
})();
