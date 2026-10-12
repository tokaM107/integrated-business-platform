// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// The list shows which way each agreement's balance runs (DOC-30), from its type and the balance's sign: a
// negative balance runs the other way (DOC-20). A suspended agreement is grey.
frappe.listview_settings["Doctor Agreement"] = {
	add_fields: ["balance_direction", "balance", "status"],
	get_indicator(doc) {
		if (doc.status === "Suspended") return [__("Suspended"), "gray", "status,=,Suspended"];
		if (!doc.balance_direction) return;
		const owed_to_doctor = (doc.balance_direction === "Owed to Doctor") === flt(doc.balance) >= 0;
		return owed_to_doctor ? [__("Owed to Doctor"), "orange"] : [__("Owed by Doctor"), "blue"];
	},
};
