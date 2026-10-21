setTimeout(() => { console.log("TIMEOUT"); process.exit(3); }, 240000);
const { chromium, BASE, session, record, shot } = require("./lib");
const TODAY = new Date().toISOString().slice(0, 10);
(async () => {
	const browser = await chromium.launch();
	const { page } = await session(browser, "sara@imed.local");
	process.on("unhandledRejection", async (e) => { console.log("FAILED AT", String(e).slice(0, 200)); console.log(await shot(page, "wf-close-failure"), await page.evaluate(() => [location.pathname, document.body.innerText.slice(0, 500)])); process.exit(1); });
	await page.goto(BASE + "/desk/treasury-close/new");
	await page.waitForFunction(() => window.cur_frm && cur_frm.doctype === "Treasury Close", null, { timeout: 30000 });
	for (const [k, v] of Object.entries({ treasury: "خزينة مكتبة الأزاريطة - MMG", business: "مكتبة الأزاريطة - MMG", close_date: TODAY })) {
		await page.evaluate(([k, v]) => cur_frm.set_value(k, v), [k, v]);
		await page.waitForTimeout(300);
	}
	await page.evaluate(() => cur_frm.set_value("counted", 10));
	await page.evaluate(() => { cur_frm.save(); });
	await page.waitForFunction(() => window.cur_frm && !cur_frm.doc.__islocal && !cur_frm.is_dirty(), null, { timeout: 30000 });
	const saved = await page.evaluate(() => ({ name: cur_frm.doc.name, expected: cur_frm.doc.expected, counted: cur_frm.doc.counted, difference: cur_frm.doc.difference, by: cur_frm.doc.counted_by }));
	await page.evaluate(() => { cur_frm.savesubmit(); });
	await page.waitForTimeout(1200);
	await page.locator(".modal.show .btn-primary:visible").first().click();
	await page.waitForFunction(() => cur_frm.doc.docstatus === 1, null, { timeout: 30000 });
	await page.waitForTimeout(1500);
	const intro = await page.evaluate(() => (document.querySelector(".form-message") || {}).innerText || "");
	record("workflow", "Sara closes her cash box: expected, counted, difference", saved.by === "sara@imed.local" && saved.difference === saved.counted - saved.expected, JSON.stringify(saved) + " | " + intro.trim());
	console.log(await shot(page, "wf-treasury-close"), page.errors);
	await browser.close();
	process.exit(0);
})();
