// Browser test helpers for the throwaway restore-test site, reached through the local forwarder (127.0.0.1:8090);
// static assets come from the development nginx (127.0.0.1:8080), the same files for every site.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = "http://127.0.0.1:8090";
const ASSETS = "http://127.0.0.1:8080";
const SITE = process.env.IMED_E2E_SITE || "restore-test";
// The test users' password on the throwaway site (set with bench set-password there, never on a real site).
const PASSWORD = process.env.IMED_E2E_PASSWORD || "";
if (!PASSWORD) throw new Error("Set IMED_E2E_PASSWORD: the test users' password on the throwaway site.");
const SHOTS = process.env.IMED_E2E_SHOTS || path.join(__dirname, "shots");
fs.mkdirSync(SHOTS, { recursive: true });

const results = [];
function record(area, check, ok, evidence) {
	results.push({ area, check, ok, evidence });
	console.log(`${ok ? "PASS" : "FAIL"}  [${area}] ${check}${evidence ? "  — " + evidence : ""}`);
}

async function session(browser, user, { viewport = { width: 1366, height: 860 } } = {}) {
	const context = await browser.newContext({ viewport, extraHTTPHeaders: { "X-Frappe-Site-Name": SITE } });
	await context.route("**/assets/**", async (route) => {
		const url = new URL(route.request().url());
		for (let attempt = 1; attempt <= 3; attempt++) {
			try {
				const response = await route.fetch({ url: ASSETS + url.pathname + url.search, headers: {} });
				return await route.fulfill({ response });
			} catch (e) {
				if (attempt === 3) return route.abort().catch(() => {});
				await new Promise((r) => setTimeout(r, 300));
			}
		}
	});
	await context.route("**/socket.io/**", (route) => route.abort());
	const page = await context.newPage();
	page.errors = [];
	// Frappe's report page throws "Filter missing" (uncaught) while it shows "set the filters" for a report whose
	// required filters are empty: its own behaviour, nothing the user sees.
	page.on("pageerror", (e) => !/Filter missing/.test(String(e)) && page.errors.push(String(e).slice(0, 200)));
	page.on("console", (m) => m.type() === "error" && !/socket\.io|ERR_FAILED|net::|Failed to load resource|Filter missing/.test(m.text()) && page.errors.push(m.text().slice(0, 200)));
	page.on("response", (r) => r.status() >= 400 && !/socket\.io/.test(r.url()) && page.errors.push(`${r.status()} ${r.request().method()} ${decodeURIComponent(r.url()).replace(/^https?:\/\/[^/]+/, "").slice(0, 140)}`));
	if (user) await login(page, user);
	return { context, page };
}

async function login(page, user) {
	await page.goto(BASE + "/login");
	await page.fill("#login_email", user);
	await page.fill("#login_password", PASSWORD);
	await Promise.all([page.waitForURL(/\/(app|desk)/, { timeout: 30000 }), page.click(".btn-login")]);
	await page.waitForFunction(() => window.frappe && frappe.boot && frappe.session && frappe.session.user !== "Guest", null, { timeout: 30000 });
}

async function call(page, method, args = {}) {
	// A server call as the logged-in user, through the page (its session and CSRF token).
	return page.evaluate(
		async ({ method, args }) => {
			try {
				const r = await frappe.call({ method, args, freeze: false, async: true, error_handlers: {}, silent: true });
				return { ok: true, message: r.message };
			} catch (e) {
				return { ok: false, status: e && e.status, exc: (e && e.exc_type) || String(e).slice(0, 120) };
			}
		},
		{ method, args }
	);
}

async function shot(page, name) {
	const file = path.join(SHOTS, `${name}.png`);
	await page.screenshot({ path: file, fullPage: false });
	return file;
}

async function logout(page) {
	// Logging out may navigate the page away while the call is still running.
	await page.evaluate(() => frappe.call({ method: "logout", async: true }).catch(() => {})).catch(() => {});
	await page.waitForTimeout(1000);
	const r = await page.request.get(BASE + "/api/method/frappe.auth.get_logged_user", { headers: { "X-Frappe-Site-Name": SITE } });
	return r.status();
}

module.exports = { logout, chromium, BASE, session, login, call, shot, record, results };
