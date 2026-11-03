// "Log out" at the bottom of the sidebar (the owner's picture of 2 Nov 2026), built like Frappe's own items so the
// sidebar's look (imed_theme.css §27) applies to it. It does what the user menu's "Log out" does
// (frappe.app.logout); the menu keeps its own.
(() => {
	function add_logout() {
		const $sidebar = $(".body-sidebar").first();
		if (!$sidebar.length || $sidebar.children(".imed-sidebar-logout").length) return;
		const label = __("Log out");
		const $item = $(`
			<div class="imed-sidebar-logout" title="${frappe.utils.escape_html(label)}">
				<div class="standard-sidebar-item">
					<a class="item-anchor" role="button" tabindex="0">
						<span class="sidebar-item-icon">${frappe.utils.icon("log-out", "sm")}</span>
						<span class="sidebar-item-label">${frappe.utils.escape_html(label)}</span>
					</a>
				</div>
			</div>`);
		$item.find(".item-anchor").on("click", () => frappe.app.logout()).on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				frappe.app.logout();
			}
		});
		// A direct child of the sidebar, so its place is set by the sidebar's order (last).
		$sidebar.append($item);
	}

	// The sidebar is drawn by Frappe after boot and redrawn when switching modules.
	frappe.router && frappe.router.on("change", () => setTimeout(add_logout, 0));
	$(() => {
		add_logout();
		setTimeout(add_logout, 1000);
	});
})();
