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

// Two sidebar items can open the same page on different filters: the hall and studio calendars (URL items), and
// Azarita's and Mawasah's invoices (one list, filtered to each library's cost center). Frappe matches the active
// item on the path alone, so the last of them won: on Azarita's invoices, Mawasah's item was the one lit (the
// owner, 5 Nov 2026). Here the page's path (less a list's "/view/list") and its query are compared with each item's:
// the item whose every filter the page's address carries is the active one (the one with the most such filters if
// several). Values are compared decoded ("+" and "%20" are both a space). A list opened from the sidebar drops the
// filters from its address, so the library invoices list lights its own item (library_sales_document_list.js).
(function () {
	const Sidebar = frappe.ui && frappe.ui.Sidebar;
	if (!Sidebar || Sidebar.prototype.imed_query_patched) return;
	const where = (href) => {
		const url = new URL(href, window.location.origin);
		const path = decodeURIComponent(url.pathname).replace(/\/view\/list\/?$/, "").replace(/\/$/, "");
		return { path, params: url.searchParams };
	};
	const is_route_in_sidebar = Sidebar.prototype.is_route_in_sidebar;
	Sidebar.prototype.is_route_in_sidebar = function () {
		const match = is_route_in_sidebar.apply(this, arguments);
		const here = where(window.location.href);
		let best = null;
		let best_count = 0;
		this.wrapper.find("a[href]").each((_, a) => {
			const href = $(a).attr("href") || "";
			if (!href.startsWith("/")) return;
			const item = where(href);
			if (item.path !== here.path) return;
			const keys = [...item.params.keys()];
			if (keys.length > best_count && keys.every((k) => here.params.get(k) === item.params.get(k))) {
				best = $(a);
				best_count = keys.length;
			}
		});
		if (best) {
			if (this.active_item) this.active_item.removeClass("active-sidebar");
			this.active_item = best.parent();
		}
		return match;
	};
	Sidebar.prototype.imed_query_patched = true;
})();
