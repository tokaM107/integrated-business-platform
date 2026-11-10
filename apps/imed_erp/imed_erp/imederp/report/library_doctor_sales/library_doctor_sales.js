// The library system's own report, from the invoices mirrored here (imederp/library_sync/reports.py).
frappe.query_reports["Library Doctor Sales"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{
			fieldname: "cost_center",
			label: __("Library"),
			fieldtype: "Link",
			options: "Cost Center",
			default: "مكتبة الأزاريطة - MMG",
			// Chosen by its tab at the top (the owner, 9 Nov 2026: one sidebar item, the libraries as tabs).
			hidden: 1,
			on_change: () => {
				const report = frappe.query_report;
				const cc = report.get_filter_value("cost_center");
				const text = cc ? `${__("Library Doctor Sales")} · ${cc.replace(/\s+-\s+[^-]+$/, "")}` : __("Library Doctor Sales");
				window.imed_head_title ? window.imed_head_title(report.page, text) : report.page.set_title(text);
				report.refresh();
			},
			get_query: () => ({ filters: { is_group: 0, cost_center_name: ["like", "مكتبة%"] } }),
		},
	],
	onload(report) {
		const show = () => {
			const cc = report.get_filter_value("cost_center");
			if (cc && window.imed_head_title) window.imed_head_title(report.page, `${__("Library Doctor Sales")} · ${cc.replace(/\s+-\s+[^-]+$/, "")}`);
			const $main = $(report.page.main);
			// Before the report's first own child (not the tabs made on an earlier visit: one set of tabs).
			const $first = $main.children().not(".imed-lib-tabs").first();
			if (window.imed_library_tabs && $first.length)
				window.imed_library_tabs($first, report.get_filter_value("cost_center"), (cc) => report.set_filter_value("cost_center", cc));
		};
		setTimeout(show, 300);
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "returned_value" && data.returned_value > 0) value = `<span style="color: var(--red-600)">${value}</span>`;
		if (data && column.fieldname === "net_value") value = `<b>${value}</b>`;
		return value;
	},
};
