// شاشة المحاسب: the accountant's own screen, as the owner approved its design (10 Nov 2026: "what matters to the
// accountant"). Today's cash, what waits on him (each with a line saying what it is, opening its list), each safe and
// whether its day was closed, the month by business, the money outside (customers, suppliers, doctors), and the
// documents he makes most. From imederp/accountant_desk.py; what he may open is decided on the server.
frappe.pages["imed-accountant"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("شاشة المحاسب"), single_column: true });
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const money = (v) => format_currency(Number(v) || 0, frappe.defaults.get_default("currency") || "EGP", 0);
	const icon = (name, size = "md") => frappe.utils.icon(name, size);
	const greeting = () => (new Date().getHours() < 12 ? __("صباح الخير") : __("مساء الخير"));
	const long_day = () => new Date().toLocaleDateString("ar-EG", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
	const $body = $(`<div class="imed-accountant"></div>`).appendTo(page.main);
	page.set_secondary_action(__("Refresh"), () => load(), "refresh");

	const WAITING = {
		expenses: { tone: "orange", icon: "receipt" },
		purchases: { tone: "green", icon: "shopping-cart" },
		handovers: { tone: "teal", icon: "hand" },
		discrepancies: { tone: "red", icon: "triangle-alert" },
		closes: { tone: "amber", icon: "lock" },
		weeks: { tone: "violet", icon: "calendar" },
		doctors: { tone: "blue", icon: "user" },
	};
	const OUTSIDE = { customers: "blue", suppliers: "red", doctors: "violet" };
	// The documents he makes most, each a new one.
	const ACTIONS = [
		{ doctype: "Expense", label: __("مصروف جديد"), tone: "orange", icon: "receipt" },
		{ doctype: "Payment Entry", label: __("سند قبض / صرف"), tone: "green", icon: "wallet" },
		{ doctype: "Treasury Close", label: __("تقفيل خزنة"), tone: "teal", icon: "lock" },
		{ doctype: "Journal Entry", label: __("قيد يومية"), tone: "blue", icon: "book-open" },
		{ doctype: "Inter Business Transfer", label: __("تحويل بين الأنشطة"), tone: "violet", icon: "repeat" },
		{ doctype: "Purchase Invoice", label: __("فاتورة شراء"), tone: "green", icon: "shopping-cart" },
	];

	const figure = (tone, label, value, detail, attrs = "") =>
		`<div class="imed-accountant__fig tone-${tone}" ${attrs}><small>${esc(label)}</small><b>${value}</b>${detail ? `<span>${esc(detail)}</span>` : ""}</div>`;

	function render(d) {
		const t = d.today || {};
		const waiting = d.waiting || [];
		const total = waiting.reduce((s, w) => s + (w.count || 0), 0);
		const state = total
			? `<span class="imed-accountant__state tone-orange">${esc(__("{0} حاجة مستنياك", [total]))}</span>`
			: `<span class="imed-accountant__state tone-green">${esc(__("مفيش حاجة مستنياك ✓"))}</span>`;
		const not_closed = t.not_closed || [];

		const today = [
			figure("teal", __("الكاش في الخزن دلوقتي"), esc(money(t.cash)), __("الخزن بس، من غير البنوك والمحافظ"), `data-report="Cash Box Balances"`),
			figure("green", __("اتحصّل النهارده"), esc(money(t.came)), __("دخل الخزن النهارده")),
			figure("red", __("اتصرف النهارده"), esc(money(t.went)), __("طلع من الخزن النهارده")),
			figure(
				not_closed.length ? "amber" : "green",
				__("خزن لسه متقفلتش"),
				not_closed.length ? esc(__("{0} من {1}", [not_closed.length, t.closable || 0])) : "✓",
				not_closed.length ? not_closed.join("، ") : __("كل الخزن اتقفلت النهارده"),
				`data-list="Treasury Close"`
			),
		].join("");

		const tasks = waiting
			.map((w, i) => {
				const m = WAITING[w.key] || { tone: "gray", icon: "list" };
				return `<button type="button" class="imed-accountant__task tone-${m.tone} ${w.count ? "" : "is-done"}" data-waiting="${i}">
					<span class="imed-accountant__task-icon">${icon(m.icon)}</span>
					<span class="imed-accountant__task-text"><b>${esc(w.label)}</b><small>${esc(w.detail || "")}</small></span>
					<span class="imed-accountant__count">${w.count ? esc(w.count) : "✓"}</span>
				</button>`;
			})
			.join("");

		const safes = d.safes || [];
		const safe_rows = safes
			.map((s) => {
				const closed = s.closed_today === null || s.closed_today === undefined ? `<span class="imed-accountant__muted">—</span>` : s.closed_today ? `<span class="imed-accountant__ok">✓ ${esc(__("اتقفلت"))}</span>` : `<span class="imed-accountant__no">${esc(__("لسه"))}</span>`;
				return `<tr><td>${esc(s.label)}</td><td class="num ${s.balance < 0 ? "neg" : ""}">${esc(money(s.balance))}</td><td>${closed}</td></tr>`;
			})
			.join("");
		const safes_total = safes.reduce((sum, s) => sum + (Number(s.balance) || 0), 0);

		const month = d.month || { rows: [], total: {} };
		const month_rows = (month.rows || [])
			.map((r) => `<tr><td>${esc(r.business)}</td><td class="num">${r.revenue ? esc(money(r.revenue)) : "—"}</td><td class="num">${r.expenses ? esc(money(r.expenses)) : "—"}</td><td class="num ${r.net < 0 ? "neg" : ""}">${esc(money(r.net))}</td></tr>`)
			.join("");
		const mt = month.total || {};

		const outside = (d.outside || []).map((o) => figure(OUTSIDE[o.key] || "gray", o.label, esc(money(o.value)), o.detail, `data-report="${esc(o.report)}"`)).join("");

		const actions = ACTIONS.filter((a) => frappe.model.can_create(a.doctype))
			.map((a) => `<button type="button" class="imed-accountant__act tone-${a.tone}" data-new="${esc(a.doctype)}"><span class="imed-accountant__act-icon">${icon(a.icon, "sm")}</span>${esc(a.label)}</button>`)
			.join("");

		$body.html(`
			<div class="imed-accountant__hero">
				<div class="imed-accountant__hero-text">
					<small>${esc(greeting())}</small>
					<h2>${esc(d.user || __("المحاسب"))}</h2>
					<span>${esc(long_day())}</span>
				</div>
				${state}
			</div>

			<h3 class="imed-accountant__h">${esc(__("النهارده"))}</h3>
			<div class="imed-accountant__today">${today}</div>

			<div class="imed-accountant__grid">
				<section class="imed-accountant__card">
					<h4>${esc(__("مستنياك"))} <small>${esc(__("دوس على أي واحدة تفتحلك القايمة"))}</small></h4>
					<div class="imed-accountant__tasks">${tasks || `<p class="text-muted">${esc(__("مفيش حاجة."))}</p>`}</div>
				</section>
				<section class="imed-accountant__card">
					<h4>${esc(__("الخزن"))} <small>${esc(__("رصيد كل خزنة، واتقفلت النهارده ولا لأ"))}</small></h4>
					${
						safe_rows
							? `<table class="imed-accountant__table"><thead><tr><th>${esc(__("الخزنة"))}</th><th class="num">${esc(__("الرصيد"))}</th><th>${esc(__("تقفيل النهارده"))}</th></tr></thead>
								<tbody>${safe_rows}</tbody><tfoot><tr><td>${esc(__("الإجمالي"))}</td><td class="num">${esc(money(safes_total))}</td><td></td></tr></tfoot></table>`
							: `<p class="text-muted">${esc(__("مفيش خزن."))}</p>`
					}
				</section>
			</div>

			<section class="imed-accountant__card imed-accountant__block">
				<h4>${esc(__("الشهر ده لكل نشاط"))} <small>${esc(__("من {0} لحد النهارده", [frappe.datetime.str_to_user(month.from)]))}</small></h4>
				<table class="imed-accountant__table">
					<thead><tr><th>${esc(__("النشاط"))}</th><th class="num">${esc(__("الإيرادات"))}</th><th class="num">${esc(__("المصروفات"))}</th><th class="num">${esc(__("الصافي"))}</th></tr></thead>
					<tbody>${month_rows || `<tr><td colspan="4" class="text-muted">${esc(__("مفيش حركة الشهر ده."))}</td></tr>`}</tbody>
					<tfoot><tr><td>${esc(__("الإجمالي"))}</td><td class="num">${esc(money(mt.revenue))}</td><td class="num">${esc(money(mt.expenses))}</td><td class="num ${mt.net < 0 ? "neg" : ""}">${esc(money(mt.net))}</td></tr></tfoot>
				</table>
			</section>

			<div class="imed-accountant__grid">
				<section class="imed-accountant__card">
					<h4>${esc(__("الفلوس اللي برة"))} <small>${esc(__("كل واحدة لوحدها"))}</small></h4>
					<div class="imed-accountant__outside">${outside}</div>
				</section>
				<section class="imed-accountant__card">
					<h4>${esc(__("اعمل"))}</h4>
					<div class="imed-accountant__actions">${actions}</div>
				</section>
			</div>`);

		$body.find("[data-report]").on("click", function () {
			const report = $(this).attr("data-report");
			if (report) frappe.set_route("query-report", report);
		});
		$body.find("[data-list]").on("click", function () {
			frappe.set_route("List", $(this).attr("data-list"));
		});
		$body.find("[data-waiting]").on("click", function () {
			const w = waiting[Number($(this).attr("data-waiting"))];
			if (!w) return;
			frappe.route_options = w.filters;
			frappe.set_route("List", w.doctype);
		});
		$body.find("[data-new]").on("click", function () {
			frappe.new_doc($(this).attr("data-new"));
		});
	}

	function load() {
		$body.html(`<div class="imed-accountant__loading">${esc(__("Loading"))}…</div>`);
		frappe.call({ method: "imed_erp.imederp.accountant_desk.overview" }).then((r) => render(r.message || {}));
	}
	wrapper.imed_load = load;
};

frappe.pages["imed-accountant"].on_page_show = function (wrapper) {
	// Frappe shows beside a page the sidebar that links to it; the accountant's sidebar is drawn in the browser
	// (imed_desk_fixes.js), so the page opened by its address got none: it asks for the ImedERP sidebar itself.
	const sidebar = frappe.app && frappe.app.sidebar;
	if (sidebar && sidebar.sidebar_title !== "ImedERP" && frappe.boot.workspace_sidebar_item && frappe.boot.workspace_sidebar_item.imederp) {
		sidebar.setup("ImedERP");
	}
	if (wrapper.imed_load) wrapper.imed_load();
};
