// تقرير المبيعات اليومية: a library's daily sales as its own system (Tanmya) prints them (the owner, 9 Nov 2026, with
// photos of that report): each item group as a table of its items, with what was sold, what was returned and the
// net, each as quantity, value before discount, discount and value, closed by the group's total; the period's total
// at the end. From the invoices mirrored here (imederp/library_sync/reports.py daily_sales). Opened from the sidebar
// on one library (?cost_center=..., Azarita by default); the period at the top, the library by its tab; "Print" prints the tables.
frappe.pages["library-daily-sales"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("تقرير المبيعات اليومية"), single_column: true });
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const qty = (v) => (Number(v) || 0).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 3 });
	const money = (v) => (Number(v) || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	const today = frappe.datetime.get_today();
	let loading = false;

	const f_from = page.add_field({ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: today, change: () => load() });
	const f_to = page.add_field({ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: today, change: () => load() });
	const f_cc = page.add_field({
		fieldname: "cost_center",
		label: __("Library"),
		fieldtype: "Link",
		options: "Cost Center",
		default: "مكتبة الأزاريطة - MMG",
		get_query: () => ({ filters: { is_group: 0, cost_center_name: ["like", "مكتبة%"] } }),
		change: () => {
			tabs();
			load();
		},
	});
	page.set_primary_action(__("Print"), () => window.print(), "printer");
	page.set_secondary_action(__("Refresh"), () => load(), "refresh");

	const $body = $(`<div class="imed-daily-sales"></div>`).appendTo(page.main);
	// The library chosen by its tab at the top (the owner, 9 Nov 2026: one sidebar item, the libraries as tabs), not
	// by the field, which stays hidden and holds the choice.
	f_cc.$wrapper.addClass("hidden");
	// The title says the library shown: "المبيعات اليومية · مكتبة المواساة".
	const tabs = () => {
		const cc = f_cc.get_value();
		const text = cc ? `${__("Library Daily Sales")} · ${cc.replace(/\s+-\s+[^-]+$/, "")}` : __("Library Daily Sales");
		window.imed_head_title ? window.imed_head_title(page, text) : page.set_title(text);
		if (window.imed_library_tabs) window.imed_library_tabs($body, cc, (pick) => f_cc.set_value(pick));
	};

	// Sold, returned, net: four figures each, as in the library system's report.
	const SIDES = [
		["sold", __("المبيعات")],
		["returned", __("مرتجعات المبيعات")],
		["net", __("صافي المبيعات")],
	];
	const figures = (r, side) => {
		const before = side === "sold" ? r.sold_before_discount : side === "returned" ? r.returned_before_discount : r.net_before_discount;
		const discount = side === "sold" ? r.sold_discount : side === "returned" ? r.returned_discount : r.net_discount;
		const value = side === "sold" ? r.sold_value : side === "returned" ? r.returned_value : r.net_value;
		const q = side === "sold" ? r.sold_qty : side === "returned" ? r.returned_qty : r.net_qty;
		return `<td class="num">${qty(q)}</td><td class="num">${money(before)}</td><td class="num">${money(discount)}</td><td class="num v">${money(value)}</td>`;
	};
	// One set of column widths for every table, so the grand total lines up under the groups.
	const cols = () => `<colgroup><col class="c-code"><col class="c-name">${"<col>".repeat(12)}</colgroup>`;
	const head = () => `
		<thead>
			<tr>
				<th rowspan="2" class="code">${__("الكود")}</th>
				<th rowspan="2" class="name">${__("اسم الصنف")}</th>
				${SIDES.map(([side, label]) => `<th colspan="4" class="side side-${side}">${label}</th>`).join("")}
			</tr>
			<tr>${SIDES.map(() => `<th>${__("الكمية")}</th><th>${__("قيمة ق الخصم")}</th><th>${__("الخصم")}</th><th>${__("القيمة")}</th>`).join("")}</tr>
		</thead>`;

	function render(r) {
		const library = (r.cost_center || "").replace(/\s+-\s+[^-]+$/, "");
		const period = r.from_date === r.to_date ? frappe.datetime.str_to_user(r.from_date) : `${frappe.datetime.str_to_user(r.from_date)} ← ${frappe.datetime.str_to_user(r.to_date)}`;
		let html = `
			<div class="imed-daily-sales__title">
				<h3>${__("تقرير المبيعات اليومية")}</h3>
				<div>${esc(library || __("كل المكتبات"))} · ${esc(period)}</div>
			</div>`;
		if (!r.groups.length) {
			html += `<div class="imed-daily-sales__empty">${__("مفيش مبيعات في الفترة دي.")}</div>`;
		}
		for (const g of r.groups) {
			html += `
				<div class="imed-daily-sales__group">
					<div class="imed-daily-sales__group-name">${__("مبيعات م الصنف")} ${esc(g.name)}</div>
					<div class="imed-daily-sales__scroll"><table>
						${cols()}${head()}
						<tbody>
							${g.items.map((it) => `<tr><td class="code">${esc(it.product_code)}</td><td class="name">${esc(it.product_name)}</td>${SIDES.map(([s]) => figures(it, s)).join("")}</tr>`).join("")}
						</tbody>
						<tfoot><tr><td colspan="2">${__("إجمالي مبيعات م الصنف")} ${esc(g.name)}</td>${SIDES.map(([s]) => figures(g.total, s)).join("")}</tr></tfoot>
					</table></div>
				</div>`;
		}
		if (r.groups.length) {
			html += `
				<div class="imed-daily-sales__scroll"><table class="imed-daily-sales__grand">${cols()}
					<tbody><tr><td colspan="2">${__("إجمالي البيع")}</td>${SIDES.map(([s]) => figures(r.total, s)).join("")}</tr></tbody>
				</table></div>`;
		}
		$body.html(html);
	}

	function load() {
		if (loading) return;
		const from_date = f_from.get_value() || today;
		const to_date = f_to.get_value() || today;
		loading = true;
		// The address carries the library and the period (Frappe drops a page's query when it opens it): a copied
		// link opens the same report, and the sidebar lights the library's own item (imed_desk_fixes.js).
		const query = $.param({ cost_center: f_cc.get_value() || "", from_date, to_date });
		if (window.location.pathname.endsWith("/library-daily-sales")) window.history.replaceState(window.history.state, "", `${window.location.pathname}?${query}`);
		$body.html(`<div class="imed-daily-sales__empty">${__("Loading")}…</div>`);
		frappe
			.call({ method: "imed_erp.imederp.library_sync.reports.daily_sales", args: { from_date, to_date, cost_center: f_cc.get_value() } })
			.then((res) => render(res.message))
			.always(() => (loading = false));
	}

	// The library (and dates) the sidebar's item or a link asked for, every time the page is shown.
	wrapper.imed_show = () => {
		const asked = Object.assign({}, frappe.utils.get_query_params(), frappe.route_options || {});
		frappe.route_options = null;
		loading = true; // set the fields without a load each
		if (asked.cost_center) f_cc.set_value(asked.cost_center);
		if (asked.from_date) f_from.set_value(asked.from_date);
		if (asked.to_date) f_to.set_value(asked.to_date);
		setTimeout(() => {
			loading = false;
			tabs();
			load();
		}, 50);
	};
};

frappe.pages["library-daily-sales"].on_page_show = function (wrapper) {
	if (wrapper.imed_show) wrapper.imed_show();
};
