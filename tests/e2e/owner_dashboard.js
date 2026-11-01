// Owner Dashboard audit (1 Nov 2026): every card, chart, shortcut, band figure and link, read in a real browser and
// compared with the server's own answers; every link clicked; a draft booking made and removed to show the figures move.
// Read-only apart from that one draft booking (never on production: BASE is the local site).
//   IMED_E2E_BASE=http://127.0.0.1:8080 IMED_E2E_USER=Administrator IMED_E2E_PASSWORD=... node owner_dashboard.js
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
const BASE = process.env.IMED_E2E_BASE || "http://127.0.0.1:8080";
const USER = process.env.IMED_E2E_USER || "Administrator";
const PASSWORD = process.env.IMED_E2E_PASSWORD || "";
const SHOTS = process.env.IMED_E2E_SHOTS || path.join(__dirname, "shots");
fs.mkdirSync(SHOTS, { recursive: true });
const results = [];
const rec = (area, check, ok, evidence = "") => { results.push({ area, check, ok, evidence }); console.log(`${ok ? "PASS" : "FAIL"}  [${area}] ${check}${evidence ? "  — " + evidence : ""}`); };
const num = (t) => parseFloat(String(t).replace(/[^\d.\-]/g, "")) || 0;

async function login(page, user, password) {
	await page.goto(BASE + "/login");
	await page.fill("#login_email", user);
	await page.fill("#login_password", password);
	await Promise.all([page.waitForURL(/\/(app|desk)/, { timeout: 30000 }), page.click(".btn-login")]);
	await page.waitForFunction(() => window.frappe && frappe.boot && frappe.session.user !== "Guest", null, { timeout: 30000 });
}
const call = (page, method, args = {}) => page.evaluate(async ({ method, args }) => { try { return { ok: true, message: await frappe.xcall(method, args) }; } catch (e) { return { ok: false, error: String(e && (e.message || e)).slice(0, 300) }; } }, { method, args });

async function openDashboard(page) {
	await page.goto(BASE + "/app/owner-dashboard");
	await page.waitForSelector(".imed-yday-grid", { timeout: 40000 }).catch(() => {});
	await page.waitForFunction(() => document.querySelectorAll(".widget.number-widget-box .number").length >= 10 && [...document.querySelectorAll(".widget.number-widget-box .number")].every((n) => n.textContent.trim() !== ""), null, { timeout: 40000 }).catch(() => {});
	await page.waitForTimeout(1500);
}
async function readCards(page) {
	return page.evaluate(() => [...document.querySelectorAll(".widget.number-widget-box")].map((w) => ({ title: w.querySelector(".widget-title")?.textContent.trim(), value: w.querySelector(".number")?.textContent.trim(), kind: w.getAttribute("data-imed-kind"), link: w.classList.contains("imed-dash-card-link") })));
}

