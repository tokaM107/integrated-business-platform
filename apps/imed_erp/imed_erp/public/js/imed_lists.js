// Copyright (c) 2026, toka mohamed and contributors
// For license information, please see license.txt

// Lists and reports, simple (the owner, 9 Nov 2026: "simple tables, the filters on the side, not on top eating the
// page, a few simple filters; reports printed as PDF; all of it on a phone").
//
//   - A list's or a report's filters move to a panel beside the table (theme §41); a phone opens it from a
//     "Filters" button. Frappe's own filter controls are moved, not copied: they keep working as before.
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
		const page = kind();
		const $page = current();
		if (!page || !$page.length) return;
		const $main = $page.find(".layout-main-section").first();
		const $form = $main.children(".page-form").first();
		if (!$main.length || !$form.length) return;
		// A report with no filters keeps no empty panel.
		const has_filters = $form.find(".standard-filter-section > [data-fieldname], .filter-section > *").length || $form.children(".form-group").length;
		$main.toggleClass("imed-side-filters", !!has_filters);
		if (page.type === "report") add_print($page);
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
			$(`<button type="button" class="btn btn-default btn-sm imed-filters-toggle">${frappe.utils.icon("filter", "sm")}<span>${esc(__("Filters"))}</span></button>`)
				.on("click", () => $main.toggleClass("imed-filters-open"))
				.insertAfter($form);
		}
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
		$items.each(function () {
			$(this).toggleClass("imed-filter-hidden", !keep.includes(this.getAttribute("data-fieldname")));
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
