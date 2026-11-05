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
		const made = make.apply(this, arguments);
		// Frappe opens every URL item in a new tab; one into this site (the hall and studio calendars) opens in the
		// same page like the other items (the owner, 5 Nov 2026). A link to another site keeps its new tab.
		if (it.link_type === "URL" && typeof it.url === "string" && it.url.startsWith("/") && this.wrapper) {
			this.wrapper.find('a[target="_blank"]').removeAttr("target").removeAttr("rel");
		}
		return made;
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

	// Moving inside the site, Frappe lights the item before the address has changed (so the old address was read
	// and the last of the items sharing the path won: the studio calendar lit on the hall calendar). Once the new
	// address is in place, the item matching it exactly (path and filters) is lit, and only it among those sharing
	// its path.
	const relight = () => {
		const here = where(window.location.href);
		let best = null;
		let best_count = 0;
		const $same = $(".body-sidebar a[href]").filter((_, a) => {
			const href = a.getAttribute("href") || "";
			if (!href.startsWith("/")) return false;
			const item = where(href);
			if (item.path !== here.path) return false;
			const keys = [...item.params.keys()];
			if (keys.length > best_count && keys.every((k) => here.params.get(k) === item.params.get(k))) {
				best = $(a);
				best_count = keys.length;
			}
			return true;
		});
		if (!best) return;
		$same.parent().removeClass("active-sidebar");
		best.parent().addClass("active-sidebar");
		if (frappe.app && frappe.app.sidebar) frappe.app.sidebar.active_item = best.parent();
	};
	if (frappe.router && frappe.router.on) frappe.router.on("change", () => setTimeout(relight, 120));
})();

// A library's account (role Library Staff) sees in its sidebar, first, the pages of its library: its screen مكتبتي
// and the records it keeps (the owner, 5 Nov 2026: the sidebar looked empty), then the sidebar's own items as they
// were. Only the library accounts; the owner and the managers keep their sidebar unchanged.
(function () {
	const Sidebar = frappe.ui && frappe.ui.Sidebar;
	if (!Sidebar || Sidebar.prototype.imed_library_patched) return;
	const is_library_account = () => {
		const roles = frappe.user_roles || [];
		return roles.includes("Library Staff") && !roles.includes("System Manager") && !roles.includes("Super Admin");
	};
	const library_items = () => [
		{ type: "Link", label: __("مكتبتي"), link_type: "Page", link_to: "imed-library", icon: "store" },
		{ type: "Link", label: __("Daily Counter Reading"), link_type: "DocType", link_to: "Daily Counter Reading", icon: "gauge" },
		{ type: "Link", label: __("Paper Counters"), link_type: "DocType", link_to: "Printer Reading", icon: "printer" },
		{ type: "Link", label: __("Stock Counts"), link_type: "DocType", link_to: "Stock Count", icon: "package" },
		{ type: "Spacer" },
	];
	const create_sidebar = Sidebar.prototype.create_sidebar;
	Sidebar.prototype.create_sidebar = function (items) {
		if (is_library_account() && !this.edit_mode && !(this.editor && this.editor.edit_mode)) {
			const mine = library_items();
			const have = new Set((items || []).map((i) => `${i.link_type}:${i.link_to}`));
			items = [...mine.filter((i) => i.type !== "Link" || !have.has(`${i.link_type}:${i.link_to}`)), ...(items || [])];
		}
		return create_sidebar.call(this, items);
	};
	Sidebar.prototype.imed_library_patched = true;
})();
