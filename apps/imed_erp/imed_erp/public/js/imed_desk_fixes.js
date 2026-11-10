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
	// Frappe's sidebar passes an item's route options to a list or a page only. A report item with route options
	// ("Azarita Doctor Sales" / "Mawasah Doctor Sales": one report, each library's cost center; the owner, 9 Nov
	// 2026) gets them in its address too, and the report reads its filters from there.
	const get_path = Item.prototype.get_path;
	Item.prototype.get_path = function () {
		const it = this.item || {};
		if (it.link_type === "Report" && it.route_options && !it.filters) {
			try {
				return frappe.utils.generate_route({ type: "Report", is_query_report: 1, name: it.link_to, route_options: JSON.parse(it.route_options) });
			} catch (e) {
				// a malformed route_options: the plain report, as Frappe would
			}
		}
		// A page item with route options (the daily sales page, a library each) the same: Frappe's route for a page
		// leaves them out of the address; the page reads them from its query.
		if (it.link_type === "Page" && it.route_options) {
			try {
				return `/desk/${frappe.router.slug(it.link_to)}?${$.param(JSON.parse(it.route_options))}`;
			} catch (e) {
				// a malformed route_options: Frappe's own route
			}
		}
		return get_path.apply(this, arguments);
	};
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

// A library's account (role Library Staff) sees in its sidebar the library's things only, on every page (the owner,
// 5 Nov 2026: "anything of the libraries only"; nothing of the studio or the center, nor ERPNext's own items): its
// screen مكتبتي and the records it keeps, each only if the account may open it. The server still decides what
// anyone opens; this only stops offering the rest. The owner and the managers keep their sidebar unchanged.
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
		{ type: "Link", label: __("Daily Printing"), link_type: "Report", link_to: "Daily Printing", icon: "file-text" },
		{ type: "Link", label: __("Stock Counts"), link_type: "DocType", link_to: "Stock Count", icon: "package" },
		{ type: "Link", label: __("طلباتي"), link_type: "DocType", link_to: "Material Request", icon: "send" },
		{ type: "Link", label: __("Printing Machines"), link_type: "DocType", link_to: "Printing Machine", icon: "settings" },
	];
	const can_open = (item) => {
		const user = (frappe.boot && frappe.boot.user) || {};
		if (item.link_type === "DocType") return (user.can_read || []).includes(item.link_to);
		// A report by its name: all_reports holds the reports the user may open (can_get_report holds doctypes).
		if (item.link_type === "Report") return Boolean((user.all_reports || {})[item.link_to]);
		return true;
	};
	// The accountant's account (role Accountant, without the owner's or the system's roles) sees the money only (the
	// owner, 9 Nov 2026: "remove what does not matter to him"): his screen, the cash, the entries, the libraries' sales,
	// the doctors' accounts, the financial reports and the accounts' settings. No bookings, studio, stock, counters,
	// printing or the system's settings. A section none of whose items he may open is left out.
	const is_accountant_account = () => {
		const roles = frappe.user_roles || [];
		return roles.includes("Accountant") && !roles.includes("System Manager") && !roles.includes("Super Admin");
	};
	const section = (label, icon) => ({ type: "Section Break", label: __(label), icon, link_type: "DocType", collapsible: 1, indent: 1, keep_closed: 0 });
	const link = (label, link_type, link_to, route_options) => ({
		type: "Link",
		child: 1,
		collapsible: 1,
		label: __(label),
		link_type,
		link_to,
		...(route_options ? { route_options: JSON.stringify(route_options) } : {}),
	});
	const AZARITA = { cost_center: "مكتبة الأزاريطة - MMG" };
	const MAWASAH = { cost_center: "مكتبة المواساة - MMG" };
	const accountant_items = () => [
		{ type: "Link", label: __("شاشة المحاسب"), link_type: "Page", link_to: "imed-accountant", icon: "wallet" },
		section("Accounts and Cash", "wallet"),
		link("Treasury Close", "DocType", "Treasury Close"),
		link("Cash Handover", "DocType", "Cash Handover"),
		link("Weekly Cash Reconciliation", "DocType", "Weekly Cash Reconciliation"),
		link("Cash Discrepancy", "DocType", "Cash Discrepancy"),
		link("Expense List", "DocType", "Expense"),
		link("Recurring Expenses", "DocType", "Recurring Expense"),
		link("Inter Business Transfer", "DocType", "Inter Business Transfer"),
		section("القيود والمدفوعات", "book-open"),
		link("Payment Entry", "DocType", "Payment Entry"),
		link("Journal Entry", "DocType", "Journal Entry"),
		link("Sales Invoice", "DocType", "Sales Invoice"),
		link("Purchase Invoice", "DocType", "Purchase Invoice"),
		section("Libraries", "book"),
		link("Azarita Invoices", "DocType", "Library Sales Document", AZARITA),
		link("Mawasah Invoices", "DocType", "Library Sales Document", MAWASAH),
		link("Azarita Daily Sales", "Page", "library-daily-sales", AZARITA),
		link("Mawasah Daily Sales", "Page", "library-daily-sales", MAWASAH),
		link("Azarita Doctor Sales", "Report", "Library Doctor Sales", AZARITA),
		link("Mawasah Doctor Sales", "Report", "Library Doctor Sales", MAWASAH),
		section("Doctors and Books", "users"),
		link("Doctors Ledger", "DocType", "Doctor Ledger Entry"),
		link("Doctor Statement", "Report", "Doctor Statement"),
		link("Doctor Receivables", "Report", "Doctor Receivables"),
		link("Doctor Debts", "Report", "Doctor Debts"),
		link("Doctor Agreements", "DocType", "Doctor Agreement"),
		section("Reports", "chart-bar-big"),
		link("Revenue by Period", "Report", "Revenue by Period"),
		link("Profit Before and After Shared Costs", "Report", "Profit Before and After Shared Costs"),
		link("Profit per Business", "Report", "Profit and Loss Statement", { company: "Mohamed Mamdouh group" }),
		link("Cash Box Balances", "Report", "Cash Box Balances"),
		link("Cash Movements", "Report", "General Ledger"),
		link("Outstanding Receivables", "Report", "Outstanding Receivables"),
		link("Who Owes Us", "Report", "Accounts Receivable"),
		link("علينا للناس", "Report", "Accounts Payable"),
		link("Expense Report", "Report", "Expense Report"),
		link("Inter Business Transfers", "Report", "Inter Business Transfers"),
		link("Platform Fees", "Report", "Platform Fees"),
		section("Settings", "settings"),
		link("Expense Categories", "DocType", "Expense Category"),
		link("Allocation Rules", "DocType", "Allocation Rule"),
		link("Expense Settings", "DocType", "Expense Settings"),
		link("Cash Close Settings", "DocType", "Cash Close Settings"),
	];
	// The items he may open, each section holding its own (as Frappe's find_nested_items makes them: create_sidebar
	// takes them nested), and a section only with items left under it.
	const openable = (items) => {
		const out = [];
		let current = null;
		for (let item of items) {
			if (item.type === "Section Break") {
				current = { ...item, nested_items: [] };
				out.push(current);
			} else if (!can_open(item)) {
				continue;
			}
			if (item.link_type === "Report") {
				// Frappe draws a report item from its kind and doctype, as the server sends them with its own items.
				const report = frappe.boot.user.all_reports[item.link_to];
				item = { ...item, report: { report_type: report.report_type, ref_doctype: report.ref_doctype } };
			}
			if (current && item.child) {
				current.nested_items.push({ ...item, nested_items: [], parent: current });
			} else {
				out.push({ ...item, nested_items: [] });
			}
		}
		return out.filter((item) => item.type !== "Section Break" || item.nested_items.length);
	};
	const create_sidebar = Sidebar.prototype.create_sidebar;
	Sidebar.prototype.create_sidebar = function (items) {
		const editing = this.edit_mode || (this.editor && this.editor.edit_mode);
		if (is_library_account() && !editing) items = library_items().filter(can_open);
		else if (is_accountant_account() && !editing) items = openable(accountant_items());
		return create_sidebar.call(this, items);
	};
	Sidebar.prototype.imed_library_patched = true;
})();
