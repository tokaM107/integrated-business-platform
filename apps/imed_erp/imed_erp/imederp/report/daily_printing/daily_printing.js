// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

frappe.query_reports["Daily Printing"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: () => ({ filters: { is_group: 0, parent_cost_center: ["like", "مكتبات 2Be Doctor%"] } }),
		},
		// The cost of a sheet, its price and margin: for the accountant; the owner's table stays short without them.
		{ fieldname: "details", label: __("Cost details"), fieldtype: "Check", default: 0 },
	],
	// On a phone a table of ten columns shows two of them (the user, 11 Nov 2026: "on a mobile it will be worse"):
	// there the same rows are drawn as one card a library a day, its figures on top and its machines under them.
	// The table itself stays for wider screens (imed_theme.css shows one or the other).
	after_datatable_render() {
		imed_printing_cards();
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// The library's day, under its machines, says so where a machine's name would be.
		if (data && data.is_total && column.fieldname === "machine" && !data.machine) value = data.reading_date ? __("The Day's Total") : data.machine_type || "";
		if (data && column.fieldname === "unexplained" && data.unexplained > 0) value = `<span style="color: var(--red-600)">${value}</span>`;
		// The library's day under its machines; a shortfall in red.
		if (data && column.fieldname === "variance_value" && data.variance_value > 0) value = `<span style="color: var(--red-600)">${value}</span>`;
		return data && data.is_total ? `<b>${value}</b>` : value;
	},
};

function imed_printing_cards() {
	const report = frappe.query_report;
	if (!report || report.report_name !== "Daily Printing") return;
	const $wrap = report.page.main.find(".report-wrapper").first();
	if (!$wrap.length) return;
	$wrap.addClass("imed-print-report").find(".imed-pc-list").remove();
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const num = (v) => format_number(v || 0, null, (v || 0) % 1 ? 1 : 0);
	const money = (v) => format_currency(v || 0, frappe.defaults.get_default("currency"));
	const days = [];
	(report.data || []).forEach((r) => {
		if (!r || !r.reading_date) return; // the period's own rows: on the table only
		let day = days[days.length - 1];
		if (!day || day.date !== r.reading_date || day.branch !== r.branch) days.push((day = { date: r.reading_date, branch: r.branch, library: r.library, machines: [], total: null }));
		if (r.is_total) day.total = r;
		else day.machines.push(r);
	});
	const stat = (label, value, cls = "") => `<div class="${cls}"><small>${esc(label)}</small><b>${esc(value)}</b></div>`;
	const cards = days
		.map((d) => {
			const t = d.total || {};
			return `<section class="imed-pc">
					<header><b>${esc(d.library || d.branch)}</b><small>${esc(frappe.datetime.str_to_user(d.date))}</small></header>
					<div class="imed-pc__sum">
						${stat(__("Printed"), num(t.consumed))}${stat(__("Sold"), num(t.sold))}${stat(__("Spoiled"), num(t.spoiled_sheets))}${stat(__("Value Not Sold"), money(t.variance_value), t.variance_value > 0 ? "is-loss" : "")}
					</div>
					<ul>${d.machines
						.map(
							(m) => `<li>
								<span class="imed-pc__machine">${esc(m.machine)}${m.fault ? `<em>${esc(__("Broke Down"))}: ${esc(m.fault)}</em>` : ""}</span>
								<span class="imed-pc__read"><small>${esc(__("Morning"))}</small>${esc(num(m.opening_reading))}</span>
								<span class="imed-pc__read"><small>${esc(__("Evening"))}</small>${esc(num(m.closing_reading))}</span>
								<span class="imed-pc__read is-printed"><small>${esc(__("Printed"))}</small>${esc(num(m.consumed))}</span>
							</li>`
						)
						.join("")}</ul>
				</section>`;
		})
		.join("");
	$wrap.prepend(`<div class="imed-pc-list">${cards || `<p class="imed-pc-empty">${esc(__("Nothing to show"))}</p>`}</div>`);
}
