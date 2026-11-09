// The library system's own report, from the invoices mirrored here (imederp/library_sync/reports.py).
frappe.query_reports["Library Sales by Item"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{
			fieldname: "cost_center",
			label: __("Library"),
			fieldtype: "Link",
			options: "Cost Center",
			default: "مكتبة الأزاريطة - MMG",
			get_query: () => ({ filters: { is_group: 0, cost_center_name: ["like", "مكتبة%"] } }),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "returned_value" && data.returned_value > 0) value = `<span style="color: var(--red-600)">${value}</span>`;
		if (data && column.fieldname === "net_value") value = `<b>${value}</b>`;
		// An item group: its name as a heading; a group's total and the grand total in bold, the grand total tinted.
		if (data && data.is_group) return column.fieldname === "product_name" ? `<b style="color: var(--imed-teal-700, var(--primary))">${value}</b>` : "";
		if (data && data.is_grand_total) return `<b style="color: var(--imed-teal-700, var(--primary))">${value}</b>`;
		if (data && data.is_total) return `<b>${value}</b>`;
		return value;
	},
};
