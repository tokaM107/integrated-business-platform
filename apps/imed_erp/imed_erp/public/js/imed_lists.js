// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// Lists and reports, simple (the owner, 9 Nov 2026: "simple tables, the filters on the side, not on top eating the
// page, a few simple filters; reports printed as PDF; all of it on a phone").
//
//   - A list's or a report's filters sit behind a Filters button above the table, which opens them as a menu
//     (theme §41; the owner, 9 Nov 2026: "a button on top, the list when I press it, the table the page's width").
//     Frappe's own filter controls are moved, not copied: they keep working as before.
//   - A list shows all its rows: the next ones load by themselves as the table's end comes into view (no 20 /
//     100 / 500 buttons).
//   - A list keeps a few simple filters (SIMPLE below, else its first four, never the record's number); the
//     others stay a click away in Frappe's own Filter button.
//   - A report has its PDF and Print buttons in its head.
(() => {
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	const MAX = 4;
	// The simple filters of the lists the owner opens most; any other list keeps its first four.
	const SIMPLE = {
		Booking: ["resource", "booking_date", "status", "customer"],
		Customer: ["customer_name", "mobile_no", "customer_group"],
		"Library Sales Document": ["cost_center", "reg_date", "customer_name"],
		"Material Request": ["set_warehouse", "status", "transaction_date"],
		"Doctor Ledger Entry": ["doctor", "entry_type", "entry_date"],
		Expense: ["cost_center", "approval_status", "posting_date"],
		"Sales Invoice": ["customer", "posting_date", "status"],
		"Journal Entry": ["posting_date", "voucher_type"],
	};

	const kind = () => {
		// Frappe has no route yet while the desk starts.
		const route = (frappe.get_route && frappe.get_route()) || [];
		if (route[0] === "List" && (!route[2] || route[2] === "List" || route[2] === "Report")) return { type: "list", doctype: route[1] };
		if (route[0] === "query-report") return { type: "report", name: route[1] };
		return null;
	};
	const current = () => $(".page-container:visible").first();

	function arrange() {
		readable_charts();
		const page = kind();
		const $page = current();
		if (!page || !$page.length) return;
		const $main = $page.find(".layout-main-section").first();
		const $form = $main.children(".page-form").first();
		if (!$main.length || !$form.length) return;
		// A report with no filters keeps no empty panel.
		const has_filters = $form.find(".standard-filter-section > [data-fieldname], .filter-section > *").length || $form.children(".form-group").length;
		$main.toggleClass("imed-side-filters", !!has_filters);
		if (page.type === "report") {
			add_print($page);
			// A chart drawn before the wrapper was in place is drawn again, once, through it.
			const report = frappe.query_report;
			if (report && report.chart && report.chart_options && report.chart.imed_drawn !== true) {
				report.render_chart(report.chart_options);
				report.chart.imed_drawn = true;
			}
		}
		if (!has_filters) return;
		if (!$form.find(".imed-filters-head").length) {
			$form.prepend(`<div class="imed-filters-head">
					<span>${frappe.utils.icon("filter", "sm")}<b>${esc(__("Filters"))}</b></span>
					<button type="button" class="btn btn-xs imed-filters-close" aria-label="${esc(__("Close"))}">${frappe.utils.icon("x", "sm")}</button>
				</div>`);
			$form.find(".imed-filters-close").on("click", () => $main.removeClass("imed-filters-open"));
		}
		if (page.type === "list") simplify($form, page.doctype);
		if (!$main.children(".imed-filters-toggle").length) {
			$(`<button type="button" class="btn btn-default btn-sm imed-filters-toggle">${frappe.utils.icon("filter", "sm")}<span>${esc(__("Filters"))}</span><b class="imed-filters-count"></b></button>`)
				.on("click", () => $main.toggleClass("imed-filters-open"))
				.insertBefore($form);
		}
		// How many filters are set, on the button.
		const set = (page.type === "list" && window.cur_list && cur_list.filter_area ? cur_list.filter_area.get().length : 0) || 0;
		$main.find(".imed-filters-count").text(set ? set : "");
		if (page.type === "list") {
			load_all($page);
			column_filters($page, page.doctype);
			range_bar($page, page.doctype);
			active_filters($page, page.doctype);
		}
		$main.toggleClass("imed-is-list", page.type === "list");
		// Every list and report page alike: only its main button (lists) or PDF and Print (reports) in the head.
		$page.toggleClass("imed-plain-head", true).toggleClass("imed-report-page", page.type === "report");
		if (!$main.children(".imed-filters-backdrop").length) {
			$(`<div class="imed-filters-backdrop"></div>`).on("click", () => $main.removeClass("imed-filters-open")).appendTo($main);
		}
	}

	// A few simple filters: the doctype's own list (SIMPLE), else its first four; the record's number never.
	function simplify($form, doctype) {
		const $items = $form.find(".standard-filter-section > [data-fieldname]");
		if (!$items.length) return;
		const names = $items.map((i, el) => el.getAttribute("data-fieldname")).get();
		const wanted = (SIMPLE[doctype] || names.filter((n) => n !== "name")).filter((n) => names.includes(n)).slice(0, MAX);
		const keep = wanted.length ? wanted : names.slice(0, MAX);
		const range = date_field(doctype);
		$items.each(function () {
			const name = this.getAttribute("data-fieldname");
			// The date is chosen from/to on the bar above the table, not as one day here.
			$(this).toggleClass("imed-filter-hidden", !keep.includes(name) || name === range);
		});
	}

	// All the rows: the paging buttons go, and the next page loads by itself when the table's end is in view.
	const ends = "IntersectionObserver" in window
		? new IntersectionObserver((entries) =>
				entries.forEach((e) => {
					if (!e.isIntersecting) return;
					const $more = $(e.target).find(".btn-more:visible");
					if (!$more.length || $more.prop("disabled")) return;
					$more.trigger("click");
					// Still in view once the rows came: watch again, so the next page loads too.
					ends.unobserve(e.target);
					setTimeout(() => document.body.contains(e.target) && ends.observe(e.target), 1200);
				})
		  )
		: null;
	function load_all($page) {
		// A hundred at a time, so a long list is all there after a scroll or two.
		if (window.cur_list && cur_list.page_length && cur_list.page_length < 100) cur_list.page_length = 100;
		$page.find(".list-paging-area").each(function () {
			if (this.dataset.imedWatched) return;
			this.dataset.imedWatched = "1";
			this.classList.add("imed-paging");
			ends && ends.observe(this);
		});
	}

	// ---- A filter in each column's head (the owner, 9 Nov 2026: "the filter inside the column itself") ----
	// The column's name opens a small menu under it: tick its values (a status, a hall), a from/to for a date, a
	// lowest/highest for an amount. It goes through Frappe's own filters, so the address and saved filters follow.
	// A phone shows no columns: there the Filters button stays.
	const TEXT = ["Link", "Data", "Select", "Dynamic Link", "Small Text"];
	const DATE = ["Date", "Datetime"];
	const NUMBER = ["Currency", "Float", "Int", "Percent"];
	let $menu = null;

	function field_of($col, doctype) {
		const meta = frappe.get_meta(doctype);
		let name = $col.attr("data-fieldname");
		if (!name && $col.text().trim() === __("Status") && meta && frappe.meta.has_field(doctype, "status")) name = "status";
		if (!name || name === "name") return null;
		const df = frappe.meta.get_docfield(doctype, name);
		if (!df || ![...TEXT, ...DATE, ...NUMBER, "Check"].includes(df.fieldtype)) return null;
		return df;
	}

	const filters_on = (fieldname) => (window.cur_list ? cur_list.filter_area.get().filter((f) => f[1] === fieldname) : []);

	function column_filters($page, doctype) {
		$page.find(".list-row-head .list-row-col").each(function () {
			const $col = $(this);
			const df = field_of($col, doctype);
			if (!df) return;
			const set = filters_on(df.fieldname);
			let $btn = $col.children(".imed-col-filter");
			if (!$btn.length) {
				$btn = $(`<button type="button" class="imed-col-filter" title="${esc(__("Filter"))}">${frappe.utils.icon("filter", "xs")}<b></b></button>`)
					.on("click", (e) => {
						e.preventDefault();
						e.stopPropagation();
						open_menu($col, df, doctype);
					})
					.appendTo($col);
			}
			const n = set.length ? (set[0][2] === "in" && Array.isArray(set[0][3]) ? set[0][3].length : 1) : 0;
			$btn.find("b").text(n || "");
			$col.toggleClass("imed-col-active", !!n);
		});
	}

	function close_menu() {
		if ($menu) $menu.remove();
		$menu = null;
	}
	$(document).on("click", (e) => {
		if ($menu && !$(e.target).closest(".imed-col-menu, .imed-col-filter").length) close_menu();
	});
	frappe.router && frappe.router.on && frappe.router.on("change", close_menu);

	async function open_menu($col, df, doctype) {
		close_menu();
		const set = filters_on(df.fieldname)[0];
		const label = __(df.label);
		$menu = $(`<div class="imed-col-menu"><div class="imed-col-menu__title">${esc(label)}</div><div class="imed-col-menu__body"></div>
				<div class="imed-col-menu__foot">
					<button type="button" class="btn btn-xs btn-default" data-do="clear">${esc(__("Clear filter"))}</button>
					<button type="button" class="btn btn-xs btn-primary" data-do="apply">${esc(__("Apply filter"))}</button>
				</div></div>`).appendTo(document.body);
		const r = $col[0].getBoundingClientRect();
		const width = 260;
		const left = Math.max(8, Math.min(window.innerWidth - width - 8, frappe.utils.is_rtl() ? r.right - width : r.left));
		$menu.css({ top: r.bottom + 6, left, width });
		const $body = $menu.find(".imed-col-menu__body");
		let read;
		if (DATE.includes(df.fieldtype) || NUMBER.includes(df.fieldtype)) {
			const type = DATE.includes(df.fieldtype) ? "date" : "number";
			const op = set ? String(set[2]).toLowerCase() : "";
			const [lo, hi] = (!set ? ["", ""] : op === "between" ? set[3] : op === ">=" ? [set[3], ""] : ["", set[3]]).map((v) =>
				type === "date" && v ? String(v).slice(0, 10) : v
			);
			$body.html(`<label>${esc(type === "date" ? __("From") : __("At least"))}<input type="${type}" class="form-control input-xs" data-k="lo" value="${esc(lo || "")}"></label>
				<label>${esc(type === "date" ? __("To") : __("At most"))}<input type="${type}" class="form-control input-xs" data-k="hi" value="${esc(hi || "")}"></label>`);
			read = () => {
				const lo2 = $body.find('[data-k="lo"]').val();
				const hi2 = $body.find('[data-k="hi"]').val();
				if (lo2 && hi2) return ["between", [lo2, hi2]];
				if (lo2) return [">=", lo2];
				if (hi2) return ["<=", hi2];
				return null;
			};
		} else if (df.fieldtype === "Check") {
			const v = set ? String(set[3]) : "";
			$body.html(["1", "0"].map((x) => `<label class="imed-col-opt"><input type="radio" name="imed-chk" value="${x}" ${v === x ? "checked" : ""}><span>${esc(x === "1" ? __("Yes") : __("No"))}</span></label>`).join(""));
			read = () => {
				const x = $body.find("input:checked").val();
				return x === undefined ? null : ["=", Number(x)];
			};
		} else {
			// The values to tick: a Select's options, else the values the column holds (the first fifty).
			let values = df.fieldtype === "Select" ? (df.options || "").split("\n").filter(Boolean) : null;
			if (!values) {
				$body.html(`<div class="text-muted small">${esc(__("Loading..."))}</div>`);
				// The values of the rows the other filters leave (the halls' list offers no studio rooms).
				const others = cur_list.filter_area.get().filter((f) => f[1] !== df.fieldname);
				const rows = await frappe.db
					.get_list(doctype, { fields: [df.fieldname], filters: others, group_by: df.fieldname, order_by: `${df.fieldname} asc`, limit: 50 })
					.catch(() => []);
				values = rows.map((row) => row[df.fieldname]).filter((v) => v !== null && v !== "");
			}
			const chosen = !set ? [] : set[2] === "in" ? set[3] : [set[3]];
			$body.html(`${values.length > 8 ? `<input type="search" class="form-control input-xs imed-col-search" placeholder="${esc(__("Search"))}">` : ""}
				<div class="imed-col-opts">${values
					.map(
						(v) => `<label class="imed-col-opt"><input type="checkbox" value="${esc(v)}" ${chosen.includes(v) ? "checked" : ""}><span>${esc(df.fieldtype === "Select" ? __(v) : v)}</span></label>`
					)
					.join("") || `<div class="text-muted small">${esc(__("Nothing to choose"))}</div>`}</div>`);
			$body.find(".imed-col-search").on("input", function () {
				const q = this.value.trim().toLowerCase();
				$body.find(".imed-col-opt").each(function () {
					$(this).toggle(!q || $(this).text().toLowerCase().includes(q));
				});
			});
			read = () => {
				const ticked = $body.find("input[type=checkbox]:checked").map((i, el) => el.value).get();
				return ticked.length ? ["in", ticked] : null;
			};
		}
		$menu.on("click", "[data-do]", async function () {
			const value = this.dataset.do === "apply" ? read() : null;
			close_menu();
			await cur_list.filter_area.remove(df.fieldname);
			if (!value) return;
			// One value is "equals" (a standard filter takes it); several go to Frappe's filter list, which keeps "in"
			// (a standard filter would drop a list of values).
			if (value[0] === "in" && value[1].length === 1) value.splice(0, 2, "=", value[1][0]);
			if (value[0] === "in") {
				await cur_list.filter_area.filter_list.add_filters([[doctype, df.fieldname, "in", value[1]]]);
				cur_list.refresh();
			} else {
				await cur_list.filter_area.add([[doctype, df.fieldname, value[0], value[1]]]);
			}
		});
	}

	// ---- The dates a list shows, from/to, above its table (the owner, 9 Nov 2026: "the sales from this date to
	// that, and the date filter showing from this to that") ----
	// The doctype's date (its simple filters' first date, else its first date filter); a range set by a link (the
	// owner's dashboard) or here shows in both boxes, and a change here is Frappe's own "between" filter.
	function date_field(doctype) {
		const meta = frappe.get_meta(doctype);
		if (!meta) return null;
		const is_date = (name) => {
			const df = name && frappe.meta.get_docfield(doctype, name);
			return df && DATE.includes(df.fieldtype);
		};
		const simple = (SIMPLE[doctype] || []).find(is_date);
		if (simple) return simple;
		const df = (meta.fields || []).find((f) => f.in_standard_filter && DATE.includes(f.fieldtype));
		return df ? df.fieldname : null;
	}

	function range_of(fieldname) {
		const set = filters_on(fieldname)[0];
		if (!set) return ["", ""];
		const op = String(set[2]).toLowerCase();
		const day = (v) => (v ? String(v).slice(0, 10) : "");
		if (op === "between" && Array.isArray(set[3])) return [day(set[3][0]), day(set[3][1])];
		if (op === ">=" || op === ">") return [day(set[3]), ""];
		if (op === "<=" || op === "<") return ["", day(set[3])];
		if (op === "=") return [day(set[3]), day(set[3])];
		return ["", ""];
	}

	function range_bar($page, doctype) {
		const fieldname = date_field(doctype);
		const $list = $page.find(".frappe-list").first();
		if (!fieldname || !$list.length || !window.cur_list || cur_list.doctype !== doctype) return;
		let $bar = $list.children(".imed-range");
		if ($bar.length && $bar.attr("data-doctype") !== doctype) {
			$bar.remove();
			$bar = $();
		}
		if (!$bar.length) {
			const label = __(frappe.meta.get_docfield(doctype, fieldname).label);
			$bar = $(`<div class="imed-range" data-doctype="${esc(doctype)}">
					<span class="imed-range__label">${frappe.utils.icon("calendar", "sm")}<b>${esc(label)}</b></span>
					<label><span>${esc(__("From"))}</span><input type="date" class="form-control input-sm" data-k="from"></label>
					<label><span>${esc(__("To"))}</span><input type="date" class="form-control input-sm" data-k="to"></label>
					<button type="button" class="btn btn-xs btn-default imed-range__clear">${esc(__("All dates"))}</button>
					<span class="imed-range__text"></span>
				</div>`).prependTo($list);
			const apply = async () => {
				const from = $bar.find('[data-k="from"]').val();
				const to = $bar.find('[data-k="to"]').val();
				await cur_list.filter_area.remove(fieldname);
				if (from && to) await cur_list.filter_area.add([[doctype, fieldname, "between", from <= to ? [from, to] : [to, from]]]);
				else if (from) await cur_list.filter_area.add([[doctype, fieldname, ">=", from]]);
				else if (to) await cur_list.filter_area.add([[doctype, fieldname, "<=", to]]);
				else cur_list.refresh();
			};
			$bar.on("change", "input", apply);
			$bar.on("click", ".imed-range__clear", () => {
				$bar.find("input").val("");
				apply();
			});
		}
		// The boxes follow the filter (set by a link, a column's menu, the side panel), unless being typed in.
		const [from, to] = range_of(fieldname);
		$bar.find("input").each(function () {
			const value = this.dataset.k === "from" ? from : to;
			if (document.activeElement !== this && this.value !== value) this.value = value;
		});
		// A date kept left to right inside the Arabic sentence (else it reads 2026-11-08).
		const user = (d) => `\u2066${frappe.datetime.str_to_user(d)}\u2069`;
		const text = from && to ? (from === to ? __("On {0}", [user(from)]) : __("From {0} to {1}", [user(from), user(to)]))
			: from ? __("From {0}", [user(from)]) : to ? __("Up to {0}", [user(to)]) : __("All dates");
		const $text = $bar.find(".imed-range__text");
		if ($text.text() !== text) $text.text(text);
		$bar.toggleClass("is-set", !!(from || to));
		$bar.find(".imed-range__clear").toggle(!!(from || to));
	}

	// ---- Every filter the list is under, in words, each with its own remove, and "clear all" (the owner, 9 Nov 2026:
	// the customers' list stayed on one customer, filtered by a name the page did not show) ----
	function filter_words(doctype, f) {
		const [, fieldname, condition, value] = f;
		const df = fieldname === "name" ? { label: __("Name"), fieldtype: "Data" } : frappe.meta.get_docfield(doctype, fieldname) || { label: fieldname };
		const one = (v) => {
			if (df.fieldtype === "Check") return cint(v) ? __("Yes") : __("No");
			if (df.fieldtype === "Select") return __(v);
			if (df.fieldtype === "Link" && typeof v === "string") return v.replace(/\s+-\s+[^-]+$/, "");
			return String(v).replace(/^%|%$/g, "");
		};
		const op = String(condition).toLowerCase();
		const list = Array.isArray(value) ? value.map(one).join("، ") : one(value);
		const text = op === "not in" || op === "!=" ? `${__("Not")} ${list}` : op === "like" ? list : op === ">=" ? `≥ ${list}` : op === "<=" ? `≤ ${list}` : list;
		// The value kept in its own direction (an English name read backwards beside the Arabic label).
		return `${__(df.label)}: \u2068${text}\u2069`;
	}

	function active_filters($page, doctype) {
		const $list = $page.find(".frappe-list").first();
		if (!$list.length || !window.cur_list || cur_list.doctype !== doctype) return;
		// The date shows on its own bar (range_bar); every other filter here.
		const range = date_field(doctype);
		const set = cur_list.filter_area.get().filter((f) => f[1] !== range);
		const key = JSON.stringify(set);
		let $row = $list.children(".imed-active");
		if ($row.length && $row.attr("data-key") === key) return;
		$row.remove();
		if (!set.length) return;
		$row = $(`<div class="imed-active">
				<span class="imed-active__title">${frappe.utils.icon("filter", "sm")}${esc(__("Showing only"))}</span>
				${set
					.map(
						(f) => `<button type="button" class="imed-active__chip" data-field="${esc(f[1])}" title="${esc(__("Remove filter"))}">
								<span>${esc(filter_words(doctype, f))}</span>${frappe.utils.icon("x", "xs")}</button>`
					)
					.join("")}
				<button type="button" class="btn btn-xs btn-default imed-active__clear">${esc(__("Clear all filters"))}</button>
			</div>`).attr("data-key", key);
		const $range = $list.children(".imed-range");
		$range.length ? $row.insertAfter($range) : $row.prependTo($list);
		$row.on("click", ".imed-active__chip", async function () {
			await cur_list.filter_area.remove(this.dataset.field);
		});
		$row.on("click", ".imed-active__clear", async () => {
			await cur_list.filter_area.clear();
			$list.find(".imed-range input").val("");
		});
	}

	// A report's PDF and Print, with no settings to choose: a wide report lies on its side.
	function add_print($page) {
		const $actions = $page.find(".page-head .page-actions").first();
		if (!$actions.length || $actions.find(".imed-print-btns").length) return;
		const run = (how) => {
			const report = frappe.query_report;
			if (!report || !report.datatable) return;
			report.get_validated_visible_indexes();
			const settings = { orientation: report.get_visible_columns().length > 6 ? "Landscape" : "Portrait", include_filters: 1, with_letter_head: 0, columns: [] };
			how === "pdf" ? report.pdf_report(settings) : report.print_report(settings);
		};
		$(`<div class="imed-print-btns">
				<button type="button" class="btn btn-primary btn-sm" data-how="pdf">${frappe.utils.icon("file-text", "sm")}<span>PDF</span></button>
				<button type="button" class="btn btn-default btn-sm" data-how="print">${frappe.utils.icon("printer", "sm")}<span>${esc(__("Print"))}</span></button>
			</div>`)
			.on("click", "button", function () {
				run(this.dataset.how);
			})
			.prependTo($actions);
	}

	// A report's chart, readable (the owner, 9 Nov 2026: its dates read "01-1 ..."): a date label short (2/11), a long
	// axis showing every few labels in full, the page's teal. Wraps Frappe's own drawing once it is loaded.
	const short_label = (label) => {
		const m = String(label).match(/^(\d{4})-(\d{2})-(\d{2})$/) || String(label).match(/^(\d{2})-(\d{2})-(\d{4})$/);
		if (!m) return label;
		const [d, mo] = m[1].length === 4 ? [m[3], m[2]] : [m[1], m[2]];
		return `${Number(d)}/${Number(mo)}`;
	};
	function readable_charts() {
		const QR = frappe.views && frappe.views.QueryReport;
		if (!QR || QR.prototype.imed_chart) return;
		const draw = QR.prototype.render_chart;
		QR.prototype.render_chart = function (options) {
			const o = Object.assign({}, options);
			if (o.data && Array.isArray(o.data.labels)) {
				o.data = Object.assign({}, o.data, { labels: o.data.labels.map(short_label) });
				if (o.data.labels.length > 8) o.axisOptions = Object.assign({}, o.axisOptions, { xIsSeries: true });
			}
			o.height = Math.max(o.height || 0, 260);
			if (!o.colors || !o.colors.length) o.colors = ["#1d9386", "#7c3aed", "#ea580c", "#2563eb", "#16a34a"];
			const out = draw.call(this, o);
			if (this.chart) this.chart.imed_drawn = true;
			return out;
		};
		QR.prototype.imed_chart = true;
	}

	// Frappe draws a list's filters after the route changes, and again when it reloads: arrange on each change.
	let timer = null;
	const later = () => {
		clearTimeout(timer);
		timer = setTimeout(arrange, 150);
	};
	$(() => {
		new MutationObserver(() => kind() && later()).observe(document.body, { childList: true, subtree: true });
		if (frappe.router && frappe.router.on) frappe.router.on("change", later);
		later();
	});
})();