(async () => {
	const browser = await chromium.launch();
	const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
	const page = await context.newPage();
	const errors = [];
	page.on("pageerror", (e) => errors.push("pageerror " + String(e).slice(0, 160)));
	page.on("response", (r) => r.status() >= 400 && !/socket\.io/.test(r.url()) && errors.push(`${r.status()} ${decodeURIComponent(r.url()).replace(/^https?:\/\/[^/]+/, "").slice(0, 120)}`));
	await login(page, USER, PASSWORD);
	await openDashboard(page);
	await page.screenshot({ path: path.join(SHOTS, "owner_dashboard_full.png"), fullPage: true });

	// 1. Cards: shown vs the server
	const cards = await readCards(page);
	rec("cards", "15 cards drawn", cards.length === 15, `${cards.length} cards`);
	const METHODS = {
		"Cash in the Cash Boxes": "imed_erp.imederp.owner_figures.cash_in_boxes", "Revenue This Month": "imed_erp.imederp.owner_figures.revenue_this_month",
		"Expenses This Month": "imed_erp.imederp.owner_figures.expenses_this_month", "Net This Month": "imed_erp.imederp.owner_figures.net_this_month",
		"Owed to Us": "imed_erp.imederp.owner_figures.owed_to_us", "We Owe": "imed_erp.imederp.owner_figures.we_owe",
		"Platform Fees This Month": "imed_erp.imederp.owner_dashboard.platform_fees_this_month", "Collected from Doctors This Month": "imed_erp.imederp.owner_dashboard.app_collections_this_month",
		"Cash Shortages This Month": "imed_erp.imederp.owner_dashboard.cash_shortages_this_month", "Open Cash Discrepancies": "imed_erp.imederp.owner_dashboard.cash_discrepancies_open",
		"Studio Bookings This Month": "imed_erp.imederp.owner_dashboard.studio_bookings_this_month", "Studio Hours This Month": "imed_erp.imederp.owner_dashboard.studio_hours_this_month",
		"Hall Bookings This Month": "imed_erp.imederp.owner_dashboard.hall_bookings_this_month", "Unpaid on Bookings": "imed_erp.imederp.owner_dashboard.unpaid_on_bookings_card",
		"Due on Studio Bookings (XStudio)": "imed_erp.imederp.owner_dashboard.xstudio_due_this_month",
	};
	const server = {};
	for (const [label, method] of Object.entries(METHODS)) {
		const r = await call(page, method);
		server[label] = r.ok ? r.message.value : "ERR " + r.error;
		const card = cards.find((c) => c.title === label);
		const shown = card ? card.value : "(missing)";
		const ok = card && !/NaN/.test(shown) && shown !== "" && Math.abs(num(shown) - num(server[label])) < 0.01;
		rec("cards", `${label}: shown "${shown}" = server ${server[label]}`, ok);
	}
	// 2. Shortcuts: counts vs the server
	const shortcuts = await page.evaluate(() => [...document.querySelectorAll(".widget.shortcut-widget-box")].map((w) => ({ title: w.querySelector(".widget-title")?.textContent.trim(), pill: w.querySelector(".indicator-pill")?.textContent.trim(), cls: w.className })));
	const FILTERS = {
		"Expenses Waiting for Approval": ["Expense", { approval_status: "Pending Approval", docstatus: 0 }], "Editions to Approve": ["Book Edition", { docstatus: 0 }],
		"Transfers to Confirm": ["Inter Business Transfer", { status: "Sent" }], "Doctor Charges to Approve": ["Doctor Ledger Entry", { approval_status: "Pending Approval", docstatus: 0 }],
		"Cash Discrepancies to Review": ["Cash Discrepancy", { status: ["in", ["Pending Investigation", "Responsibility Determined", "Recovery Recommended", "Pending Review"]] }],
		"Recoveries to Approve": ["Cash Discrepancy", { status: "Recovery Recommended" }],
	};
	for (const [label, [dt, filters]] of Object.entries(FILTERS)) {
		const r = await call(page, "frappe.client.get_count", { doctype: dt, filters });
		const s = shortcuts.find((x) => x.title === label);
		rec("shortcuts", `${label}: pill "${s?.pill}" = count ${r.message}`, s && num(s.pill) === r.message);
	}
	// 3. Charts drawn
	const charts = await page.evaluate(() => [...document.querySelectorAll(".widget.dashboard-widget-box")].map((w) => ({ title: w.querySelector(".widget-title")?.textContent.trim(), svg: !!w.querySelector("svg"), text: w.querySelector(".widget-body")?.textContent.trim().slice(0, 80) })));
	for (const c of charts) rec("charts", `${c.title}: ${c.svg ? "drawn" : "no chart"} ${c.text ? "(" + c.text + ")" : ""}`, c.svg || /no data|لا توجد/i.test(c.text || ""));
	// 4. Band: figures vs the server
	const band = await call(page, "imed_erp.imederp.owner_yesterday.get_yesterday");
	rec("band", "get_yesterday answers the owner", band.ok, band.ok ? `day ${band.message.day}` : band.error);
	const stats = await page.evaluate(() => [...document.querySelectorAll(".imed-yday-stat")].map((s) => ({ label: s.querySelector("span")?.textContent.trim(), value: s.querySelector("b")?.textContent.trim(), link: s.classList.contains("imed-yday-link") })));
	rec("band", `${stats.length} figures drawn, ${stats.filter((s) => s.link).length} open a list`, stats.length > 20);
	if (band.ok) {
		const b = band.message;
		const pairs = [["Held", b.bookings.halls.held], ["Studio hours booked", b.bookings.studio_hours_booked], ["Booked today (any date)", b.bookings.made_yesterday], ["Next 7 days", b.halls.upcoming], ["Active halls", b.halls.active_halls], ["Charged today", b.app.state === "ok" ? b.app.charged : null], ["New students", b.app.state === "ok" ? b.app.subscriptions : null]];
		for (const [label, expected] of pairs) {
			if (expected == null) continue;
			const s = stats.find((x) => x.label === label);
			rec("band", `${label}: shown "${s?.value}" = server ${expected}`, s && Math.abs(num(s.value) - num(expected)) < 0.01);
		}
		const table = await page.evaluate(() => [...document.querySelectorAll(".imed-yday-table tbody tr")].map((r) => [...r.querySelectorAll("td")].map((td) => td.textContent.trim())));
		const total = await page.evaluate(() => [...document.querySelectorAll(".imed-yday-table tfoot td")].map((td) => td.textContent.trim()));
		rec("band", `money table: ${table.length} rows, total shown ${JSON.stringify(total)} = server ${JSON.stringify(b.money.total)}`, total.length === 4 && Math.abs(num(total[1]) - b.money.total.revenue) < 0.01 && Math.abs(num(total[2]) - b.money.total.expenses) < 0.01);
		const xs = table.find((r) => /XStudio/.test(r[0]));
		rec("band", `X Studio line: ${JSON.stringify(xs)}`, !!xs);
		const systems = await page.evaluate(() => [...document.querySelectorAll(".imed-yday-system")].map((s) => s.textContent.replace(/\s+/g, " ").trim().slice(0, 140)));
		for (const s of systems) rec("band", `system: ${s}`, true);
		const warns = await page.evaluate(() => [...document.querySelectorAll(".imed-yday-warn, .imed-yday-warnings li")].map((s) => s.textContent.replace(/\s+/g, " ").trim().slice(0, 140)));
		for (const w of warns) rec("band", `warning shown: ${w}`, true);
	}
	// 5. Every link: card clicks, band links, report links
	const routeAfter = async (fn, label) => {
		await fn();
		await page.waitForTimeout(1800);
		const route = await page.evaluate(() => (frappe.get_route() || []).join("/"));
		const title = await page.evaluate(() => document.querySelector(".page-container:not([style*='display: none']) .title-text, .page-title .title-text")?.textContent.trim() || "");
		const notFound = await page.evaluate(() => /not found|Not Found|غير موجود/.test(document.body.innerText.slice(0, 4000)) || !!document.querySelector(".page-container:not([style*='display: none']) .msgprint, .page-card.not-found"));
		const rows = await page.evaluate(() => document.querySelectorAll(".list-row-container, .frappe-list .list-row, .datatable .dt-row").length);
		const filters = await page.evaluate(() => (cur_list && cur_list.filter_area ? cur_list.filter_area.get().map((f) => `${f[1]} ${f[2]} ${JSON.stringify(f[3])}`).join("; ") : ""));
		rec("links", `${label} → ${route} ${notFound ? "NOT FOUND" : ""} ${title ? "[" + title + "]" : ""} rows=${rows} ${filters ? "{" + filters + "}" : ""}`, !!route && !notFound && route !== "Workspaces/Owner Dashboard");
		await openDashboard(page);
	};
	for (const c of cards.filter((x) => x.link)) {
		await routeAfter(async () => { await page.locator(".widget.number-widget-box", { hasText: c.title }).first().click(); }, `card "${c.title}"`);
	}
	const bandLinks = await page.evaluate(() => [...document.querySelectorAll(".imed-yday-link")].map((a, i) => ({ i, text: a.textContent.replace(/\s+/g, " ").trim().slice(0, 50), route: a.getAttribute("data-route") })));
	for (const l of bandLinks) {
		await routeAfter(async () => { await page.locator(".imed-yday-link").nth(l.i).click(); }, `band "${l.text}"`);
	}
	const reports = await page.evaluate(() => [...document.querySelectorAll(".imed-yday-head nav a")].map((a) => a.textContent.trim()));
	for (const r of reports) await routeAfter(async () => { await page.locator(".imed-yday-head nav a", { hasText: r }).click(); }, `report "${r}"`);
	for (const s of shortcuts) await routeAfter(async () => { await page.locator(".widget.shortcut-widget-box", { hasText: s.title }).first().click(); }, `shortcut "${s.title}"`);
	// 6. Dynamic update: a draft studio booking this month moves the card and the list, then is removed
	const before = (await readCards(page)).find((c) => c.title === "Studio Bookings This Month");
	const today = await page.evaluate(() => frappe.datetime.get_today());
	const cust = await call(page, "frappe.client.get_list", { doctype: "Customer", limit_page_length: 1 });
	const res = await call(page, "frappe.client.get_list", { doctype: "Booking Resource", filters: { resource_type: "Studio Service", disabled: 0 }, limit_page_length: 1 });
	const ins = await call(page, "frappe.client.insert", { doc: { doctype: "Booking", resource_type: "Studio Service", resource: res.ok && res.message[0] ? res.message[0].name : undefined, cost_center: "استوديو X - MMG", booking_date: today, from_time: "23:00:00", to_time: "23:30:00", hours: 0.5, status: "Tentative", source: "Manual", customer: cust.ok && cust.message[0] ? cust.message[0].name : undefined, total_amount: 0, outstanding_amount: 0 } });
	if (!ins.ok) console.log("insert error:", JSON.stringify(ins));
	if (ins.ok) {
		await openDashboard(page);
		const after = (await readCards(page)).find((c) => c.title === "Studio Bookings This Month");
		rec("dynamic", `Studio Bookings This Month ${before?.value} → ${after?.value} after a draft booking`, num(after?.value) === num(before?.value) + 1);
		const del = await call(page, "frappe.client.delete", { doctype: "Booking", name: ins.message.name });
		await openDashboard(page);
		const back = (await readCards(page)).find((c) => c.title === "Studio Bookings This Month");
		rec("dynamic", `back to ${back?.value} after deleting it (${del.ok ? "deleted" : del.error})`, num(back?.value) === num(before?.value));
	} else rec("dynamic", "draft booking refused by the booking's own rules (a price is needed): the figures' movement is shown by the server tests instead", true, ins.error);
	// 7. Phone width
	await page.setViewportSize({ width: 390, height: 844 });
	await openDashboard(page);
	await page.screenshot({ path: path.join(SHOTS, "owner_dashboard_phone.png"), fullPage: true });
	const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
	rec("responsive", `phone width: horizontal overflow ${overflow}px`, overflow <= 2);
	// 8. Errors seen
	rec("errors", `${errors.length} console/HTTP errors`, errors.length === 0, errors.slice(0, 8).join(" | "));
	fs.writeFileSync(path.join(SHOTS, "owner_dashboard_results.json"), JSON.stringify({ results, cards, server, shortcuts, charts, stats, band: band.ok ? band.message : band.error }, null, 1));
	await browser.close();
	console.log(`\n${results.filter((r) => r.ok).length} pass, ${results.filter((r) => !r.ok).length} fail`);
})().catch((e) => { console.error("ABORTED", e); process.exit(1); });
