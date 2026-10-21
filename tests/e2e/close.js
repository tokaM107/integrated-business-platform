// The daily cash close and its review, through the forms (owner, 21 Oct 2026): Sara sees her close and cannot reopen
// it; the accountant reopens it with a reason and closes the day again short; the shortage opens a discrepancy that
// Sara can read but not decide; the accountant writes it off; the week's review shows it. Needs a submitted close of
// Azarita's box today (the first run of the previous version of this file made one) on the copy site.
setTimeout(() => { console.log("TIMEOUT"); process.exit(3); }, 300000);
const { chromium, BASE, session, record, shot, call } = require("./lib");
const TODAY = new Date().toISOString().slice(0, 10);
const WEEK_START = new Date(Date.now() - 6 * 864e5).toISOString().slice(0, 10);
const AZARITA_BOX = "خزينة مكتبة الأزاريطة - MMG";

async function open(page, route, doctype) {
	await page.goto(BASE + route);
	await page.waitForFunction((dt) => window.cur_frm && cur_frm.doctype === dt && !cur_frm.is_new() !== undefined, doctype, { timeout: 30000 });
	await page.waitForTimeout(1200);
}

function buttons(page) {
	return page.evaluate(() => Object.keys(cur_frm.custom_buttons || {}));
}

async function confirmDialog(page) {
	await page.waitForTimeout(800);
	await page.locator(".modal.show .btn-primary:visible").first().click();
}

