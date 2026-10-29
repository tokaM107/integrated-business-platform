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
		"Studio Bookings This Month": ["clapperboard", "count"],
		"Studio Hours This Month": ["clock", "count"],
		"Hall Bookings This Month": ["presentation", "count"],
		"Unpaid on Bookings": ["hourglass", "due"],
		"Due on Studio Bookings (XStudio)": ["clapperboard", "due"],
	};
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
			</div>`).insertBefore($editor);
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
				return ["Treasury", {}];
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
	let fetched_at = 0;
	let fetching = false;

	const money = (value, currency) => format_currency(value || 0, currency);
	const number = (value) => format_number(value || 0, null, 0);
	const tone = (value) => (value > 0 ? "is-positive" : value < 0 ? "is-negative" : "");
	const STATES = {
		ok: __("Working"),
		warning: __("Needs attention"),
		error: __("Failed"),
		unknown: __("Unknown"),
		not_configured: __("Not configured"),
	};

	function card(icon, title, body, extra_class = "") {
		return `<section class="imed-yday-card ${extra_class}">
				<h3>${frappe.utils.icon(icon, "sm")}<span>${esc(title)}</span></h3>
				${body}
			</section>`;
	}

	function money_card(data) {
		const c = data.currency;
		const rows = data.money.rows
			.map(
				(row) => `<tr class="${row.revenue || row.expenses ? "" : "is-quiet"}">
					<td>${esc(row.business)}${
					row.not_split ? ` <span class="imed-yday-flag">${esc(__("not split"))}</span>` : ""
				}${row.external ? ` <span class="imed-yday-flag">${esc(__("from XStudio, {0} booking(s)", [row.bookings]))}</span>` : ""}</td>
					<td class="is-num">${money(row.revenue, c)}</td>
					<td class="is-num">${money(row.expenses, c)}</td>
					<td class="is-num ${tone(row.net)}">${money(row.net, c)}</td>
				</tr>`
			)
			.join("");
		const t = data.money.total;
		return card(
			"chart-column",
			__("Revenue and expenses by business"),
			`<table class="imed-yday-table">
				<thead><tr><th>${esc(__("Business"))}</th><th class="is-num">${esc(__("Revenue"))}</th>
					<th class="is-num">${esc(__("Expenses"))}</th><th class="is-num">${esc(__("Net"))}</th></tr></thead>
				<tbody>${rows}</tbody>
				<tfoot><tr><td>${esc(__("Total"))}</td><td class="is-num">${money(t.revenue, c)}</td>
					<td class="is-num">${money(t.expenses, c)}</td><td class="is-num ${tone(t.net)}">${money(t.net, c)}</td></tr></tfoot>
			</table>
			<p class="imed-yday-note">${esc(
				__("Invoiced revenue and approved expenses (submitted documents only). The X Studio line is what XStudio reports as paid on the day's bookings; it is shown, not posted.")
			)}</p>`,
			"is-wide"
		);
	}

	// Every figure opens the list behind it: route = [doctype, filters] (a Frappe list view with those filters).
	function stat(label, value, cls = "", route = null) {
		const inner = `<span>${esc(label)}</span><b>${value}</b>`;
		return route
			? `<a class="imed-yday-stat imed-yday-link ${cls}" href="#" data-route="${esc(JSON.stringify(route))}" title="${esc(__("Open the list"))}">${inner}</a>`
			: `<div class="imed-yday-stat ${cls}">${inner}</div>`;
	}

	const open_route = (route) => frappe.set_route("List", route[0], route[1]);
	const HELD = ["not in", ["Cancelled", "No Show"]];

	function bookings_card(b, day, currency) {
		const list = (resource_type, status) => ["Booking", { booking_date: day, resource_type, status }];
		const kind = (title, s, resource_type) =>
			`<div class="imed-yday-sub">${esc(title)}</div>
			<div class="imed-yday-stats">
				${stat(__("Held"), number(s.held), "", list(resource_type, HELD))}
				${stat(__("Completed"), number(s.completed), "", list(resource_type, "Completed"))}
				${stat(__("Cancelled"), number(s.cancelled), s.cancelled ? "is-warning" : "", list(resource_type, "Cancelled"))}
				${stat(__("No Show"), number(s.no_show), s.no_show ? "is-warning" : "", list(resource_type, "No Show"))}
			</div>`;
		const hours = __("{0} h", [number(b.studio_hours_booked)]);
		const delivered = __("{0} h", [number(b.studio_hours_delivered)]);
		const made = ["Booking", { creation: ["Between", [`${day} 00:00:00`, `${day} 23:59:59`]] }];
		const open = ["Booking", { booking_date: day, status: ["in", ["Tentative", "Confirmed with Deposit"]], source_system: ["is", "not set"] }];
		return card(
			"calendar-days",
			__("Halls and studio"),
			`${kind(__("Halls"), b.halls, "Hall")}${kind(__("Studio"), b.studio, "Studio Service")}
			<div class="imed-yday-stats">
				${stat(__("Studio hours booked"), hours, "", list("Studio Service", HELD))}
				${stat(__("Studio hours delivered"), delivered, "", list("Studio Service", "Completed"))}
				${stat(__("Booked today (any date)"), number(b.made_yesterday), "", made)}
			</div>
			<div class="imed-yday-sub">${esc(__("The studio's money, as XStudio says it (not posted here)"))}</div>
			<div class="imed-yday-stats">
				${stat(__("Due in XStudio"), money(b.xstudio_due, currency), b.xstudio_due ? "is-negative" : "", ["Booking", { booking_date: day, source_system: "xstudio", status: HELD, xstudio_amount_due: [">", 0] }])}
				${stat(__("Paid in XStudio"), money(b.xstudio_paid, currency), b.xstudio_paid ? "is-positive" : "", ["Booking", { booking_date: day, source_system: "xstudio", xstudio_amount_paid: [">", 0] }])}
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
		return card(
			"presentation",
			__("IMED hall bookings"),
			`<div class="imed-yday-sub">${esc(__("Today"))}</div>
			<div class="imed-yday-stats">
				${stat(__("Booked"), number(h.today.held), "", hall({ booking_date: day, status: held }))}
				${stat(__("Completed"), number(h.today.completed), "", hall({ booking_date: day, status: "Completed" }))}
				${stat(__("Cancelled"), number(h.today.cancelled), h.today.cancelled ? "is-warning" : "", hall({ booking_date: day, status: "Cancelled" }))}
				${stat(__("Hours today"), __("{0} h", [number(h.today_hours)]), "", hall({ booking_date: day, status: held }))}
			</div>
			<div class="imed-yday-stats">
				${stat(__("Next 7 days"), number(h.upcoming), "", hall({ booking_date: ["Between", [frappe.datetime.add_days(day, 1), frappe.datetime.add_days(day, 7)]], status: held }))}
				${stat(__("Active halls"), number(h.active_halls), "", ["Booking Resource", { resource_type: "Hall", disabled: 0 }])}
				${stat(__("Occupied now"), `${number(h.occupied_now)} / ${number(h.active_halls)}`, h.occupied_now ? "is-positive" : "", hall({ status: held, booking_date: day }))}
			</div>
			<div class="imed-yday-sub">${esc(__("This month"))}</div>
			<div class="imed-yday-stats">
				${stat(__("Bookings"), number(h.month_held), "", hall({ booking_date: month, status: held }))}
				${stat(__("Hours"), __("{0} h", [number(h.month_hours)]), "", hall({ booking_date: month, status: held }))}
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
		if (p.state !== "ok") {
			return card("printer", __("Paper and counters"), `<p class="imed-yday-warn">${esc(__("No printing machine is set up."))}</p>`);
		}
		const libraries = p.libraries
			.map((lib) => {
				if (!lib.reading) return "";
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
						${stat(__("Sheets printed"), number(lib.consumed), "", ["Printer Reading", { reading_date: day }])}
						${stat(__("Sheets sold"), number(lib.sold), "", ["Sales Invoice", { docstatus: 1, posting_date: day }])}
						${stat(__("Difference"), number(lib.variance), lib.variance ? "is-warning" : "", ["Printer Reading", { reading_date: day }])}
					</div>`;
			})
			.join("");
		return card("printer", __("Paper and counters"), libraries + warnings(p.warnings));
	}

	// Where a system's figures live: the XStudio sync and the file imports in the import logs, the jobs in theirs.
	function system_route(s) {
		if (s.name === __("XStudio bookings")) return ["Integration Import Log", { source_system: "xstudio" }];
		if (s.name === __("File imports")) return ["Data Import", {}];
		if (s.name.startsWith(__("Daily job"))) return ["Scheduled Job Log", {}];
		return ["Error Log", {}];
	}

	function systems_card(list) {
		const rows = list
			.map(
				(s) => `<li class="imed-yday-system is-${esc(s.state)}">
					<span class="imed-yday-dot"></span>
					<div><b><a href="#" class="imed-yday-link" data-route="${esc(JSON.stringify(system_route(s)))}">${esc(s.name)}</a></b> <span class="imed-yday-state">${esc(STATES[s.state] || s.state)}</span>
						${s.detail ? `<div class="imed-yday-detail">${esc(s.detail)}</div>` : ""}
						${
							s.last_success
								? `<div class="imed-yday-detail">${esc(__("Last success: {0}", [frappe.datetime.str_to_user(s.last_success)]))}</div>`
								: ""
						}
					</div>
				</li>`
			)
			.join("");
		return card("plug", __("Integrations and imports"), `<ul class="imed-yday-systems">${rows}</ul>`);
	}

	function render_yesterday($page) {
		if (!yesterday) return;
		$page.find(".imed-yday").remove();
		const d = yesterday;
		const day = frappe.datetime.str_to_user(d.day);
		const links = [
			["Revenue by Period", __("Revenue by period")],
			["Profit Before and After Shared Costs", __("Profit before and after shared costs")],
			["Outstanding Receivables", __("Outstanding receivables")],
		]
			.map(([report, label]) => `<a href="/desk/query-report/${encodeURIComponent(report)}">${esc(label)}</a>`)
			.join("");
		const $panel = $(`<div class="imed-yday">
				<div class="imed-yday-head">
					<h2>${frappe.utils.icon("calendar-check", "md")}<span>${esc(__("Today, {0}", [day]))}</span> <small class="text-muted">${esc(__("as of {0}", [d.as_of ? frappe.datetime.str_to_user(d.as_of).slice(11, 16) : ""]))}</small></h2>
					<nav>${links}</nav>
				</div>
				<div class="imed-yday-grid">
					${money_card(d)}
					${bookings_card(d.bookings, d.day, d.currency)}
					${d.halls ? halls_card(d.halls, d.currency) : ""}
					${app_card(d.app, d.currency, d.day)}
					${printing_card(d.printing, d.day)}
					${systems_card(d.systems)}
				</div>
			</div>`);
		$panel.on("click", ".imed-yday-link", function (e) {
			e.preventDefault();
			open_route(JSON.parse($(this).attr("data-route")));
		});
		const $welcome = $page.find(".imed-dash-welcome").first();
		if ($welcome.length) $panel.insertAfter($welcome);
		else $panel.insertBefore($page.find(".codex-editor").first());
	}

	// The server refuses anyone else (owner_yesterday.check_owner); not asking spares them an error.
	const is_owner = () => frappe.session.user === "Administrator" || frappe.user.has_role("Super Admin");

	function add_yesterday($page) {
		if (!is_owner()) return;
		if (Date.now() - fetched_at < REFRESH_MS) {
			if (yesterday && !$page.find(".imed-yday").length) render_yesterday($page);
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

	function decorate() {
		if (!on_dashboard()) return;
		const $page = $(".page-container:visible .layout-main-section, .page-container:visible").first();
		if (!$page.length) return;
		add_welcome($page);
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
