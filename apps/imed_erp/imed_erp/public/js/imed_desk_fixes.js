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
