// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Doctor Debts"] = {
	filters: [
		{
			fieldname: "to_date",
			label: __("As On"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "doctor",
			label: __("Doctor"),
			fieldtype: "Link",
			options: "Customer",
			get_query: () => ({ filters: { customer_group: "طبيب" } }),
		},
		{
			fieldname: "agreement_type",
			label: __("Agreement Type"),
			fieldtype: "Select",
			options: ["", "Books", "App"],
		},
		{
			fieldname: "agreement",
			label: __("Agreement"),
			fieldtype: "Link",
			options: "Doctor Agreement",
			get_query: () => ({ filters: { docstatus: 1 } }),
		},
		{
			// Age ranges in days, as in ERPNext's receivable reports.
			fieldname: "range",
			label: __("Ageing Range"),
			fieldtype: "Data",
			default: "30, 60, 90",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "outstanding" && data && flt(data.outstanding) > 0) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
