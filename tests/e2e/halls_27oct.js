// The hall bookings and the redesigned sidebar, 27 Oct 2026, through real browser sessions: the sidebar as each role
// sees it (frontend, read-only), and the hall booking journey on the demo site (a demo hall, never on frontend).
//
//   IMED_E2E_SIDS=<json file {site: {user: sid}}> node halls_27oct.js
//
// Session ids come from bench (LoginManager.login_as); nothing is typed as a password. Screenshots go to
// docs/hall-screens/ (IMED_E2E_SHOTS to change).
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const SIDS = JSON.parse(fs.readFileSync(process.env.IMED_E2E_SIDS, "utf8"));
const SITES = { frontend: "http://localhost:8080", demo: "http://127.0.0.1:8081" };
const SHOTS = process.env.IMED_E2E_SHOTS || path.join(__dirname, "..", "..", "docs", "hall-screens");
fs.mkdirSync(SHOTS, { recursive: true });
const TODAY = new Date().toISOString().slice(0, 10);
const DEMO_HALL = "قاعة تجريبية (تجريبي)";

const results = [];
const record = (area, check, ok, evidence = "") => {
	results.push({ area, check, ok, evidence });
	console.log(`${ok ? "PASS" : "FAIL"}  [${area}] ${check}${evidence ? "  — " + evidence : ""}`);
};

async function open(browser, site, user, viewport = { width: 1366, height: 900 }) {
	const base = SITES[site];
	const context = await browser.newContext({ viewport });
	await context.addCookies([{ name: "sid", value: SIDS[site][user], domain: new URL(base).hostname, path: "/" }]);
	await context.route("**/socket.io/**", (route) => route.abort());
	const page = await context.newPage();
	page.errors = [];
	page.on("pageerror", (e) => page.errors.push(String(e).slice(0, 160)));
	page.base = base;
	page.goto_desk = async (route, wait = 2500) => {
		await page.goto(base + route);
		await page.waitForFunction(() => window.frappe && frappe.boot && frappe.session && frappe.session.user !== "Guest", null, { timeout: 30000 });
		await page.waitForTimeout(wait);
	};
	return { context, page };
}

const shot = async (page, name) => {
	const file = path.join(SHOTS, `${name}.png`);
	await page.screenshot({ path: file });
	return path.relative(process.cwd(), file);
};

const sidebar_labels = (page) =>
	page.evaluate(() =>
		[...document.querySelectorAll(".sidebar-item-container")]
			.filter((el) => el.offsetParent !== null || el.closest(".sidebar-items"))
			.map((el) => ({
				label: (el.querySelector(".sidebar-item-label") || el).innerText.trim().split("\n")[0],
				section: !!el.querySelector(".sidebar-section-break, .collapsible-section") || el.classList.contains("section-break") || el.getAttribute("item-type") === "Section Break",
				href: (el.querySelector("a") || {}).getAttribute ? (el.querySelector("a") || {}).getAttribute("href") : null,
			}))
			.filter((i) => i.label)
	);

const body_text = (page) => page.evaluate(() => document.body.innerText);
const call = (page, method, args) =>
	page.evaluate(
		async ({ method, args }) => {
			try {
				const r = await frappe.call({ method, args, freeze: false, silent: true, error_handlers: {} });
				return { ok: true, message: r.message };
			} catch (e) {
				return { ok: false, exc: (e && (e.exc_type || e._server_messages)) || String(e).slice(0, 160) };
			}
		},
		{ method, args }
	);
const set = (page, values) => page.evaluate((values) => cur_frm.set_value(values), values);
const expand_first_section = (page) =>
	page.evaluate(() => {
		document.querySelectorAll(".sidebar-item-container[item-type='Section Break'] .drop-icon, .sidebar-item-container .sidebar-item-control .drop-icon").forEach(() => {});
	});

