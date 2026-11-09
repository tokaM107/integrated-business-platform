// شاشة المحاسب: the accountant's own screen (the owner, 9 Nov 2026: "an accountant's account and the screen he should
// see"). The company's money at a glance, what waits on him (each a count that opens the list of those documents),
// the documents he makes most, and what each cash box holds. From imederp/accountant_desk.py; what he may open is
// decided on the server, this page only shows.
frappe.pages["imed-accountant"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("شاشة المحاسب"), single_column: true });
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const money = (v) => format_currency(Number(v) || 0, frappe.defaults.get_default("currency") || "EGP", 0);
	const icon = (name, size = "md") => frappe.utils.icon(name, size);
	const go_icon = () => icon(frappe.utils.is_rtl() ? "chevron-left" : "chevron-right", "sm");
	const greeting = () => (new Date().getHours() < 12 ? __("صباح الخير") : __("مساء الخير"));
	const long_day = () => new Date().toLocaleDateString("ar-EG", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
	const short_box = (a) => (a || "").replace(/\s+-\s+[^-]+$/, "");
	const $body = $(`<div class="imed-accountant"></div>`).appendTo(page.main);
	page.set_secondary_action(__("Refresh"), () => load(), "refresh");

	// Each figure's tone and icon; a figure the accountant opens the report of.
	const FIGURES = {
		cash: { tone: "teal", icon: "wallet", report: "Cash Box Balances" },
		revenue: { tone: "green", icon: "trending-up", report: "Revenue by Period" },
		expenses: { tone: "orange", icon: "trending-down", report: "Expense Report" },
		owed_to_us: { tone: "blue", icon: "users", report: "Accounts Receivable" },
		we_owe: { tone: "red", icon: "file-text", report: "Accounts Payable" },
	};
	const WAITING = {
		expenses: { tone: "orange", icon: "receipt" },
		handovers: { tone: "teal", icon: "hand" },
		discrepancies: { tone: "red", icon: "triangle-alert" },
		closes: { tone: "amber", icon: "lock" },
		weeks: { tone: "violet", icon: "calendar" },
		doctors: { tone: "blue", icon: "user" },
	};
	// The documents he makes most, each a new one.
	const ACTIONS = [
		{ doctype: "Expense", label: __("مصروف جديد"), hint: __("مصروف من خزنة"), tone: "orange", icon: "receipt" },
		{ doctype: "Payment Entry", label: __("سند قبض أو صرف"), hint: __("فلوس داخلة أو خارجة"), tone: "green", icon: "wallet" },
		{ doctype: "Journal Entry", label: __("قيد يومية"), hint: __("تسوية أو تحويل بين حسابات"), tone: "blue", icon: "book-open" },
		{ doctype: "Treasury Close", label: __("تقفيل خزنة"), hint: __("عدّ الخزنة آخر اليوم"), tone: "teal", icon: "lock" },
		{ doctype: "Inter Business Transfer", label: __("تحويل بين الأنشطة"), hint: __("من نشاط لنشاط"), tone: "violet", icon: "repeat" },
		{ doctype: "Weekly Cash Reconciliation", label: __("مراجعة الأسبوع"), hint: __("مطابقة خزن الأسبوع"), tone: "cyan", icon: "calendar" },
	];

	function render(d) {
		const waiting = d.waiting || [];
		const total = waiting.reduce((s, w) => s + (w.count || 0), 0);
		const state = total
			? `<span class="imed-accountant__state tone-orange">${esc(__("{0} حاجة مستنياك", [total]))}</span>`
			: `<span class="imed-accountant__state tone-green">${esc(__("مفيش حاجة مستنياك ✓"))}</span>`;
		const figures = (d.figures || [])
			.map((f) => {
				const m = FIGURES[f.key] || { tone: "gray", icon: "wallet" };
				return `<button type="button" class="imed-accountant__figure tone-${m.tone}" data-report="${esc(m.report || "")}">
					<span class="imed-accountant__figure-icon">${icon(m.icon)}</span>
					<small>${esc(f.label)}</small>
					<b>${esc(money(f.value))}</b>
				</button>`;
			})
			.join("");
		const tasks = waiting
			.map((w, i) => {
				const m = WAITING[w.key] || { tone: "gray", icon: "list" };
				return `<button type="button" class="imed-accountant__task tone-${m.tone} ${w.count ? "" : "is-done"}" data-waiting="${i}">
					<span class="imed-accountant__task-icon">${icon(m.icon)}</span>
					<span class="imed-accountant__task-text">${esc(w.label)}</span>
					<span class="imed-accountant__count">${w.count ? esc(w.count) : "✓"}</span>
				</button>`;
			})
			.join("");
		const actions = ACTIONS.filter((a) => frappe.model.can_create(a.doctype))
			.map(
				(a) => `<button type="button" class="imed-accountant__action tone-${a.tone}" data-new="${esc(a.doctype)}">
					<span class="imed-accountant__action-icon">${icon(a.icon)}</span>
					<span><b>${esc(a.label)}</b><small>${esc(a.hint)}</small></span>
					<span class="imed-accountant__go">${go_icon()}</span>
				</button>`
			)
			.join("");
		const boxes = (d.boxes || [])
			.map((b) => `<tr><td>${esc(short_box(b.account))}</td><td class="num ${b.balance < 0 ? "neg" : ""}">${esc(money(b.balance))}</td></tr>`)
			.join("");

		$body.html(`
			<div class="imed-accountant__hero">
				<span class="imed-accountant__hero-icon">${icon("wallet", "lg")}</span>
				<div class="imed-accountant__hero-text">
					<small>${esc(greeting())}</small>
					<h2>${esc(d.user || __("المحاسب"))}</h2>
					<span>${esc(long_day())}</span>
				</div>
				${state}
			</div>
			<div class="imed-accountant__figures">${figures}</div>
			<div class="imed-accountant__grid">
				<section class="imed-accountant__card">
					<h4>${esc(__("مستنياك"))}</h4>
					<div class="imed-accountant__tasks">${tasks || `<p class="text-muted">${esc(__("مفيش حاجة."))}</p>`}</div>
				</section>
				<section class="imed-accountant__card">
					<h4>${esc(__("اعمل"))}</h4>
					<div class="imed-accountant__actions">${actions}</div>
				</section>
			</div>
			<section class="imed-accountant__card">
				<h4>${esc(__("الخزن دلوقتي"))} <a class="imed-accountant__more" data-report="Cash Box Balances">${esc(__("التفاصيل"))}</a></h4>
				${boxes ? `<table class="imed-accountant__boxes"><tbody>${boxes}</tbody></table>` : `<p class="text-muted">${esc(__("مفيش فلوس في الخزن."))}</p>`}
			</section>`);

		$body.find("[data-report]").on("click", function () {
			const report = $(this).attr("data-report");
			if (report) frappe.set_route("query-report", report);
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
