// Small fixes to Frappe's desk, each for something seen in the browser.

// The sidebar's app menu draws an item that has neither an icon name nor an icon file as <img src="undefined">,
// a broken image and a 404 on every page (seen 21 Oct 2026 for ERPNext's "Organization", which ships no icon
// file). Such an item gets Frappe's plain folder icon instead.
(function () {
	const header = frappe.ui && frappe.ui.SidebarHeader;
	if (!header || !header.prototype.add_app_item || header.prototype.add_app_item.imed_patched) return;
	const add_app_item = header.prototype.add_app_item;
	header.prototype.add_app_item = function (item) {
		if (item && !item.icon && !item.icon_url) item.icon = "folder-normal";
		return add_app_item.call(this, item);
	};
	header.prototype.add_app_item.imed_patched = true;
})();

// The sidebar (workspace_sidebar/imederp.json) opens the calendars by URL (Frappe's sidebar has no calendar link
// type), and Frappe shows a URL item to everyone. A URL into a doctype the user may not read (/desk/booking/...) is
// left out here, so nobody is offered a page that would refuse them; the server still decides what anyone opens.
(function () {
	const Item = frappe.ui && frappe.ui.sidebar_item && frappe.ui.sidebar_item.TypeLink;
	if (!Item || Item.prototype.imed_url_patched) return;
	const make = Item.prototype.make;
	Item.prototype.make = function () {
		const it = this.item || {};
		if (it.link_type === "URL" && typeof it.url === "string" && frappe.session.user !== "Administrator") {
			const match = it.url.match(/^\/desk\/([a-z0-9-]+)(?:[/?#]|$)/);
			const can_read = (frappe.boot && frappe.boot.user && frappe.boot.user.can_read) || [];
			if (match && can_read.length && !can_read.some((name) => frappe.router.slug(name) === match[1])) return;
		}
		return make.apply(this, arguments);
	};
	Item.prototype.imed_url_patched = true;
})();

// Two sidebar URLs can share a path and differ in their query (the hall calendar and the studio calendar are the
// same calendar on different filters). Frappe matches the active item on the path alone, so the last one won; when
// an item's full address (path and query) is the page's, that one is the active item.
(function () {
	const Sidebar = frappe.ui && frappe.ui.Sidebar;
	if (!Sidebar || Sidebar.prototype.imed_query_patched) return;
	const is_route_in_sidebar = Sidebar.prototype.is_route_in_sidebar;
	Sidebar.prototype.is_route_in_sidebar = function () {
		const match = is_route_in_sidebar.apply(this, arguments);
		const here = decodeURIComponent(window.location.pathname + window.location.search).replace(/\/$/, "");
		const exact = this.wrapper.find("a[href]").filter((_, a) => decodeURIComponent($(a).attr("href") || "").replace(/\/$/, "") === here);
		if (exact.length) {
			if (this.active_item) this.active_item.removeClass("active-sidebar");
			this.active_item = exact.first().parent();
		}
		return match;
	};
	Sidebar.prototype.imed_query_patched = true;
})();
