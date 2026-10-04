// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Expense Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
		},
		{
			// A group (e.g. Libraries) includes every business under it.
			fieldname: "activity",
			label: __("Activity"),
			fieldtype: "Link",
			options: "Cost Center",
		},
		{
			// A group category includes every category under it.
			fieldname: "expense_category",
			label: __("Expense Category"),
			fieldtype: "Link",
			options: "Expense Category",
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "treasury",
			label: __("Cash/Bank Account"),
			fieldtype: "Link",
			options: "Account",
			get_query: () => ({ filters: { account_type: ["in", ["Cash", "Bank"]], is_group: 0 } }),
		},
		{
			fieldname: "group_by",
			label: __("Group Totals By"),
			fieldtype: "Select",
			options: [
				"",
				"Expense Category",
				"Activity",
				"Month",
				"Activity and Expense Category",
				"Month, Activity and Expense Category",
			],
		},
	],
};
