// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Weekly Cash Reconciliation", {
	setup(frm) {
		frm.set_query("business", () => ({ filters: { is_group: 0 } }));
	},
	refresh(frm) {
		if (frm.doc.needs_review) {
			frm.set_intro(__("A close of this week was reopened after the review. Cancel and amend to review the week again."), "orange");
		} else if (frm.doc.docstatus === 0 && (frm.doc.unresolved || frm.doc.earlier_open)) {
			frm.set_intro(__("{0} discrepancies are still open.", [(frm.doc.unresolved || 0) + (frm.doc.earlier_open || 0)]), "orange");
		} else if (frm.doc.docstatus === 0 && !(frm.doc.items || []).length && frm.doc.week_start) {
			frm.set_intro(__("No close was submitted this week."), "blue");
		}
	},
});
