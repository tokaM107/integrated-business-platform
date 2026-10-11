// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// Stock Count screen: the recorded quantity shows as soon as an item is picked, the difference as soon as
// the counted quantity is typed, and Get Items in Store lists everything the store holds for a full count.
// The server works them out again on save (stock_count.py); this is only so the person counting sees them.

const METHOD = "imed_erp.imederp.doctype.stock_count.stock_count.";

frappe.ui.form.on("Stock Count", {
	setup(frm) {
		frm.set_query("store", () => ({ filters: { is_group: 0 } }));
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Items in Store"), () => get_store_items(frm));
		}
	},

	store(frm) {
		refresh_recorded(frm);
	},
	posting_date(frm) {
		refresh_recorded(frm);
	},
	posting_time(frm) {
		refresh_recorded(frm);
	},
});

frappe.ui.form.on("Stock Count Item", {
	item_code(frm, cdt, cdn) {
		set_recorded(frm, locals[cdt][cdn]);
	},
	counted_qty(frm, cdt, cdn) {
		set_difference(frm, locals[cdt][cdn]);
	},
});

function get_store_items(frm) {
	if (!frm.doc.store) {
		frappe.msgprint(__("Choose the store first."));
		return;
	}
	const fetch = () =>
		frappe.call({
			method: METHOD + "get_store_items",
			args: { store: frm.doc.store, posting_date: frm.doc.posting_date, posting_time: frm.doc.posting_time },
			freeze: true,
			callback({ message }) {
				frm.clear_table("items");
				(message || []).forEach((item) => frm.add_child("items", item));
				frm.refresh_field("items");
				set_totals(frm);
				frappe.show_alert({
					message: __("{0} items. Type the counted quantity of each, 0 if there is none.", [(message || []).length]),
					indicator: "blue",
				});
			},
		});
	if ((frm.doc.items || []).length) {
		frappe.confirm(__("Replace the items already listed with every item in the store?"), fetch);
	} else {
		fetch();
	}
}

function refresh_recorded(frm) {
	(frm.doc.items || []).forEach((row) => set_recorded(frm, row));
}

function set_recorded(frm, row) {
	if (!row.item_code || !frm.doc.store) return;
	frappe.call({
		method: METHOD + "get_recorded",
		args: {
			item_code: row.item_code,
			store: frm.doc.store,
			posting_date: frm.doc.posting_date,
			posting_time: frm.doc.posting_time,
		},
		callback({ message }) {
			frappe.model.set_value(row.doctype, row.name, "recorded_qty", message.recorded_qty);
			frappe.model.set_value(row.doctype, row.name, "valuation_rate", message.valuation_rate);
			set_difference(frm, row);
		},
	});
}

function set_difference(frm, row) {
	// Nothing to compare until the counted quantity is typed.
	const counted = row.counted_qty;
	const difference = counted === null || counted === undefined || counted === "" ? 0 : flt(counted) - flt(row.recorded_qty);
	frappe.model.set_value(row.doctype, row.name, "difference_qty", difference);
	frappe.model.set_value(row.doctype, row.name, "difference_value", flt(difference * flt(row.valuation_rate), 2));
	set_totals(frm);
}

function set_totals(frm) {
	const rows = frm.doc.items || [];
	frm.set_value("items_counted", rows.length);
	frm.set_value("items_with_difference", rows.filter((row) => flt(row.difference_qty)).length);
	frm.set_value("total_difference_value", rows.reduce((sum, row) => sum + flt(row.difference_value), 0));
}