(async () => {
	const browser = await chromium.launch();
	const sara = (await session(browser, "sara@imed.local")).page;
	const accountant = (await session(browser, "accountant@imed.local")).page;
	for (const page of [sara, accountant]) {
		process.on("unhandledRejection", async (e) => { console.log("FAILED AT", String(e).slice(0, 300)); console.log(await shot(page, "wf-close-failure")); process.exit(1); });
	}

	const closes = await call(accountant, "frappe.client.get_list", {
		doctype: "Treasury Close", filters: { treasury: AZARITA_BOX, close_date: TODAY, docstatus: 1 }, fields: ["name"],
	});
	const list = closes.message || [];
	if (!list.length) { console.log("No submitted close of Azarita today on this site."); process.exit(2); }
	const original = list[0].name;

	// Sara: her close, in Arabic, no Reopen.
	await open(sara, "/desk/treasury-close/" + encodeURIComponent(original), "Treasury Close");
	const saraView = await sara.evaluate(() => ({
		dir: document.documentElement.dir, expected: (cur_frm.fields_dict.expected.label_area || {}).innerText || "",
	}));
	const saraButtons = await buttons(sara);
	record("workflow", "Sara sees her close in Arabic, without Reopen", saraView.dir === "rtl" && !saraButtons.some((b) => /Reopen|افتح/.test(b)), JSON.stringify({ ...saraView, saraButtons }));
	const refused = await call(sara, "imed_erp.imederp.doctype.treasury_close.treasury_close.reopen", { name: original, reason: "x" });
	record("security", "Sara's reopen call is refused by the server", refused.ok === false && refused.status === 403, JSON.stringify(refused).slice(0, 160));

	// The accountant reopens it with a reason; the amended draft opens.
	await open(accountant, "/desk/treasury-close/" + encodeURIComponent(original), "Treasury Close");
	await accountant.evaluate(() => cur_frm.custom_buttons[Object.keys(cur_frm.custom_buttons).find((b) => /Reopen|افتح/.test(b))].click());
	await accountant.waitForSelector(".modal.show textarea", { timeout: 15000 });
	await accountant.fill(".modal.show textarea", "Recounted with the branch: the drawer was counted before the last sale");
	await confirmDialog(accountant);
	await accountant.waitForFunction((n) => window.cur_frm && cur_frm.doc.amended_from === n, original, { timeout: 30000 });
	const draft = await accountant.evaluate(() => ({ name: cur_frm.doc.name, opening: cur_frm.doc.opening, expected: cur_frm.doc.expected, reason: cur_frm.doc.reopen_reason }));
	const kept = (await call(accountant, "frappe.client.get", { doctype: "Treasury Close", name: original })).message || {};
	record("workflow", "Reopened: the original kept, cancelled, with the reason; a draft amends it", kept.docstatus === 2 && /Recounted/.test(kept.reopen_reason || "") && kept.reopened_by === "accountant@imed.local" && !draft.reason, JSON.stringify({ draft, kept: { docstatus: kept.docstatus, by: kept.reopened_by } }));

	// Closed again, 15 short.
	await accountant.evaluate(() => cur_frm.set_value("counted", cur_frm.doc.expected - 15));
	await accountant.evaluate(() => { cur_frm.save(); });
	await accountant.waitForFunction(() => !cur_frm.is_dirty() && !cur_frm.doc.__islocal, null, { timeout: 30000 });
	await accountant.evaluate(() => { cur_frm.savesubmit(); });
	await confirmDialog(accountant);
	await accountant.waitForFunction(() => cur_frm.doc.docstatus === 1, null, { timeout: 30000 });
	await accountant.waitForTimeout(1500);
	const closed = await accountant.evaluate(() => ({ difference: cur_frm.doc.difference, discrepancy: cur_frm.doc.cash_discrepancy, intro: (document.querySelector(".form-message") || {}).innerText || "" }));
	record("workflow", "Closed 15 short: a discrepancy is opened", closed.difference === -15 && !!closed.discrepancy, JSON.stringify(closed));
	console.log(await shot(accountant, "wf-close-short"));

	// Sara reads the discrepancy, decides nothing.
	await open(sara, "/desk/cash-discrepancy/" + encodeURIComponent(closed.discrepancy), "Cash Discrepancy");
	const saraDecides = await buttons(sara);
	const saraWriteOff = await call(sara, "imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy.write_off", { name: closed.discrepancy, reason: "x" });
	record("security", "Sara reads the shortage but cannot settle it", saraDecides.length === 0 && saraWriteOff.ok === false && saraWriteOff.status === 403, JSON.stringify({ saraDecides, status: saraWriteOff.status }));
	console.log(await shot(sara, "wf-discrepancy-branch"));

	// The accountant writes it off: the company bears it.
	await open(accountant, "/desk/cash-discrepancy/" + encodeURIComponent(closed.discrepancy), "Cash Discrepancy");
	const offered = await buttons(accountant);
	await accountant.evaluate(() => cur_frm.custom_buttons[Object.keys(cur_frm.custom_buttons).find((b) => /Write Off|اشطب/.test(b))].click());
	await accountant.waitForSelector(".modal.show textarea", { timeout: 15000 });
	await accountant.fill(".modal.show textarea", "Not found after the recount; the company bears it");
	await confirmDialog(accountant);
	await accountant.waitForFunction(() => cur_frm.doc.status === "Written Off", null, { timeout: 30000 });
	record("workflow", "The accountant writes the shortage off", true, JSON.stringify({ offered }));
	console.log(await shot(accountant, "wf-discrepancy-written-off"));

	// The week's review: one per week and business, so a draft from an earlier run is opened and saved again.
	const earlier = ((await call(accountant, "frappe.client.get_list", {
		doctype: "Weekly Cash Reconciliation", filters: { week_start: WEEK_START, business: "مكتبة الأزاريطة - MMG", docstatus: 0 }, fields: ["name"],
	})).message || [])[0];
	await accountant.goto(BASE + "/desk/weekly-cash-reconciliation/" + (earlier ? encodeURIComponent(earlier.name) : "new"));
	await accountant.waitForFunction(() => window.cur_frm && cur_frm.doctype === "Weekly Cash Reconciliation", null, { timeout: 30000 });
	await accountant.waitForTimeout(800);
	if (earlier) await accountant.evaluate(() => cur_frm.dirty());
	else await accountant.evaluate(([d, b]) => { cur_frm.set_value("week_start", d); cur_frm.set_value("business", b); }, [WEEK_START, "مكتبة الأزاريطة - MMG"]);
	await accountant.waitForTimeout(800);
	await accountant.evaluate(() => { cur_frm.save(); });
	await accountant.waitForFunction(() => !cur_frm.doc.__islocal && !cur_frm.is_dirty(), null, { timeout: 30000 });
	await accountant.waitForTimeout(1200);
	const week = await accountant.evaluate(() => ({ items: cur_frm.doc.items.map((r) => [r.treasury_close, r.difference, r.discrepancy_status]), shortage: cur_frm.doc.total_shortage, unresolved: cur_frm.doc.unresolved, missing: cur_frm.doc.missing_days }));
	record("workflow", "The week's review lists the corrected close and the shortage", week.items.some((r) => r[0] === draft.name && r[1] === -15) && !week.items.some((r) => r[0] === original), JSON.stringify(week).slice(0, 400));
	console.log(await shot(accountant, "wf-weekly-review"));
	console.log("errors", sara.errors, accountant.errors);
	await browser.close();
	process.exit(0);
})();
