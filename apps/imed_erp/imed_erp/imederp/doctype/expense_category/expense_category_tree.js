// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.treeview_settings["Expense Category"] = {
	breadcrumb: "ImedERP",
	// Fields asked for when a category is added from the tree.
	fields: [
		{ fieldtype: "Data", fieldname: "expense_category_name", label: __("Expense Category Name"), reqd: true },
		{ fieldtype: "Check", fieldname: "is_group", label: __("Is Group") },
		{
			fieldtype: "Link",
			fieldname: "expense_account",
			label: __("Expense Account"),
			options: "Account",
			get_query: () => ({ filters: { root_type: "Expense", is_group: 0 } }),
		},
	],
};
