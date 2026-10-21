setTimeout(() => { console.log("TIMEOUT"); process.exit(3); }, 540000);
const { chromium, BASE, session, record, results } = require("./lib");
const fs = require("fs");
const SCREENS = {
	"sara@imed.local": ["Sales Invoice", "Expense", "Inter Business Transfer", "Stock Count", "Damaged Stock Entry", "Daily Counter Reading", "Material Request", "Customer"],
	"raghad@imed.local": ["Book Edition", "Damaged Stock Sale", "Stock Entry", "Material Request", "Printer Reading"],
	"gilan@imed.local": ["Booking", "Expense"],
	"menna@imed.local": ["App Subscription", "App Course"],
	"accountant@imed.local": ["Doctor Ledger Entry", "Doctor Agreement", "Recurring Expense", "Allocation Rule", "Platform Fee Schedule", "Journal Entry"],
};
(async () => {
	const browser = await chromium.launch();
	const { page: probe } = await session(browser, "owner@imed.local");
	const ar = await probe.evaluate(() => __("Dispose as Scrap"));
	record("ui", "the scrap button is in Arabic", ar !== "Dispose as Scrap", ar);
	for (const [user, doctypes] of Object.entries(SCREENS)) {
		const { context, page } = await session(browser, user);
		for (const dt of doctypes) {
			const slug = dt.toLowerCase().replace(/ /g, "-");
			for (const [kind, route] of [["list", `/desk/${slug}`], ["new form", `/desk/${slug}/new`]]) {
				page.errors.length = 0;
				await page.goto(BASE + route);
				await page.waitForTimeout(2500);
				const state = await page.evaluate(() => {
					const text = document.body.innerText;
					const english = [...document.querySelectorAll(".form-section label, .control-label, .list-row-head span, .page-title .title-text")]
						.map((e) => e.innerText.trim())
						.filter((t) => t && /^[A-Za-z][A-Za-z /&'()-]{3,}$/.test(t));
					return { denied: /Not Permitted|غير مسموح|لا يُسمح|ليس لديك صلاحية/.test(text), english: [...new Set(english)].slice(0, 6) };
				});
				const ok = !state.denied && page.errors.length === 0;
				record("screens", `${user.split("@")[0]}: ${dt} ${kind}`, ok, `${state.denied ? "DENIED " : ""}${page.errors.join(" | ")}${state.english.length ? " untranslated: " + state.english.join(", ") : ""}`);
			}
		}
		await context.close();
	}
	await browser.close();
	fs.writeFileSync(__dirname + "/screens-results.json", JSON.stringify(results, null, 1));
	console.log(`\n${results.filter((r) => r.ok).length} of ${results.length} passed`);
})();
