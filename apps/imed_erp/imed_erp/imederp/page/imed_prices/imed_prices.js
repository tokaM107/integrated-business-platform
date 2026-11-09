// الأسعار: the owner's prices, a business at a time (imederp/owner_prices.py; owner, 9 Nov 2026). The libraries: what
// the supplies cost, what a printed sheet costs from them, and each selling price beside its cost and margin; the
// app: the fee per student; the halls and the studio: shown, changed where they are booked. A change is from today:
// everyone sees it, and what was sold or booked before keeps its price.
frappe.pages["imed-prices"].on_page_load = function (wrapper) {
	const API = "imed_erp.imederp.owner_prices";
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("الأسعار"), single_column: true });
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const money = (v) => format_currency(v || 0, "EGP", 2);
	const num = (v, d = 2) => format_number(v || 0, null, d);
	const BUSINESSES = [
		["libraries", __("Libraries"), "/assets/imed_erp/images/logos/doctor-2-be.jpg"],
		["halls", __("Halls"), "/assets/imed_erp/images/logos/imed-academy.jpg"],
		["studio", __("Studio"), "/assets/imed_erp/images/logos/x-studio.jpg"],
		["app", __("BA Plus App"), "/assets/imed_erp/images/logos/ba-plus.jpg"],
	];
	let current = "libraries";
	const $body = $(`<div class="imed-prices">
			<div class="imed-prices__tabs">${BUSINESSES.map(([k, label, logo]) => `<button type="button" data-b="${k}"><img src="${logo}" alt=""><span>${esc(label)}</span></button>`).join("")}</div>
			<div class="imed-prices__body"></div>
		</div>`).appendTo(page.main);

	const note = (text) => `<p class="imed-prices__note">${frappe.utils.icon("info", "sm")}<span>${esc(text)}</span></p>`;
	const input = (key, value, step = "0.01") => `<input type="number" min="0" step="${step}" class="form-control imed-prices__input" data-key="${esc(key)}" value="${esc(value)}">`;
	const save = (key) => `<button type="button" class="btn btn-sm btn-primary imed-prices__save" data-key="${esc(key)}">${esc(__("Save"))}</button>`;

	function libraries(d) {
		const costs = d.costs.map((c) => `<tr><td>${esc(c.label)}</td><td class="is-num">${input(c.key, c.value)}</td><td>${save(c.key)}</td></tr>`).join("");
		const yields = d.yields.map((y) => `<tr><td>${esc(y.label)}</td><td class="is-num">${input(y.key, y.value || "", "1")}</td><td>${save(y.key)}</td></tr>`).join("");
		const sheet = d.sheet
			.map(
				(s) => `<div class="imed-prices__sheet">
						<b>${esc(s.machine)}</b>
						<span class="imed-prices__big">${money(s.total)}</span>
						<small>${esc(__("paper"))} ${num(s.paper, 3)} + ${esc(__("ink"))} ${num(s.ink, 3)} + ${esc(__("waste"))} ${num(s.waste, 3)} + ${esc(__("overheads"))} ${num(s.overheads, 3)}</small>
					</div>`
			)
			.join("");
		const selling = d.selling
			.map((s) => {
				const tone = s.margin == null ? "" : s.margin > 0 ? "is-in" : "is-out";
				return `<tr><td>${esc(s.label)}${s.since ? `<small>${esc(__("since {0}", [frappe.datetime.str_to_user(s.since)]))}</small>` : ""}</td>
					<td class="is-num">${s.cost == null ? "—" : money(s.cost)}</td>
					<td class="is-num">${input(s.key, s.value)}</td>
					<td class="is-num ${tone}">${s.margin == null ? "—" : money(s.margin)}</td>
					<td>${save(s.key)}</td></tr>`;
			})
			.join("");
		return `${note(__("A price changed here is in force from today, for every account; what was sold before keeps its price."))}
			<section class="imed-sec"><header class="imed-sec__head"><h2>${frappe.utils.icon("shopping-cart", "sm")}<span>${esc(__("What we buy at"))}</span></h2></header>
				<table class="imed-prices__table"><tbody>${costs}${yields}</tbody></table></section>
			<section class="imed-sec"><header class="imed-sec__head"><h2>${frappe.utils.icon("printer", "sm")}<span>${esc(__("What a printed sheet costs"))}</span></h2></header>
				<div class="imed-prices__sheets">${sheet}</div></section>
			<section class="imed-sec"><header class="imed-sec__head"><h2>${frappe.utils.icon("tag", "sm")}<span>${esc(__("What we sell at"))}</span></h2></header>
				<table class="imed-prices__table"><thead><tr><th>${esc(__("Service"))}</th><th class="is-num">${esc(__("Cost"))}</th><th class="is-num">${esc(__("Price"))}</th><th class="is-num">${esc(__("Margin"))}</th><th></th></tr></thead><tbody>${selling}</tbody></table></section>`;
	}

	function app(d) {
		const rows = d.tiers
			.map(
				(t, i) => `<tr data-i="${i}"><td>${esc(__("From {0} to {1} students", [t.from, t.to || "∞"]))}</td><td class="is-num">${input(`tier-${i}`, t.value)}</td></tr>`
			)
			.join("");
		return `${note(__("A new fee per student is in force from today; the courses charged before keep theirs."))}
			<section class="imed-sec"><header class="imed-sec__head"><h2>${frappe.utils.icon("smartphone", "sm")}<span>${esc(__("Fee per student"))}</span></h2>${d.since ? `<small>${esc(__("since {0}", [frappe.datetime.str_to_user(d.since)]))}</small>` : ""}</header>
				<table class="imed-prices__table"><tbody>${rows}</tbody></table>
				<div class="imed-prices__foot"><button type="button" class="btn btn-primary imed-prices__fees">${esc(__("Save"))}</button></div></section>`;
	}

	function shown(d, where, cols) {
		if (d.error) return note(d.error);
		const head = cols.map(([, label]) => `<th class="is-num">${esc(label)}</th>`).join("");
		const rows = d.rows.map((r) => `<tr><td>${esc(r.label)}</td>${cols.map(([k]) => `<td class="is-num">${r[k] == null ? "—" : money(r[k])}</td>`).join("")}</tr>`).join("");
		return `${note(where)}<section class="imed-sec"><table class="imed-prices__table"><thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table></section>`;
	}

	const RENDER = {
		libraries,
		app,
		halls: (d) => shown(d, __("The halls' prices are changed on Sparkle, where they are booked."), [["first_hour", __("First hour")], ["two_hours", __("Two hours")], ["extra_hour", __("Each extra hour")]]),
		studio: (d) => shown(d, __("The studio's prices are changed on XStudio, where it is booked."), [["value", __("Per hour")]]),
	};

	function load(business) {
		current = business;
		$body.find(".imed-prices__tabs button").each(function () {
			$(this).toggleClass("is-active", this.dataset.b === business);
		});
		const $out = $body.find(".imed-prices__body").html(`<div class="imed-skel is-wide"><span></span></div>`);
		frappe.xcall(`${API}.get_prices`, { business }).then((d) => $out.html(RENDER[business](d)));
	}

	$body.on("click", ".imed-prices__tabs button", function () {
		load(this.dataset.b);
	});
	$body.on("click", ".imed-prices__save", function () {
		const key = this.dataset.key;
		const value = $body.find(`.imed-prices__input[data-key="${CSS.escape(key)}"]`).val();
		frappe.xcall(`${API}.set_price`, { business: current, key, value }).then((d) => {
			$body.find(".imed-prices__body").html(RENDER[current](d));
			frappe.show_alert({ message: __("Saved, from today."), indicator: "green" });
		});
	});
	$body.on("click", ".imed-prices__fees", function () {
		const tiers = [];
		$body.find("tr[data-i]").each(function () {
			const i = Number(this.dataset.i);
			tiers.push({ i, value: $(this).find("input").val() });
		});
		frappe.xcall(`${API}.get_prices`, { business: "app" }).then((d) => {
			const rows = d.tiers.map((t, i) => ({ from: t.from, to: t.to, value: tiers[i] ? tiers[i].value : t.value }));
			frappe.xcall(`${API}.set_fees`, { tiers: JSON.stringify(rows) }).then((n) => {
				$body.find(".imed-prices__body").html(app(n));
				frappe.show_alert({ message: __("Saved, from today."), indicator: "green" });
			});
		});
	});
	load(current);
};
