// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// An approved edition is carried forward (DOC-15) or cancelled because the curriculum changed (DOC-17) only
// through these two buttons; the server records who did it and when (book_edition.py).
frappe.ui.form.on("Book Edition", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		if (frm.doc.status === "Cancelled") {
			frm.set_intro(
				__("Cancelled because the curriculum changed: notice of {0}, received by {1}.", [
					frappe.datetime.str_to_user(frm.doc.notice_date),
					// set_intro shows HTML: a name is text.
					frappe.utils.escape_html(frappe.user.full_name(frm.doc.notice_received_by)),
				]),
				"red"
			);
			return;
		}
		if (!frm.perm[0] || !frm.perm[0].write) return;

		if (frm.doc.remaining_qty > 0) {
			frm.add_custom_button(__("Carry Forward"), () => carry_forward(frm), __("Edition"));
		}
		frm.add_custom_button(
			__("Cancel: Curriculum Changed"),
			() => cancel_for_curriculum_change(frm),
			__("Edition")
		);
	},
});

function carry_forward(frm) {
	frappe.prompt(
		[
			{
				fieldname: "period",
				fieldtype: "Link",
				options: "Academic Period",
				label: __("Carry to Period"),
				reqd: 1,
				get_query: () => ({ filters: { is_closed: 0 } }),
				description: __(
					"The {0} unsold copies go on to this period at their original cost and stay on sale.",
					[frm.doc.remaining_qty]
				),
			},
		],
		({ period }) =>
			frappe
				.call({
					method: "imed_erp.imederp.doctype.book_edition.book_edition.carry_forward",
					args: { edition: frm.doc.name, period },
					freeze: true,
				})
				.then(() => frm.reload_doc()),
		__("Carry Forward"),
		__("Carry Forward")
	);
}

function cancel_for_curriculum_change(frm) {
	frappe.prompt(
		[
			{
				fieldname: "notice_date",
				fieldtype: "Date",
				label: __("Notice Date"),
				reqd: 1,
				default: frappe.datetime.get_today(),
				description: __(
					"The day the doctor said the curriculum changed. You are recorded as the employee who received it."
				),
			},
		],
		({ notice_date }) =>
			frappe
				.call({
					method: "imed_erp.imederp.doctype.book_edition.book_edition.cancel_for_curriculum_change",
					args: { edition: frm.doc.name, notice_date },
					freeze: true,
				})
				.then(() => frm.reload_doc()),
		__("Cancel: Curriculum Changed"),
		__("Cancel Edition")
	);
}
