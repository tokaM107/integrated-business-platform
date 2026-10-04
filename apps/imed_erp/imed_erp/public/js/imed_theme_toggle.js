// One-click light / dark switch, next to the notifications: beside the bell on the home screen, and
// under "Notification" in the sidebar of every other page.
//
// Uses Frappe's own mechanism (the data-theme-mode attribute, frappe.ui.set_theme and the user's
// desk_theme setting), so the choice is saved to the user and the full theme dialog keeps working.
(() => {
	const is_ar = () => (frappe.boot.lang || "").startsWith("ar");
	const t = (en, ar) => (is_ar() ? ar : en);

	const is_dark = () => (frappe.ui.get_current_theme ? frappe.ui.get_current_theme() : document.documentElement.dataset.theme) === "dark";

	// The button offers the other mode: a moon in light mode, a sun in dark mode.
	// Home screen size next to the bell; sidebar size like the other sidebar items.
	const icon = (size) => frappe.utils.icon(is_dark() ? "sun" : "moon", size);
	const label = () => (is_dark() ? t("Light mode", "الوضع النهاري") : t("Dark mode", "الوضع الليلي"));

	function toggle() {
		const next = is_dark() ? "light" : "dark";
		const root = document.documentElement;
		root.classList.add("imed-theme-switching");
		root.setAttribute("data-theme-mode", next);
		frappe.ui.set_theme(next);
		if (frappe.theme_switcher) frappe.theme_switcher.current_theme = next;
		frappe.xcall("frappe.core.doctype.user.user.switch_theme", { theme: next === "dark" ? "Dark" : "Light" });
		refresh();
		// Let the colours change together, then restore normal transitions.
		setTimeout(() => root.classList.remove("imed-theme-switching"), 350);
	}

	function refresh() {
		$(".imed-theme-toggle").each(function () {
			const $b = $(this);
			$b.attr({ "aria-label": label(), title: label(), "aria-pressed": is_dark() ? "true" : "false" });
			$b.find(".imed-theme-toggle__icon").html(icon($b.hasClass("imed-theme-toggle--home") ? "md" : "sm"));
			$b.find(".sidebar-item-label").text(label());
		});
	}

	// Home screen: a round button right before the notification bell.
	function add_to_home(scope) {
		const $bell = $(scope || document).find(".desktop-navbar .desktop-notifications").first();
		if (!$bell.length || $bell.siblings(".imed-theme-toggle").length) return;
		$(`<button type="button" class="btn-reset nav-link text-muted imed-theme-toggle imed-theme-toggle--home">
				<span class="imed-theme-toggle__icon"></span>
			</button>`)
			.on("click", toggle)
			.insertBefore($bell);
		refresh();
	}

	// Other pages: a sidebar item under "Notification", built like Frappe's own items.
	function add_to_sidebar() {
		const $notification = $(".body-sidebar .sidebar-notification").first();
		if (!$notification.length || $notification.siblings(".imed-sidebar-theme").length) return;
		const $item = $(`
			<div class="imed-sidebar-theme" data-toggle="tooltip" data-placement="right">
				<div class="standard-sidebar-item">
					<a class="item-anchor imed-theme-toggle" role="button" tabindex="0">
						<span class="sidebar-item-icon text-ink-gray-7 imed-theme-toggle__icon"></span>
						<span class="sidebar-item-label"></span>
					</a>
				</div>
			</div>`);
		$item.find(".imed-theme-toggle").on("click", toggle).on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				toggle();
			}
		});
		$item.insertAfter($notification);
		refresh();
	}

	$(document).on("desktop_screen", (e, args) => {
		add_to_home(args && args.desktop && args.desktop.page ? args.desktop.page.body : document);
	});
	// The sidebar is drawn by Frappe after boot and redrawn when switching modules.
	frappe.router && frappe.router.on("change", () => setTimeout(add_to_sidebar, 0));
	$(() => {
		add_to_home(document);
		add_to_sidebar();
		// Frappe draws the sidebar a moment after the page; check again shortly.
		setTimeout(add_to_sidebar, 1000);
	});
})();
