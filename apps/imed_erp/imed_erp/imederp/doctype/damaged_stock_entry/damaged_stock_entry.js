// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// Damaged stock: the damaged store is filled in, and each item's stock and cost show as soon as it is
// picked. The server checks all of it again and works out the loss on save.

frappe.ui.form.on("Damaged Stock Entry", {
	setup(frm) {
		frm.set_query("source_store", () => ({ filters: { is_group: 0, custom_is_damaged_store: 0 } }));
		frm.set_query("damaged_store", () => ({ filters: { is_group: 0, custom_is_damaged_store: 1 } }));
		frm.set_query("item_code", "items", () => ({ filters: { is_stock_item: 1, disabled: 0 } }));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.damaged_store) {
			frappe
				.call("imed_erp.imederp.damaged_stock.default_damaged_store")
				.then((r) => r.message && frm.set_value("damaged_store", r.message));
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.set_intro(
				__("Taken out of {0} as a loss of {1} on {2}; kept in {3} at zero value until sold by weight.", [
					frm.doc.source_store,
					format_currency(frm.doc.total_loss),
					frm.doc.branch,
					frm.doc.damaged_store,
				]),
				"blue"
			);
		}
	},

	source_store(frm) {
		(frm.doc.items || []).forEach((row) => fetch_stock(frm, row.doctype, row.name));
	},
});

frappe.ui.form.on("Damaged Stock Item", {
	item_code(frm, cdt, cdn) {
		fetch_stock(frm, cdt, cdn);
	},
	qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "loss_value", flt(row.qty) * flt(row.valuation_rate));
	},
});

function fetch_stock(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code || !frm.doc.source_store) return;
	frappe
		.call("imed_erp.imederp.doctype.damaged_stock_entry.damaged_stock_entry.get_stock", {
			item_code: row.item_code,
			store: frm.doc.source_store,
			posting_date: frm.doc.posting_date,
			posting_time: frm.doc.posting_time,
		})
		.then((r) => {
			frappe.model.set_value(cdt, cdn, "valuation_rate", r.message.valuation_rate);
			frappe.model.set_value(cdt, cdn, "loss_value", flt(row.qty) * flt(r.message.valuation_rate));
			frappe.show_alert({
				message: __("{0} has {1} {2} in {3}", [row.item_code, r.message.qty, row.stock_uom || "", frm.doc.source_store]),
				indicator: r.message.qty > 0 ? "blue" : "orange",
			});
		});
}
