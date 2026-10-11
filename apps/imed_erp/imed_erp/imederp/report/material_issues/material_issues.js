// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Material Issues"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "material_request", label: __("Material Request"), fieldtype: "Link", options: "Material Request" },
		{
			fieldname: "approval_status",
			label: __("Approval Status"),
			fieldtype: "Select",
			options: ["", "Pending Approval", "Approved", "Rejected"],
		},
		{ fieldname: "warehouse", label: __("To Warehouse"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "printing_machine", label: __("Printing Machine"), fieldtype: "Link", options: "Printing Machine" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "requested_by", label: __("Requested By"), fieldtype: "Link", options: "User" },
	],
};
