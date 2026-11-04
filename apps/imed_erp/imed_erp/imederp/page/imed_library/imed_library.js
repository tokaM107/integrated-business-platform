// مكتبتي: a library's own screen (owner, 4 Nov 2026: one account a library, as simple as can be). Four big buttons
// (today's counters, something finished, what we hold, ask for more), what the store holds, and the last requests.
// Every action is checked on the server (imederp/library_desk.py); this page only asks and shows.
frappe.pages["imed-library"].on_page_load = function (wrapper) {
	const API = "imed_erp.imederp.library_desk";
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("مكتبتي"), single_column: true });
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const qty = (v) => (Number(v) || 0).toLocaleString("ar-EG");
	const $body = $(`<div class="imed-library"></div>`).appendTo(page.main);
	let desk = null;

	const STYLE = `
		<style>
			.imed-library { max-width: 760px; margin: 0 auto; padding: 8px 4px 40px; direction: rtl; }
			.imed-library__head { font-size: 22px; font-weight: 700; margin: 6px 0 2px; }
			.imed-library__date { color: var(--text-muted); margin-bottom: 18px; }
			.imed-library__tiles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
			.imed-library__tile { border: 1px solid var(--border-color); border-radius: 16px; padding: 22px 16px; text-align: center;
				background: var(--card-bg); cursor: pointer; font-size: 19px; font-weight: 600; user-select: none; }
			.imed-library__tile:hover { border-color: var(--primary); }
			.imed-library__tile .emoji { display: block; font-size: 38px; margin-bottom: 8px; }
			.imed-library__tile small { display: block; font-weight: 400; font-size: 13px; color: var(--text-muted); margin-top: 6px; }
			.imed-library__tile.is-done small { color: var(--green-600, #2e7d32); }
			.imed-library h4 { margin: 26px 0 10px; font-size: 16px; }
			.imed-library__row { display: flex; justify-content: space-between; padding: 10px 4px; border-bottom: 1px solid var(--border-color); }
			@media (max-width: 480px) { .imed-library__tile { font-size: 17px; padding: 18px 10px; } }
		</style>`;

	function render() {
		const counted = desk.counter_today;
		const items = desk.items || [];
		const requests = desk.requests || [];
		$body.html(`${STYLE}
			<div class="imed-library__head">${esc(desk.library_name || desk.library)}</div>
			<div class="imed-library__date">${esc(frappe.datetime.str_to_user(frappe.datetime.get_today()))}</div>
			<div class="imed-library__tiles">
				<div class="imed-library__tile ${counted && counted.docstatus === 1 ? "is-done" : ""}" data-action="counters">
					<span class="emoji">📟</span>${__("عدادات النهارده")}
					<small>${counted ? (counted.docstatus === 1 ? __("اتسجلت ✓") : __("سجّل آخر اليوم")) : __("سجّل الصبح")}</small>
				</div>
				<div class="imed-library__tile" data-action="used"><span class="emoji">📦</span>${__("حاجة خلصت")}<small>${__("إزازة حبر، كرتونة ورق…")}</small></div>
				<div class="imed-library__tile" data-action="count"><span class="emoji">🔢</span>${__("رصيد المخزون")}<small>${__("اكتب اللي عندنا دلوقتي")}</small></div>
				<div class="imed-library__tile" data-action="ask"><span class="emoji">📝</span>${__("اطلب حاجة")}<small>${__("حبر، ورق…")}</small></div>
			</div>
			<h4>${__("اللي عندنا في المخزن")}</h4>
			${items.map((i) => `<div class="imed-library__row"><span>${esc(i.item_name)}</span><b>${qty(i.qty)}</b></div>`).join("") || `<div class="text-muted">${__("مفيش أصناف لسه.")}</div>`}
			<h4>${__("طلباتي")}</h4>
			${requests.map((r) => `<div class="imed-library__row"><span>${esc(frappe.datetime.str_to_user(r.transaction_date))}</span><span>${esc(__(r.custom_approval_status || r.status))}</span></div>`).join("") || `<div class="text-muted">${__("مفيش طلبات.")}</div>`}
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

// Back to the page (after the counters' form, say): what it shows is read again.
frappe.pages["imed-library"].on_page_show = function (wrapper) {
	if (wrapper.imed_reload) wrapper.imed_reload();
};
