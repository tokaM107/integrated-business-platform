// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// DOC-29: a doctor's file shows each of his agreements with its balance, which way it runs (orange: we owe him;
// blue: he owes us) and when it is next settled. The balances stay apart; nothing is offset between them.
frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.customer_group !== "طبيب") return;
		frappe
			.call("imed_erp.imederp.doctype.doctor_agreement.doctor_agreement.get_doctor_summary", { doctor: frm.doc.name })
			.then(({ message }) => {
				if (!message || !message.length) return;
				const esc = frappe.utils.escape_html;
				const rows = message
					.map(
						(a) => `<tr>
							<td><a href="/app/doctor-agreement/${encodeURIComponent(a.agreement)}">${esc(a.agreement)}</a></td>
							<td>${esc(a.agreement_type)}</td>
							<td>${esc(a.status)}</td>
							<td style="color: var(--${a.owed_by_doctor ? "blue" : "orange"}-600)">
								<b>${format_currency(a.balance)}</b> ${esc(a.direction)}</td>
							<td>${a.next_settlement_date ? frappe.datetime.str_to_user(a.next_settlement_date) : ""}</td>
						</tr>`
					)
					.join("");
				frm.dashboard.add_section(
					`<table class="table table-sm" style="margin: 0">
						<thead><tr>
							<th>${__("Agreement")}</th><th>${__("Type")}</th><th>${__("Status")}</th>
							<th>${__("Balance")}</th><th>${__("Next Settlement")}</th>
						</tr></thead>
						<tbody>${rows}</tbody>
					</table>`,
					__("Agreements")
				);
			});
	},
});
