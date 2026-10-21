// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The Owner Dashboard's look (owner's request of 21 Oct 2026: "more creative and easy on the eye"). It only adds and
// marks elements on Frappe's own workspace: a welcome band on top, an icon and a meaning (in, out, attention...) on
// each money card, negative amounts marked, the approvals calm when nothing waits. The figures themselves are the
// server's (imederp/owner_figures.py, setup/setup_dashboard.py). Styles: imed_theme.css §22. Loaded by hooks.py.
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
		"Studio Bookings": ["clapperboard", "count"],
		"Studio Hours": ["clock", "count"],
		"Hall Bookings": ["presentation", "count"],
		"Unpaid on Bookings": ["hourglass", "due"],
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

	function mark_cards($page) {
		const map = by_title();
		$page.find(".widget.number-widget-box").each(function () {
			const $card = $(this);
			const entry = map[$card.find(".widget-title").first().text().trim()];
			if (entry && !$card.attr("data-imed-kind")) {
				$card.attr("data-imed-kind", entry[1]).addClass("imed-dash-card");
				$card.find(".widget-label").first().prepend(`<span class="imed-dash-card-icon">${frappe.utils.icon(entry[0], "md")}</span>`);
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

	function decorate() {
		if (!on_dashboard()) return;
		const $page = $(".page-container:visible .layout-main-section, .page-container:visible").first();
		if (!$page.length) return;
		add_welcome($page);
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
