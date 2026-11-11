// مكتبتي: a library's own screen (owner, 4 Nov 2026: one account a library, as simple as can be). Four big buttons
// (today's counters, something finished, what we hold, ask for more), what the store holds, and the last requests.
// Every action is checked on the server (imederp/library_desk.py); this page only asks and shows.
// مكتبتي is a library account's screen only. Anyone else who reaches it (the owner signing in after the library's
// account signed out on the same browser keeps its last address: 5 Nov 2026) is taken to their own first page.
function imed_not_a_library() {
	const roles = frappe.user_roles || [];
	if (roles.includes("Library Staff")) return false;
	window.location.replace("/desk");
	return true;
}

frappe.pages["imed-library"].on_page_load = function (wrapper) {
	if (imed_not_a_library()) return;
	const API = "imed_erp.imederp.library_desk";
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("مكتبتي"), single_column: true });
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const qty = (v) => (Number(v) || 0).toLocaleString("ar-EG");
	const $body = $(`<div class="imed-library"></div>`).appendTo(page.main);
	let desk = null;

	// The look (owner, 5 Nov 2026: "professional"; theme §35 in imed_theme.css): a header card with the library, a
	// greeting and today's counters, the four actions as cards with an icon each, then what the store holds and the
	// last requests side by side. The actions themselves are unchanged (ACTIONS below).
	const icon = (name) => frappe.utils.icon(name, "md");
	const greeting = () => (new Date().getHours() < 12 ? __("صباح الخير") : __("مساء الخير"));
	const long_day = () => new Date().toLocaleDateString("ar-EG", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
	const store_name = (s) => (s || "").replace(/\s+-\s+[^-]+$/, "");
	// A request's state as a coloured pill: approved green, waiting orange, rejected red, else grey.
	const REQUEST_TONE = { Approved: "green", "Pending Approval": "orange", Rejected: "red" };
	const REQUEST_KIND = { "Material Transfer": __("تحويل من المخزن"), Purchase: __("شراء") };

	function counters_state(counted) {
		if (counted && counted.docstatus === 1) return { tone: "green", text: __("عدادات النهارده اتسجلت ✓") };
		if (counted) return { tone: "orange", text: __("فاضل عدادات آخر اليوم") };
		return { tone: "blue", text: __("سجّل عدادات الصبح") };
	}

	function tile(action, tone, icon_name, title, hint, badge) {
		return `<button type="button" class="imed-library__tile tone-${tone}" data-action="${action}">
				<span class="imed-library__tile-icon">${icon(icon_name)}</span>
				<span class="imed-library__tile-text">
					<b>${esc(title)}</b>
					<small>${esc(hint)}</small>
					${badge ? `<span class="imed-library__badge tone-${badge.tone}">${esc(badge.text)}</span>` : ""}
				</span>
				<span class="imed-library__tile-go">${icon(frappe.utils.is_rtl() ? "chevron-left" : "chevron-right")}</span>
			</button>`;
	}

	// The day's counters a machine: the morning's, the evening's and the sheets printed between them (the owner,
	// 5 Nov 2026: "where are the morning and the evening"). Before the evening only the morning is known.
	function counters_card() {
		const rows = desk.counter_rows || [];
		const done = desk.counter_today && desk.counter_today.docstatus === 1;
		const other_day = desk.counter_date && desk.counter_date !== frappe.datetime.get_today();
		const title = other_day ? __("عدادات يوم {0}", [frappe.datetime.str_to_user(desk.counter_date)]) : __("عدادات النهارده");
		const total = rows.reduce((sum, r) => sum + (Number(r.printed) || 0), 0);
		const cell = (v, cls = "") => `<td class="${cls}">${v == null ? `<span class="imed-library__wait">${esc(__("لسه"))}</span>` : esc(qty(v))}</td>`;
		const body = rows.length
			? `<table class="imed-library__counters">
					<thead><tr><th>${esc(__("المكنة"))}</th><th>${esc(__("الصبح"))}</th><th>${esc(__("آخر اليوم"))}</th><th>${esc(__("اتطبع"))}</th></tr></thead>
					<tbody>${rows
						.map((r) => `<tr><td class="imed-library__machine">${icon("printer")}<span>${esc(r.machine)}</span>${r.fault ? `<span class="imed-library__badge tone-red">${esc(__("عطلت"))}</span>` : ""}</td>${cell(r.morning)}${cell(r.evening)}${cell(r.printed, "is-printed")}</tr>`)
						.join("")}</tbody>
					${done ? `<tfoot><tr><td colspan="3">${esc(__("اتطبع النهارده كله"))}</td><td class="is-printed">${esc(qty(total))} ${esc(__("ورقة"))}</td></tr></tfoot>` : ""}
				</table>`
			: `<p class="imed-library__empty">${icon("gauge")}${esc(__("لسه متسجلتش عدادات الصبح. دوس على «عدادات النهارده» فوق."))}</p>`;
		return `<section class="imed-library__card imed-library__card--wide">
				<h4>${icon("gauge")}${esc(title)}${done ? `<span class="imed-library__badge tone-green">${esc(__("اليوم اتقفل ✓"))}</span>` : rows.length ? `<span class="imed-library__badge tone-orange">${esc(__("مستني آخر اليوم"))}</span>` : ""}</h4>
				${body}
			</section>`;
	}

	function render() {
		const counted = desk.counter_today;
		const items = desk.items || [];
		const requests = desk.requests || [];
		const state = counters_state(counted);
		const stock = items
			.map((i) => {
				const out = !(Number(i.qty) > 0);
				return `<li class="${out ? "is-out" : ""}">
						<span class="imed-library__item">${icon("package")}<span>${esc(i.item_name)}</span></span>
						<b>${out ? esc(__("خلص")) : esc(qty(i.qty))}</b>
					</li>`;
			})
			.join("");
		const asked = requests
			.map((r) => {
				const status = r.custom_approval_status || r.status;
				return `<li>
						<span class="imed-library__item">${icon("file-text")}<span>${esc(REQUEST_KIND[r.material_request_type] || __("طلب"))}<small>${esc(frappe.datetime.str_to_user(r.transaction_date))}</small></span></span>
						<span class="imed-library__badge tone-${REQUEST_TONE[status] || "gray"}">${esc(__(status))}</span>
					</li>`;
			})
			.join("");
		$body.html(`
			<section class="imed-library__hero">
				<div class="imed-library__hero-icon">${icon("store")}</div>
				<div class="imed-library__hero-text">
					<small>${esc(greeting())} 👋</small>
					<h2>${esc(desk.library_name || desk.library)}</h2>
					<span class="imed-library__hero-meta">${icon("calendar")}${esc(long_day())}<i></i>${icon("warehouse")}${esc(store_name(desk.store))}</span>
				</div>
				${
					// While the day's counters are still to be read this is the way to them (it looked like a button
					// and did nothing: the user, 11 Nov 2026); once the day is closed it only says so.
					counted && counted.docstatus === 1
						? `<span class="imed-library__hero-state tone-${state.tone}">${esc(state.text)}</span>`
						: `<button type="button" class="imed-library__hero-state is-action tone-${state.tone}" data-action="counters">${esc(state.text)}</button>`
				}
			</section>
			<div class="imed-library__tiles">
				${tile("counters", "teal", "gauge", __("عدادات النهارده"), counted ? (counted.docstatus === 1 ? __("اتسجلت النهارده ✓") : __("سجّل آخر اليوم")) : __("سجّل الصبح"))}
				${tile("used", "orange", "package-minus", __("حاجة خلصت"), __("إزازة حبر، كرتونة ورق…"))}
				${tile("count", "blue", "clipboard-list", __("رصيد المخزون"), __("اكتب اللي عندنا دلوقتي"))}
				${tile("ask", "violet", "send", __("اطلب حاجة"), __("حبر، ورق…"))}
			</div>
			${counters_card()}
			<div class="imed-library__cards">
				<section class="imed-library__card">
					<h4>${icon("warehouse")}${esc(__("اللي عندنا في المخزن"))}</h4>
					${stock ? `<ul class="imed-library__list">${stock}</ul>` : `<p class="imed-library__empty">${esc(__("مفيش أصناف لسه."))}</p>`}
				</section>
				<section class="imed-library__card">
					<h4>${icon("list")}${esc(__("طلباتي"))}</h4>
					${asked ? `<ul class="imed-library__list">${asked}</ul>` : `<p class="imed-library__empty">${icon("inbox")}${esc(__("مفيش طلبات."))}</p>`}
				</section>
			</div>
		`);
		$body.find("[data-action]").on("click", function () {
			ACTIONS[$(this).data("action")]();
		});
	}

	function load() {
		return frappe.xcall(`${API}.get_desk`).then((r) => {
			desk = r;
			render();
		});
	}

	const options = () => (desk.items || []).map((i) => ({ label: `${i.item_name} (${qty(i.qty)})`, value: i.item_code }));

	function done(message) {
		frappe.show_alert({ message, indicator: "green" }, 4);
		load();
	}

	const ACTIONS = {
		counters() {
			// One number a machine, read off its counter: in the morning, then at the end of the day.
			frappe.xcall(`${API}.counters_today`).then((now) => {
				if (now.phase === "done") return frappe.msgprint(__("عدادات النهارده اتسجلت خلاص ✓"));
				const morning = now.phase === "morning";
				const fields = [
					{
						fieldtype: "HTML",
						options: `<p class="imed-counters__hint">${
							morning
								? __("بداية اليوم: اكتب الرقم اللي ظاهر على عداد كل مكنة.")
								: now.earlier
								? __("يوم {0} لسه ناقصه قراية آخر اليوم. اكتب أرقام العدادات دلوقتي.", [frappe.datetime.str_to_user(now.date)])
								: __("آخر اليوم: اكتب الرقم اللي ظاهر على عداد كل مكنة.")
						}</p>`,
					},
				];
				now.machines.forEach((m, i) => {
					const before = morning ? m.last : m.morning;
					fields.push({
						fieldname: `m${i}`,
						fieldtype: "Int",
						label: m.machine,
						reqd: 1,
						description: before ? (morning ? __("آخر قراية امبارح: {0}", [qty(before)]) : __("الصبح كان: {0}", [qty(before)])) : __("أول قراية للمكنة دي"),
					});
					fields.push(
						morning
							? { fieldname: `n${i}`, fieldtype: "Data", label: __("العداد زاد عن امبارح، ليه؟"), depends_on: before ? `eval:doc.m${i} > ${before}` : "eval:false" }
							: { fieldname: `n${i}`, fieldtype: "Data", label: __("المكنة عطلت؟ اكتب إيه اللي حصل (لو فيه)") }
					);
				});
				const d = new frappe.ui.Dialog({
					title: morning ? __("عدادات الصبح") : __("عدادات آخر اليوم"),
					fields,
					primary_action_label: __("سجّل"),
					primary_action(v) {
						const readings = {};
						const notes = {};
						now.machines.forEach((m, i) => {
							readings[m.machine] = v[`m${i}`];
							if (v[`n${i}`]) notes[m.machine] = v[`n${i}`];
						});
						frappe.xcall(`${API}.save_counters`, { phase: now.phase, readings: JSON.stringify(readings), notes: JSON.stringify(notes) }).then((r) => {
							d.hide();
							done(morning ? __("عدادات الصبح اتسجلت. آخر اليوم سجّل تاني.") : __("اليوم اتقفل: اتطبع {0} ورقة.", [qty(r.sheets)]));
						});
					},
				});
				d.$wrapper.addClass("imed-counters");
				d.$wrapper.find("input[data-fieldtype='Int']").attr("inputmode", "numeric");
				d.show();
			});
		},
		used() {
			const d = new frappe.ui.Dialog({
				title: __("حاجة خلصت"),
				fields: [
					{ fieldname: "item_code", fieldtype: "Select", label: __("إيه اللي خلص؟"), options: options(), reqd: 1 },
					{ fieldname: "qty", fieldtype: "Float", label: __("كام؟ (بالوحدة اللي جنب الاسم)"), default: 1, reqd: 1 },
				],
				primary_action_label: __("تمام"),
				primary_action(v) {
					frappe.xcall(`${API}.used_up`, v).then(() => {
						d.hide();
						done(__("اتسجل، واتخصم من المخزن."));
					});
				},
			});
			d.show();
		},
		count() {
			const d = new frappe.ui.Dialog({
				title: __("رصيد المخزون"),
				fields: [
					{ fieldtype: "HTML", options: `<p class="text-muted">${__("اكتب العدد اللي عندنا دلوقتي. اللي مش عارفه سيبه فاضي.")}</p>` },
					...(desk.items || []).map((i) => ({ fieldname: i.item_code, fieldtype: "Float", label: `${i.item_name}: ${__("المسجل")} ${qty(i.qty)}` })),
				],
				primary_action_label: __("سجّل"),
				primary_action(v) {
					const quantities = {};
					Object.keys(v).forEach((k) => v[k] !== undefined && v[k] !== null && v[k] !== "" && (quantities[k] = v[k]));
					frappe.xcall(`${API}.count`, { quantities: JSON.stringify(quantities) }).then(() => {
						d.hide();
						done(__("الرصيد اتسجل."));
					});
				},
			});
			d.show();
		},
		ask() {
			const d = new frappe.ui.Dialog({
				title: __("اطلب حاجة"),
				fields: [
					{ fieldname: "item_code", fieldtype: "Select", label: __("محتاجين إيه؟"), options: options(), reqd: 1 },
					{ fieldname: "qty", fieldtype: "Float", label: __("كام؟ (بالوحدة اللي جنب الاسم)"), default: 1, reqd: 1 },
					{ fieldname: "note", fieldtype: "Small Text", label: __("ملاحظة (لو فيه)") },
				],
				primary_action_label: __("ابعت الطلب"),
				primary_action(v) {
					frappe.xcall(`${API}.ask_for`, v).then(() => {
						d.hide();
						done(__("الطلب اتبعت."));
					});
				},
			});
			d.show();
		},
	};

	load();
	wrapper.imed_reload = () => desk && load();
};

// This page is in no sidebar, so opened directly (a reload, a link) Frappe found none to show and the sidebar came
// up empty (the owner, 5 Nov 2026; after signing in it kept the one already shown). Then the Stock sidebar is shown,
// as after signing in; a library's account gets its own pages on top of it (imed_desk_fixes.js).
function imed_library_sidebar() {
	const sidebar = frappe.app && frappe.app.sidebar;
	const known = frappe.boot && frappe.boot.workspace_sidebar_item;
	if (!sidebar || !sidebar.setup || !known || !known.stock) return;
	if (!(sidebar.workspace_sidebar_items || []).length) sidebar.setup("Stock");
}

// Back to the page (after the counters' form, say): what it shows is read again.
frappe.pages["imed-library"].on_page_show = function (wrapper) {
	if (imed_not_a_library()) return;
	if (wrapper.imed_reload) wrapper.imed_reload();
	setTimeout(imed_library_sidebar, 300);
};
