// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// Sale of damaged stock by weight: the total is the weight times the price per kilogram, shown as it is
// typed; the server works it out again and posts the invoice on submit.

frappe.ui.form.on("Damaged Stock Sale", {
	setup(frm) {
		frm.set_query("damaged_store", () => ({ filters: { is_group: 0, custom_is_damaged_store: 1 } }));
		frm.set_query("item_code", "items", () => ({ filters: { is_stock_item: 1 } }));
		frm.set_query("damage_entry", "items", (doc, cdt, cdn) => ({
			filters: { docstatus: 1, damaged_store: doc.damaged_store },
		}));
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
				__("Sold {0} {1} at {2}: {3}, invoiced in {4}.", [
					frm.doc.weight,
					frm.doc.weight_uom,
					format_currency(frm.doc.rate),
					format_currency(frm.doc.amount),
					frm.doc.sales_invoice,
				]),
				"green"
			);
		}
	},

	weight(frm) {
		frm.trigger("calculate");
	},
	rate(frm) {
		frm.trigger("calculate");
	},
	calculate(frm) {
		const rate = flt(frm.doc.rate, precision("rate"));
		frm.set_value("amount", flt(flt(frm.doc.weight) * rate, precision("amount")));
	},
});

frappe.ui.form.on("Damaged Stock Sale Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code || !frm.doc.damaged_store) return;
		frappe
			.call("imed_erp.imederp.doctype.damaged_stock_sale.damaged_stock_sale.get_damaged_qty", {
				item_code: row.item_code,
				store: frm.doc.damaged_store,
			})
			.then((r) => frappe.model.set_value(cdt, cdn, "available_qty", r.message));
	},
});
