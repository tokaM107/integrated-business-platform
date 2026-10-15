// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Doctor Receivables"] = {
	filters: [
		{
			// Left empty, the opening is zero and every entry up to To Date is a movement.
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
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
			fieldname: "agreement",
			label: __("Agreement"),
			fieldtype: "Link",
			options: "Doctor Agreement",
			get_query: () => ({ filters: { agreement_type: "Books", docstatus: 1 } }),
		},
		{
			// Only the entries of this library: a payout for the agreement as a whole is left out.
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: () => ({ filters: { is_group: 0 } }),
		},
		{
			fieldname: "show_settled",
			label: __("Show Settled Agreements"),
			fieldtype: "Check",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "branch" && data && data.indent && !data.branch) {
			return `<span class="text-muted">${__("Not by branch")}</span>`;
		}
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "outstanding" && !data.indent && flt(data.outstanding) > 0) {
			value = `<span style="color: var(--orange-600); font-weight: 600">${value}</span>`;
		}
		// The entries behind the figure, for checking it (filtered on the agreement and, on a branch row, nothing
		// more: the ledger list has no branch column).
		if (column.fieldname === "entries" && data.agreement && flt(data.entries)) {
			const url = `/app/doctor-ledger-entry?agreement=${encodeURIComponent(data.agreement)}&docstatus=1`;
			value = `<a href="${url}">${value}</a>`;
		}
		if (!data.indent && ["doctor", "agreement"].includes(column.fieldname)) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
	// Agreements, each with its libraries under it (the rows' indent).
	tree: true,
	initial_depth: 1,
};
