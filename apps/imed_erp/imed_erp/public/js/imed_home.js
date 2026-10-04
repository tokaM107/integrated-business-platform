// IMED ERP home screen: a greeting band with today's date and quick actions, above Frappe's app grid.
//
// Hooks into Frappe's own "desktop_screen" event, fired every time the home screen is drawn. It only
// adds elements; Frappe's grid, its edit mode and its routes are untouched. Every quick action is
// shown only if the user has the permission for it. Loaded by hooks.py (app_include_js).
(() => {
	const is_ar = () => (frappe.boot.lang || "").startsWith("ar");
	// Translations for this file only; the full Arabic translation of the app is planned for week 11.
	const t = (en, ar) => (is_ar() ? ar : en);

	// Each action: which permission it needs, and where it goes.
	const QUICK_ACTIONS = [
		{
			label: () => t("Owner Dashboard", "لوحة المالك"),
			icon: "layout-dashboard",
			allowed: () =>
				(frappe.boot.desktop_icons || []).some((i) => i.label === "Owner Dashboard" && !i.hidden),
			go: () => frappe.set_route(frappe.router.slug("Owner Dashboard")),
		},
		{
			label: () => t("New Sales Invoice", "فاتورة مبيعات جديدة"),
			icon: "receipt-text",
			allowed: () => frappe.model.can_create("Sales Invoice"),
			go: () => frappe.new_doc("Sales Invoice"),
		},
		{
			label: () => t("New Book Edition", "طبعة كتاب جديدة"),
			icon: "book-open",
			allowed: () => frappe.model.can_create("Book Edition"),
			go: () => frappe.new_doc("Book Edition"),
		},
		{
			label: () => t("Printer Reading", "قراءة عداد"),
			icon: "printer",
			allowed: () => frappe.model.can_create("Printer Reading"),
			go: () => frappe.new_doc("Printer Reading"),
		},
		{
			label: () => t("Customers", "العملاء"),
			icon: "users",
			allowed: () => frappe.model.can_read("Customer"),
			go: () => frappe.set_route("List", "Customer"),
		},
		{
			label: () => t("Academic Periods", "الفترات الأكاديمية"),
			icon: "calendar-range",
			allowed: () => frappe.model.can_read("Academic Period"),
			go: () => frappe.set_route("List", "Academic Period"),
		},
	];

	function greeting() {
		const hour = new Date().getHours();
		if (hour < 12) return { text: t("Good morning", "صباح الخير"), icon: "sunrise" };
		if (hour < 18) return { text: t("Good afternoon", "مساء الخير"), icon: "sun" };
		return { text: t("Good evening", "مساء الخير"), icon: "moon" };
	}

	function first_name() {
		const full = (frappe.session.user_fullname || "").trim();
		const first = full.split(/\s+/)[0] || "";
		return first.charAt(0).toUpperCase() + first.slice(1);
	}

	function today() {
		// Latin digits, like the rest of the system (dates, amounts).
		const locale = is_ar() ? "ar-EG-u-nu-latn" : "en-GB";
		return new Intl.DateTimeFormat(locale, {
			weekday: "long",
			day: "numeric",
			month: "long",
			year: "numeric",
		}).format(new Date());
	}

	function build_hero() {
		const hello = greeting();
		const name = first_name();
		const company = frappe.defaults.get_user_default("Company");

		const $hero = $(`
			<section class="imed-home-hero" aria-label="${frappe.utils.escape_html(t("Welcome", "ترحيب"))}">
				<div class="imed-home-hero__text">
					<div class="imed-home-hero__eyebrow">
						${frappe.utils.icon(hello.icon, "sm")}
						<span>${frappe.utils.escape_html(today())}</span>
					</div>
					<h1 class="imed-home-hero__title">
						${frappe.utils.escape_html(hello.text)}${name ? t(", ", "، ") + frappe.utils.escape_html(name) : ""}
					</h1>
					<p class="imed-home-hero__subtitle">
						${frappe.utils.escape_html(t("What would you like to do today?", "تحب تبدأ بإيه النهارده؟"))}
						${company ? `<span class="imed-home-hero__company">${frappe.utils.escape_html(company)}</span>` : ""}
					</p>
					<div class="imed-home-hero__actions" role="list"></div>
				</div>
				<div class="imed-home-hero__art" aria-hidden="true"></div>
			</section>
		`);

		const $actions = $hero.find(".imed-home-hero__actions");
		QUICK_ACTIONS.filter((a) => {
			try {
				return a.allowed();
			} catch (e) {
				return false;
			}
		}).forEach((a) => {
			$(`<button type="button" class="imed-home-action" role="listitem">
					${frappe.utils.icon(a.icon, "sm")}
					<span>${frappe.utils.escape_html(a.label())}</span>
				</button>`)
				.on("click", a.go)
				.appendTo($actions);
		});
		if (!$actions.children().length) $actions.remove();
		return $hero;
	}

	function decorate(wrapper) {
		const $wrapper = $(wrapper || document).find(".desktop-wrapper").addBack(".desktop-wrapper").first();
		if (!$wrapper.length || $wrapper.find(".imed-home-hero").length) return;

		build_hero().insertAfter($wrapper.find(".desktop-navbar").first());

		// The box reads like the field it becomes ("Search or type a command"), not just "Search".
		const $label = $wrapper.find("#desktop-navbar-modal-search .desktop-search-icon").first();
		if ($label.length && !$label.find(".imed-search-placeholder").length) {
			$label.contents().filter((i, node) => node.nodeType === 3).remove();
			$label.append(
				`<span class="imed-search-placeholder">${frappe.utils.escape_html(__("Search or type a command"))}</span>`
			);
		}

		// A "Search" button beside the search box; it opens the same search window as the box.
		const $search = $wrapper.find(".desktop-search-wrapper").first();
		if ($search.length && !$search.find(".imed-search-btn").length) {
			$(`<button type="button" class="imed-search-btn">
					${frappe.utils.icon("search", "sm")}
					<span>${frappe.utils.escape_html(t("Search", "بحث"))}</span>
				</button>`)
				.on("click", () => $search.find("#desktop-navbar-modal-search").trigger("click"))
				.appendTo($search);
		}

		// A heading over the app grid.
		const $grid = $wrapper.find(".desktop-container > .icons-container").first();
		if ($grid.length && !$grid.find(".imed-home-apps-title").length) {
			$(`<h2 class="imed-home-apps-title">${frappe.utils.escape_html(t("Apps", "التطبيقات"))}</h2>`).prependTo(
				$grid
			);
		}
	}

	// ------------------------------------------------------------------ search
	// Frappe's search always opens in a window. On the home screen that window is placed on the search
	// box itself, so typing feels like typing in the box, with the results dropping down under it.
	// Starting to type anywhere on the home screen opens it with those letters already in it.
	const on_home = () => document.body.dataset.route === "" && $(".desktop-wrapper:visible").length > 0;
	const search_box = () => $(".desktop-search-wrapper #desktop-navbar-modal-search:visible").first();
	let pending_text = "";

	// The typing field is laid exactly over the box (same place and size), so clicking the box only
	// shows a cursor in it; the results hang underneath.
	function anchor_search($modal) {
		const $box = search_box();
		if (!$box.length || window.innerWidth < 576) return;
		const box = $box[0].getBoundingClientRect();
		$modal.addClass("imed-search-anchored");
		$modal.find(".modal-dialog").css({ top: `${box.top}px`, left: `${box.left}px`, width: `${box.width}px` });
	}

	$(document).on("shown.bs.modal", ".modal", function () {
		const $modal = $(this);
		const $input = $modal.find("#navbar-search");
		if (!$input.length || !on_home()) return;
		anchor_search($modal);
		if (pending_text) {
			$input.val(pending_text).trigger("input");
			pending_text = "";
		}
	});
	$(document).on("hidden.bs.modal", ".modal.imed-search-anchored", function () {
		$(this).removeClass("imed-search-anchored").find(".modal-dialog").css({ top: "", left: "", width: "" });
	});
	$(window).on("resize", () => {
		const $open = $(".modal.imed-search-anchored.show");
		if ($open.length) anchor_search($open);
	});

	// Type-to-search: a printable key on the home screen, outside any field, opens the search with it.
	$(document).on("keydown", (e) => {
		if (!on_home() || e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
		if (e.key.length !== 1 || e.key === " ") return;
		const el = e.target;
		if (el.closest && el.closest("input, textarea, select, [contenteditable=''], [contenteditable='true'], .modal.show"))
			return;
		if ($(".modal.show").length) return;
		const $box = search_box();
		if (!$box.length) return;
		e.preventDefault();
		pending_text = e.key;
		$box.trigger("click");
	});

	$(document).on("desktop_screen", (e, args) => {
		decorate(args && args.desktop && args.desktop.page ? args.desktop.page.body : document);
	});
	// In case the home screen was drawn before this file loaded.
	$(() => decorate(document));
})();
