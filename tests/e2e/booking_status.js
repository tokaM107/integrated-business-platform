// The booking screens read their statuses' colours from the server (frappe.boot.imed_booking, booking_rules.py;
// review of 2 Nov 2026), and open without a script error: the list, the calendar and a booking's form. Read-only:
// it opens screens and makes no record. On the throwaway site (README.md).
//   IMED_E2E_PASSWORD=... node booking_status.js
const { chromium, BASE, session, record, results, shot } = require("./lib");

(async () => {
	const browser = await chromium.launch();
	const { page } = await session(browser, "owner@imed.local");
	const boot = await page.evaluate(() => frappe.boot.imed_booking || null);
	record("bookings", "the server sends every status's colour", !!boot && Object.keys(boot.colors).length === 6, JSON.stringify(boot && boot.colors));

	for (const [label, route] of [["list", "/app/booking"], ["calendar", "/app/booking/view/calendar"]]) {
		page.errors.length = 0;
		await page.goto(BASE + route);
		await page.waitForTimeout(2500);
		await shot(page, `booking_${label}`);
		record("bookings", `the ${label} opens without a script error`, page.errors.length === 0, page.errors.join(" | "));
	}

	const listed = await page.evaluate(async () => (await frappe.db.get_list("Booking", { fields: ["name", "status"], limit: 1 }))[0] || null);
	if (listed) {
		const indicator = await page.evaluate((status) => frappe.listview_settings["Booking"].get_indicator({ status }), listed.status);
		record("bookings", "the list's indicator uses the server's colour", indicator[1] === boot.colors[listed.status], JSON.stringify(indicator));
		page.errors.length = 0;
		await page.goto(`${BASE}/app/booking/${encodeURIComponent(listed.name)}`);
		await page.waitForTimeout(2500);
		await shot(page, "booking_form");
		record("bookings", "a booking's form opens without a script error", page.errors.length === 0, page.errors.join(" | "));
	} else {
		record("bookings", "a booking's form (no booking on the site)", true, "skipped: nothing to open");
	}
	await browser.close();
	const failed = results.filter((r) => !r.ok).length;
	console.log(`\n${results.length - failed} of ${results.length} passed.`);
	process.exit(failed ? 1 : 0);
})();