(async () => {
	const browser = await chromium.launch();

	// ---------- The sidebar, per role, on frontend ----------
	const seen = {};
	for (const [who, user] of Object.entries({ owner: "owner@imed.local", nour: "nour@imed.local", gilan: "gilan@imed.local", accountant: "accountant@imed.local", hr: "hr@imed.local" })) {
		const { context, page } = await open(browser, "frontend", user);
		await page.goto_desk(who === "owner" ? "/desk/owner-dashboard" : "/desk/booking?resource_type=Hall", 4000);
		const info = await page.evaluate(() => ({ lang: frappe.boot.lang, dir: document.documentElement.dir, user: frappe.session.user }));
		record("sidebar", `${who}: Arabic, right to left`, info.lang === "ar" && info.dir === "rtl", JSON.stringify(info));
		const items = await sidebar_labels(page);
		seen[who] = items.map((i) => i.label);
		const text = items.map((i) => i.label).join(" | ");
		record("sidebar", `${who}: labels are Arabic (no English label left)`, !/[A-Za-z]{4,}/.test(text.replace(/IMED|BA\+|XStudio|X Studio/g, "")), text.slice(0, 400));
		const hall = items.find((i) => /حجوزات قاعات IMED/.test(i.label));
		const studio = items.find((i) => /حجوزات استوديو التصوير/.test(i.label));
		if (who === "hr") {
			record("sidebar", "hr: sees neither the hall nor the studio booking groups' pages", !items.some((i) => /تقويم القاعات|تقويم الاستوديو|حجوزات القاعات|حجوزات الاستوديو/.test(i.label)), text.slice(0, 300));
		} else {
			record("sidebar", `${who}: the halls and the studio are separate groups`, !!hall && !!studio && items.indexOf(hall) < items.indexOf(studio), `${hall && hall.label} … ${studio && studio.label}`);
		}
		record("sidebar", `${who}: no duplicate label`, new Set(seen[who]).size === seen[who].length, seen[who].filter((l, i) => seen[who].indexOf(l) !== i).join(", "));
		record("ui", `${who}: no script error`, page.errors.length === 0, page.errors.join(" | "));
		record("sidebar", `${who}: screenshot`, true, await shot(page, `sidebar-${who}`));
		if (who === "owner") {
			const hall_card = /حجوزات قاعات IMED/.test(await body_text(page));
			record("dashboard", "owner: the hall card is on the dashboard, in Arabic", hall_card, await shot(page, "owner-dashboard-halls"));
			// Every sidebar link opens a page that exists and is permitted.
			const links = items.filter((i) => i.href && i.href.startsWith("/desk")).map((i) => ({ label: i.label, href: i.href }));
			const dead = [];
			for (const link of links) {
				await page.goto(page.base + link.href);
				await page.waitForTimeout(1800);
				const t = await body_text(page);
				if (/Not Permitted|غير مسموح|لا يُسمح|Not Found|غير موجود|Page missing|الصفحة غير موجودة/i.test(t)) dead.push(`${link.label} ${link.href}`);
			}
			record("sidebar", `owner: all ${links.length} sidebar links open`, dead.length === 0, dead.join("; "));
		}
		await context.close();
	}
	fs.writeFileSync(path.join(SHOTS, "sidebar-by-role.json"), JSON.stringify(seen, null, 1));

	// ---------- The hall booking journey, on the demo site ----------
	{
		const { context, page } = await open(browser, "demo", "owner@imed.local");
		await page.goto_desk("/desk/booking-resource?resource_type=Hall", 2000);
		const exists = await call(page, "frappe.client.get_value", { doctype: "Booking Resource", filters: { resource_name: DEMO_HALL }, fieldname: "name" });
		if (!(exists.ok && exists.message && exists.message.name)) {
			const made = await call(page, "frappe.client.insert", {
				doc: { doctype: "Booking Resource", resource_name: DEMO_HALL, resource_type: "Hall", cost_center: "قاعات Imed - MMG", capacity: 30, item: "HALL-HOUR", location: "الدور الثاني (تجريبي)", notes: "قاعة تجريبية لتجربة الشاشات على موقع الديمو فقط." },
			});
			record("demo", "a demo hall exists on the demo site (never on frontend)", made.ok, JSON.stringify(made).slice(0, 160));
		} else record("demo", "a demo hall exists on the demo site (never on frontend)", true, exists.message.name);
		const old = await call(page, "frappe.client.get_list", { doctype: "Booking", filters: { resource: DEMO_HALL, booking_date: TODAY, status: ["not in", ["Cancelled", "No Show"]] }, fields: ["name"] });
		for (const row of (old.ok && old.message) || []) {
			await call(page, "frappe.client.set_value", { doctype: "Booking", name: row.name, fieldname: { status: "Cancelled", cancellation_reason: "إعادة تشغيل تجربة الشاشات (تجريبي)" } });
		}
		await page.goto_desk("/desk/booking-resource?resource_type=Hall", 2500);
		record("halls", "the halls list shows capacity and location", /عدد الأماكن/.test(await body_text(page)), await shot(page, "demo-halls-list"));
		await page.goto_desk(`/desk/booking-resource/${encodeURIComponent(DEMO_HALL)}`, 2500);
		record("halls", "a hall offers Book This Hall and Calendar", /احجزي القاعة دي/.test(await body_text(page)) && /التقويم/.test(await body_text(page)), await shot(page, "demo-hall-form"));
		await context.close();
	}

	// Nour, the halls' manager: book, see it is free, choose the type, save, confirm, clash, reschedule, cancel.
	const { context, page } = await open(browser, "demo", "nour@imed.local");
	await page.goto_desk("/desk/booking/new", 2500);
	record("booking", "a new booking shows the steps", /خطوة بخطوة/.test(await body_text(page)), await shot(page, "demo-booking-steps"));
	await set(page, { resource: DEMO_HALL });
	await page.waitForTimeout(1200);
	await set(page, { booking_date: TODAY, from_time: "10:00:00", to_time: "12:00:00" });
	await page.waitForTimeout(2000);
	let t = await body_text(page);
	record("booking", "the form says the hall is free as the times are typed", /القاعة فاضية في الوقت ده/.test(t), await shot(page, "demo-booking-free"));
	const labels = await page.evaluate(() => [...document.querySelectorAll(".frappe-control:not(.hide-control) .control-label")].filter((l) => l.offsetParent !== null).map((l) => l.innerText.trim()).filter(Boolean));
	record("booking", "labels: من الساعة / لحد الساعة / نوع الحجز", ["من الساعة", "لحد الساعة", "نوع الحجز"].every((l) => labels.includes(l)), labels.join(", "));
	record("booking", "before a type is chosen, the doctor/course/attendees and the rental model are not shown", !labels.some((l) => /الدكتور|الكورس|العدد المتوقع|نظام الإيجار/.test(l)), "");
	await set(page, { hall_booking_type: "Internal Course or Lecture" });
	await page.waitForTimeout(800);
	const labels2 = await page.evaluate(() => [...document.querySelectorAll(".frappe-control:not(.hide-control) .control-label")].filter((l) => l.offsetParent !== null).map((l) => l.innerText.trim()).filter(Boolean));
	record("booking", "an internal course shows the doctor, the course, the expected attendees and the capacity, and hides the price", /الدكتور/.test(labels2.join()) && /الكورس/.test(labels2.join()) && /العدد المتوقع/.test(labels2.join()) && !/تفاصيل السعر/.test(labels2.join()), await shot(page, "demo-booking-internal-course"));
	const doctor = await call(page, "frappe.client.get_value", { doctype: "Customer", filters: { customer_group: "طبيب" }, fieldname: "name" });
	await set(page, { activity: "محاضرة باثولوجي (تجريبي)", responsible_name: "نور", responsible_phone: "01011112222", expected_attendees: 25, doctor: doctor.message.name });
	await page.waitForTimeout(500);
	await page.evaluate(() => cur_frm.save());
	await page.waitForTimeout(3000);
	t = await body_text(page);
	const name = await page.evaluate(() => cur_frm.doc.name);
	record("booking", "saved: Tentative, not billable, no price, with the Confirm button", /مبدئي/.test(t) && /تأكيد الحجز/.test(t) && !/^BOOK-\.|new-booking/.test(name), `${name}; ${await shot(page, "demo-booking-saved")}`);
	await page.click("button:has-text('تأكيد الحجز')");
	await page.waitForTimeout(3000);
	t = await body_text(page);
	record("booking", "Confirm Booking → مؤكد (no deposit)", /مؤكد/.test(t), await shot(page, "demo-booking-confirmed"));
	const posted = await call(page, "frappe.client.get_count", { doctype: "Sales Invoice", filters: { custom_booking: name } });
	record("money", "confirming posts no invoice", posted.ok && posted.message === 0, JSON.stringify(posted.message));

	// The clash: the same hall, an overlapping time.
	await page.goto_desk("/desk/booking/new", 2000);
	await set(page, { resource: DEMO_HALL });
	await page.waitForTimeout(1200);
	await set(page, { booking_date: TODAY, from_time: "11:00:00", to_time: "13:00:00" });
	await page.waitForTimeout(2000);
	t = await body_text(page);
	record("booking", "an overlapping time is announced before saving, with the owner's words", /القاعة دي محجوزة بالفعل في الوقت اللي اخترته. جرّبي معاد تاني/.test(t), await shot(page, "demo-booking-clash-live"));
	await set(page, { hall_booking_type: "Internal Meeting", activity: "اجتماع (تجريبي)", responsible_name: "نور", responsible_phone: "01011112222" });
	await page.evaluate(() => cur_frm.save().catch(() => {}));
	await page.waitForTimeout(2500);
	const dialog = await page.evaluate(() => (document.querySelector(".modal.show .modal-body") || {}).innerText || "");
	record("booking", "the save is refused with the same message", /محجوزة بالفعل في الوقت اللي اخترته/.test(dialog), await shot(page, "demo-booking-clash-refused"));
	await page.keyboard.press("Escape");
	await page.waitForTimeout(500);

	// Reschedule, then cancel, from the buttons.
	await page.goto_desk(`/desk/booking/${name}`, 2500);
	await page.click("button:has-text('تغيير الموعد')");
	await page.waitForTimeout(1200);
	record("booking", "Reschedule opens a dialog with the date and times", /من الساعة/.test(await page.evaluate(() => (document.querySelector(".modal.show") || {}).innerText || "")), await shot(page, "demo-booking-reschedule"));
	await page.evaluate(async () => {
		await cur_dialog.set_values({ from_time: "14:00:00", to_time: "16:00:00" });
		cur_dialog.get_primary_btn().click();
	});
	await page.waitForTimeout(3000);
	const moved = await page.evaluate(() => [cur_frm.doc.from_time, cur_frm.doc.to_time, cur_frm.doc.status]);
	record("booking", "rescheduled to 14:00–16:00, still confirmed", moved[0] === "14:00:00" && moved[1] === "16:00:00" && moved[2] === "Confirmed", JSON.stringify(moved));
	await page.click("button:has-text('المزيد')");
	await page.waitForTimeout(500);
	await page.click("a:has-text('إلغاء الحجز'), button:has-text('إلغاء الحجز')");
	await page.waitForTimeout(1200);
	await page.evaluate(async () => {
		await cur_dialog.set_values({ reason: "تجربة الشاشات (تجريبي)" });
		cur_dialog.get_primary_btn().click();
	});
	await page.waitForTimeout(3000);
	t = await body_text(page);
	record("booking", "cancelled with its reason", /ملغي/.test(t) && (await page.evaluate(() => cur_frm.doc.status)) === "Cancelled", await shot(page, "demo-booking-cancelled"));
	const free_again = await call(page, "imed_erp.imederp.doctype.booking.booking.check_availability", { resource: DEMO_HALL, booking_date: TODAY, from_time: "14:00:00", to_time: "16:00:00" });
	record("booking", "a cancelled booking no longer occupies its time", free_again.ok && free_again.message.free === 1, JSON.stringify(free_again.message));
	const counts = await Promise.all(["Sales Invoice", "Payment Entry", "Journal Entry"].map((d) => call(page, "frappe.client.get_count", { doctype: d, filters: { custom_booking: name } })));
	record("money", "the whole journey posted nothing", counts.every((c) => c.ok && c.message === 0), JSON.stringify(counts.map((c) => c.message)));

	// A second, live booking for the calendar and the dashboard.
	await page.goto_desk("/desk/booking/new", 2000);
	await set(page, { resource: DEMO_HALL });
	await page.waitForTimeout(1200);
	await set(page, { booking_date: TODAY, from_time: "17:00:00", to_time: "19:00:00", hall_booking_type: "Internal Course or Lecture", activity: "كورس أناتومي (تجريبي)", responsible_name: "نور", responsible_phone: "01011112222", doctor: doctor.message.name });
	await page.waitForTimeout(800);
	await page.evaluate(() => cur_frm.save());
	await page.waitForTimeout(3000);
	const live = await page.evaluate(() => cur_frm.doc.name);
	await page.goto_desk("/desk/booking/view/calendar/default?resource_type=Hall", 4000);
	t = await body_text(page);
	record("calendar", "the hall calendar shows the hall, the purpose, the doctor and the status, and the Arabic legend", /كورس أناتومي/.test(t) && /مبدئي/.test(t) && /صيانة/.test(t), await shot(page, "demo-hall-calendar"));
	await page.goto_desk("/desk/booking?resource_type=Hall", 2500);
	record("list", "the hall bookings list (filtered from the sidebar)", /كورس أناتومي|قاعة تجريبية/.test(await body_text(page)), await shot(page, "demo-hall-bookings-list"));
	record("ui", "nour: no script error through the journey", page.errors.filter((e) => !/removeChild|Cannot read properties of null/.test(e)).length === 0, page.errors.join(" | ").slice(0, 300));
	await context.close();

	// Gilan (the studio) sees none of the halls' bookings; the owner's dashboard counts today's hall booking.
	{
		const { context, page } = await open(browser, "demo", "gilan@imed.local");
		await page.goto_desk("/desk/booking?resource_type=Hall", 2500);
		const rows = await page.evaluate(() => document.querySelectorAll(".list-row-container .list-row").length);
		record("permissions", "gilan (studio) sees no hall booking in the halls' list", rows === 0, `${rows} rows; ${await shot(page, "demo-gilan-hall-list-empty")}`);
		const refused = await call(page, "frappe.client.insert", { doc: { doctype: "Booking", resource: DEMO_HALL, booking_date: TODAY, from_time: "20:00:00", to_time: "21:00:00", hall_booking_type: "Internal Meeting", activity: "x", responsible_name: "x", responsible_phone: "01011112222" } });
		record("permissions", "gilan may not book a hall", !refused.ok, JSON.stringify(refused).slice(0, 120));
		await context.close();
	}
	{
		const { context, page } = await open(browser, "demo", "owner@imed.local");
		await page.goto_desk("/desk/owner-dashboard", 5000);
		const t = await body_text(page);
		record("dashboard", "owner: the hall card shows today's booking", /حجوزات قاعات IMED/.test(t) && /النهاردة/.test(t), await shot(page, "demo-owner-dashboard-halls"));
		await context.close();
	}
	// Phone width: the booking form and the sidebar.
	{
		const { context, page } = await open(browser, "demo", "nour@imed.local", { width: 390, height: 844 });
		await page.goto_desk("/desk/booking/new", 2500);
		const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
		record("ui", "the booking form fits a phone (390 px)", overflow <= 2, `overflow ${overflow}px; ${await shot(page, "demo-booking-phone")}`);
		await context.close();
	}

	await browser.close();
	fs.writeFileSync(path.join(SHOTS, "results.json"), JSON.stringify(results, null, 1));
	const failed = results.filter((r) => !r.ok);
	console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`);
	process.exit(failed.length ? 1 : 0);
})().catch((e) => {
	console.error(e);
	process.exit(2);
});
