// The demo site's cash screens with their sample records (setup/seed_cash_demo.py): each opens with no script error
// or failed request and shows what the seed made. Read-only, except the owner's approval attempt, which the server
// refuses (the recovery policy is not approved). Run with IMED_E2E_SITE=demo.
setTimeout(() => { console.log("TIMEOUT"); process.exit(3); }, 300000);
const { chromium, BASE, session, record, shot, call } = require("./lib");

async function form(page, route, doctype) {
	await page.goto(BASE + route);
	await page.waitForFunction((dt) => window.cur_frm && cur_frm.doctype === dt && cur_frm.doc && cur_frm.doc.name, doctype, { timeout: 30000 });
	await page.waitForTimeout(1500);
	return page.evaluate(() => ({
		intro: ((document.querySelector(".form-message") || {}).innerText || "").trim(),
		buttons: Object.keys(cur_frm.custom_buttons || {}),
		dir: document.documentElement.dir,
	}));
}

async function list(page, route) {
	await page.goto(BASE + route);
	await page.waitForSelector(".list-row-container, .no-result", { timeout: 30000 });
	await page.waitForTimeout(1200);
	// One checkbox per record (the header's is .list-check-all).
	return page.locator(".list-row-checkbox").count();
}

(async () => {
	const browser = await chromium.launch();
	const mark = (page, where) => page.errors.push(`-- at ${where}`);
	const owner = (await session(browser, "owner@imed.local")).page;
	const raghad = (await session(browser, "raghad@imed.local")).page;

	// The owner's page: the cash cards.
	await owner.goto(BASE + "/desk/owner-dashboard");
	await owner.waitForTimeout(6000);
	const cards = await owner.evaluate(() => document.body.innerText);
	record("demo", "Owner's page shows the cash cards", /فروقات خزينة مفتوحة/.test(cards) && /عجز الخزاين الشهر ده/.test(cards) && !/NaN/.test(cards), "");
	console.log(await shot(owner, "demo-owner-dashboard"));
	mark(owner, "demo-owner-dashboard");

	const closes = await list(owner, "/desk/treasury-close");
	record("demo", "Cash box closes listed for the owner", closes >= 9, `${closes} rows`);
	console.log(await shot(owner, "demo-closes"));
	mark(owner, "demo-closes");

	const discrepancies = await list(owner, "/desk/cash-discrepancy");
	record("demo", "Cash discrepancies listed, one in each state", discrepancies === 4, `${discrepancies} rows`);
	console.log(await shot(owner, "demo-discrepancies"));
	mark(owner, "demo-discrepancies");

	// The recommended recovery: the owner sees Approve, and the server refuses it while the policy is off.
	const recommended = ((await call(owner, "frappe.client.get_list", { doctype: "Cash Discrepancy", filters: { status: "Recovery Recommended" }, fields: ["name"] })).message || [])[0];
	const view = await form(owner, "/desk/cash-discrepancy/" + recommended.name, "Cash Discrepancy");
	const approve = await call(owner, "imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy.approve_recovery", { name: recommended.name });
	const status = (await call(owner, "frappe.client.get_value", { doctype: "Cash Discrepancy", filters: recommended.name, fieldname: "status" })).message.status;
	record("demo", "Recommended recovery waits for the owner; approving is refused while the policy is off", approve.ok === false && status === "Recovery Recommended" && view.buttons.length > 0, JSON.stringify({ ...view, status }));
	console.log(await shot(owner, "demo-recommended-recovery"));
	mark(owner, "demo-recommended-recovery");

	const week = ((await call(owner, "frappe.client.get_list", { doctype: "Weekly Cash Reconciliation", fields: ["name"] })).message || [])[0];
	const weekView = await form(owner, "/desk/weekly-cash-reconciliation/" + week.name, "Weekly Cash Reconciliation");
	const weekDoc = await owner.evaluate(() => ({ end: cur_frm.doc.week_end, rows: cur_frm.doc.items.length, shortage: cur_frm.doc.total_shortage, open: cur_frm.doc.unresolved }));
	record("demo", "The week Saturday to Thursday with its closes and open items", weekDoc.end === "2026-10-22" && weekDoc.rows === 9 && weekDoc.open === 3, JSON.stringify({ ...weekDoc, intro: weekView.intro }));
	console.log(await shot(owner, "demo-weekly"));
	mark(owner, "demo-weekly");

	await owner.goto(BASE + "/desk/query-report/Cash Discrepancies?view=Discrepancies&from_date=2026-10-01&to_date=2026-10-21");
	await owner.waitForTimeout(5000);
	const reportRows = await owner.locator(".dt-row").count();
	record("demo", "Cash Discrepancies report shows the sample rows", reportRows >= 4, `${reportRows} rows`);
	console.log(await shot(owner, "demo-report"));
	mark(owner, "demo-report");

	// Raghad: her branch only, in Arabic, no decisions.
	const hers = await list(raghad, "/desk/treasury-close");
	record("demo", "Raghad sees Mawasah's closes only", hers === 4, `${hers} rows`);
	const mawasahShort = ((await call(raghad, "frappe.client.get_list", { doctype: "Cash Discrepancy", fields: ["name", "status"] })).message || []);
	const herView = await form(raghad, "/desk/cash-discrepancy/" + mawasahShort[0].name, "Cash Discrepancy");
	record("demo", "Raghad reads her branch's discrepancies, decides nothing", mawasahShort.length === 2 && herView.buttons.length === 0 && herView.dir === "rtl", JSON.stringify({ count: mawasahShort.length, ...herView }));
	console.log(await shot(raghad, "demo-branch-discrepancy"));

	console.log("errors", owner.errors, raghad.errors);
	await browser.close();
	process.exit(0);
})();
