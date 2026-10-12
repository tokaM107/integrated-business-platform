// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The list shows each agreement's direction in its colour (DOC-30), and a suspended one in grey.
frappe.listview_settings["Doctor Agreement"] = {
	add_fields: ["balance_direction", "status"],
	get_indicator(doc) {
		if (doc.status === "Suspended") return [__("Suspended"), "gray", "status,=,Suspended"];
		if (doc.balance_direction === "Owed to Doctor") return [__("Owed to Doctor"), "orange", "balance_direction,=,Owed to Doctor"];
		if (doc.balance_direction === "Owed by Doctor") return [__("Owed by Doctor"), "blue", "balance_direction,=,Owed by Doctor"];
	},
};
