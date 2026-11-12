// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// Two buttons: what a run would post from the chosen days (nothing is posted), and a run now. The posting itself
// is imederp/revenue_posting.py.
frappe.ui.form.on("Automatic Revenue Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Preview"), () => {
			frappe
				.xcall("imed_erp.imederp.revenue_posting.preview", {
					studio_from: frm.doc.post_studio ? frm.doc.studio_from : null,
					libraries_from: frm.doc.post_libraries ? frm.doc.libraries_from : null,
				})
				.then((r) => {
					const rows = (r.groups || [])
						.map((g) => `<tr><td>${frappe.utils.escape_html(g.what)}</td><td class="text-right">${g.count}</td><td class="text-right">${format_currency(g.amount)}</td></tr>`)
						.join("");
					const lowered = r.lowered ? `<p class="text-muted">${__("{0} studio amounts were lowered in XStudio after posting: for the accountant.", [r.lowered])}</p>` : "";
					frappe.msgprint({
						title: __("What a Run Would Post"),
						message: rows
							? `<table class="table table-bordered"><thead><tr><th>${__("From")}</th><th class="text-right">${__("Entries")}</th><th class="text-right">${__("Amount")}</th></tr></thead><tbody>${rows}</tbody></table>${lowered}`
							: `<p>${__("Nothing to post: tick what to post and its day first, or everything is already posted.")}</p>${lowered}`,
					});
				});
		});
		frm.add_custom_button(__("Run Now"), () => {
			if (frm.is_dirty()) return frappe.msgprint(__("Save first."));
			frappe.confirm(__("Post to the ledger now what the preview shows?"), () => {
				frappe.xcall("imed_erp.imederp.revenue_posting.run_now").then(() => frm.reload_doc());
			});
		});
	},
});
