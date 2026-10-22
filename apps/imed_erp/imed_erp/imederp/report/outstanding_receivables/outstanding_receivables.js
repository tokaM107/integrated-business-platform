// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Outstanding Receivables"] = {
	filters: [
		{
			fieldname: "cost_center",
			label: __("Business"),
			fieldtype: "Link",
			options: "Cost Center",
			description: __("A group stands for every business under it."),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "payment_status",
			label: __("Payment Status"),
			fieldtype: "Select",
			options: [
				{ value: "", label: __("All") },
				{ value: "Unpaid", label: __("Unpaid") },
				{ value: "Partly Paid", label: __("Partly Paid") },
				{ value: "Overdue", label: __("Overdue") },
			],
		},
		{
			fieldname: "kind",
			label: __("Show"),
			fieldtype: "Select",
			options: [
				{ value: "", label: __("All") },
				{ value: "Invoiced", label: __("Invoiced") },
				{ value: "Credit", label: __("Customer Credit") },
				{ value: "Not Invoiced", label: __("Not Invoiced") },
			],
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		// Red what is owed on an invoice, orange a booking not invoiced yet; the subtotals in bold.
		if (column.fieldname === "outstanding" && !data.is_subtotal && data.outstanding > 0) {
			const colour = data.voucher_type === "Booking" ? "--text-on-orange" : "--text-on-red";
			value = `<span style="color: var(${colour})">${value}</span>`;
		}
		return data.is_subtotal ? `<b>${value}</b>` : value;
	},
};
