// Roles, pages, server calls and branch isolation, through a real browser session per user.
const { chromium, BASE, session, call, shot, record, results, logout } = require("./lib");
const fs = require("fs");

const USERS = {
	owner: "owner@imed.local",
	accountant: "accountant@imed.local",
	raghad: "raghad@imed.local", // Mawasah library manager (and the store approver)
	sara: "sara@imed.local", // Azarita library manager
	gilan: "gilan@imed.local", // studio manager
	nour: "nour@imed.local", // halls manager
	menna: "menna@imed.local", // app manager
};

async function opens(page, route) {
	// Opens a desk route; returns {denied, title} from what the page shows.
	await page.goto(BASE + route);
	await page.waitForTimeout(2500);
	return page.evaluate(() => {
		const text = document.body.innerText;
		return {
			denied: /Not Permitted|لا يُسمح|غير مسموح|ليس لديك صلاحية|Insufficient Permission|No permission/i.test(text),
			title: document.title,
		};
	});
}

(async () => {
	const browser = await chromium.launch();

	// ---------- Authentication ----------
	for (const [who, user] of Object.entries(USERS)) {
		const { context, page } = await session(browser, user);
		const info = await page.evaluate(() => ({ user: frappe.session.user, lang: frappe.boot.lang, dir: document.documentElement.dir }));
		record("auth", `${who} logs in (Arabic, right to left)`, info.user === user && info.lang === "ar" && info.dir === "rtl", JSON.stringify(info));
		record("ui", `${who}: no script errors on the home page`, page.errors.length === 0, page.errors.join(" | "));
		const status = await logout(page);
		record("auth", `${who} logs out`, status === 403 || status === 401, `after logout the session call answers ${status}`);
		await context.close();
	}
	{
		const { context, page } = await session(browser, null);
		await page.goto(BASE + "/login");
		await page.fill("#login_email", USERS.sara);
		await page.fill("#login_password", "wrong-password");
		await page.click(".btn-login");
		await page.waitForTimeout(2500);
		const user = await page.evaluate(() => (window.frappe && frappe.session && frappe.session.user) || "Guest");
		record("auth", "a wrong password is refused", user === "Guest" || !/desk|app/.test(page.url()), `url ${page.url()}`);
		await context.close();
	}

	// ---------- Sara: Azarita's library manager ----------
	{
		const { context, page } = await session(browser, USERS.sara);
		const ledger = await opens(page, "/desk/doctor-ledger-entry");
		record("pages", "Sara cannot open the doctors' ledger", ledger.denied, JSON.stringify(ledger));
		for (const report of ["Doctor Statement", "Doctor Debts", "Platform Fees"]) {
			const r = await call(page, "frappe.desk.query_report.get_script", { report_name: report });
			record("pages", `Sara cannot open the report ${report}`, !r.ok && r.status === 403, JSON.stringify(r));
		}
		const own = await call(page, "frappe.desk.query_report.run", { report_name: "Treasury Balances", filters: { date: new Date().toISOString().slice(0, 10) } });
		const boxes = own.ok ? own.message.result.map((r) => r.treasury) : [];
		record(
			"isolation",
			"Sara's Treasury Balances: her box and the wallets only",
			own.ok && boxes.includes("خزينة مكتبة الأزاريطة - MMG") && !boxes.some((b) => /المواساة|سنتر|Studio/.test(b)),
			JSON.stringify(boxes)
		);
		const dash = await call(page, "imed_erp.imederp.owner_dashboard.revenue_this_month");
		record("api", "Sara cannot read the owner's figures", !dash.ok, JSON.stringify(dash));
		const machines = await call(page, "imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading.get_machines", { branch: "مكتبة المواساة - MMG" });
		record("api", "Sara cannot list Mawasah's machines", !machines.ok, JSON.stringify(machines));
		const sales = await call(page, "frappe.client.get_list", { doctype: "Sales Invoice", fields: ["name", "cost_center"], limit_page_length: 100 });
		record(
			"isolation",
			"Sara's sales list holds Azarita's sales only",
			sales.ok && sales.message.every((s) => s.cost_center === "مكتبة الأزاريطة - MMG"),
			sales.ok ? `${sales.message.length} invoices: ${[...new Set(sales.message.map((s) => s.cost_center))]}` : JSON.stringify(sales)
		);
		const je = await call(page, "frappe.client.insert", {
			doc: { doctype: "Journal Entry", company: "Mohamed Mamdouh group", posting_date: new Date().toISOString().slice(0, 10), accounts: [] },
		});
		record("money", "Sara cannot make a journal entry", !je.ok, JSON.stringify(je));
		const mawasahInvoice = await page.evaluate(async () => {
			const r = await frappe.xcall("frappe.client.get_value", { doctype: "Sales Invoice", filters: { cost_center: "مكتبة المواساة - MMG" }, fieldname: "name" }).catch((e) => ({ error: true }));
			return r;
		});
		record("isolation", "Sara cannot look up a Mawasah sale", !mawasahInvoice || mawasahInvoice.error || !mawasahInvoice.name, JSON.stringify(mawasahInvoice));
		// A return (credit note) on one of her own sales.
		const mine = sales.ok && sales.message[0];
		if (mine) {
			const ret = await call(page, "erpnext.accounts.doctype.sales_invoice.sales_invoice.make_sales_return", { source_name: mine.name });
			let refused = !ret.ok;
			let detail = JSON.stringify(ret).slice(0, 160);
			if (ret.ok) {
				const doc = Object.assign(ret.message, { return_reason: "test" });
				const saved = await call(page, "frappe.client.insert", { doc });
				refused = !saved.ok;
				detail = JSON.stringify(saved).slice(0, 160);
			}
			record("money", "Sara cannot return a sale (QA-04)", refused, detail);
			const cancel = await call(page, "imed_erp.imederp.sales_cancellation.cancel_with_reason", { doctype: "Sales Invoice", name: mine.name, reason: "test" });
			record("money", "Sara cannot cancel a sale", !cancel.ok, JSON.stringify(cancel).slice(0, 160));
		} else {
			record("money", "Sara cannot return or cancel a sale", false, "no sale of hers on this site to try");
		}
		await context.close();
	}

	// ---------- Gilan (studio) and Nour (halls) ----------
	for (const [who, own, other] of [
		["gilan", "استوديو X - MMG", "مكتبة الأزاريطة - MMG"],
		["nour", "قاعات Imed - MMG", "استوديو X - MMG"],
	]) {
		const { context, page } = await session(browser, USERS[who]);
		const r = await opens(page, "/desk/booking/view/calendar/Booking");
		record("pages", `${who} opens the bookings calendar`, !r.denied && page.errors.length === 0, JSON.stringify(r) + " " + page.errors.join("|"));
		const exp = await call(page, "frappe.client.get_list", { doctype: "Expense", fields: ["name", "activity"], limit_page_length: 100 });
		record(
			"isolation",
			`${who} sees no other business's expenses`,
			exp.ok && exp.message.every((e) => e.activity === own),
			exp.ok ? `${exp.message.length} expenses: ${[...new Set(exp.message.map((e) => e.activity))]}` : JSON.stringify(exp)
		);
		const statement = await call(page, "frappe.desk.query_report.get_script", { report_name: "Doctor Statement" });
		record("pages", `${who} cannot open the doctor statement`, !statement.ok && statement.status === 403, JSON.stringify(statement));
		await context.close();
	}

	// ---------- Owner and accountant ----------
	for (const who of ["owner", "accountant"]) {
		const { context, page } = await session(browser, USERS[who]);
		for (const report of ["Treasury Balances", "Doctor Statement", "Doctor Debts", "Platform Fees", "Expense Report", "Daily Printing"]) {
			const r = await opens(page, `/desk/query-report/${report}`);
			record("pages", `${who} opens ${report}`, !r.denied && page.errors.length === 0, JSON.stringify(r) + " " + page.errors.join("|"));
			page.errors.length = 0;
		}
		const figures = await call(page, "imed_erp.imederp.owner_dashboard.revenue_this_month");
		record("api", `${who} reads the owner's figures`, figures.ok, JSON.stringify(figures));
		await context.close();
	}

	// ---------- Phone width ----------
	for (const [who, route] of [["owner", "/desk/owner-dashboard"], ["sara", "/desk/expense/new"]]) {
		const { context, page } = await session(browser, USERS[who], { viewport: { width: 390, height: 844 } });
		await page.goto(BASE + route);
		await page.waitForTimeout(3000);
		const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
		record("ui", `${who}: ${route} fits a phone (390 px), no sideways scroll`, overflow <= 2, `overflow ${overflow}px; ${await shot(page, `phone-${who}`)}`);
		await context.close();
	}

	// ---------- Accessibility of the home page ----------
	{
		const { context, page } = await session(browser, USERS.sara);
		await page.goto(BASE + "/desk");
		await page.waitForTimeout(3000);
		const a11y = await page.evaluate(() => {
			const actions = [...document.querySelectorAll(".imed-home-action")];
			return {
				actions: actions.length,
				buttons: actions.filter((b) => b.tagName === "BUTTON" && !b.getAttribute("role")).length,
				inListItems: actions.filter((b) => b.parentElement.getAttribute("role") === "listitem").length,
				unlabeled: [...document.querySelectorAll("button")].filter((b) => !(b.innerText.trim() || b.getAttribute("aria-label") || b.title)).length,
			};
		});
		record("a11y", "home quick actions are buttons inside list items", a11y.actions === 0 || (a11y.buttons === a11y.actions && a11y.inListItems === a11y.actions), JSON.stringify(a11y));
		await shot(page, "sara-home");
		await context.close();
	}

	await browser.close();
	fs.writeFileSync(__dirname + "/roles-results.json", JSON.stringify(results, null, 1));
	console.log(`\n${results.filter((r) => r.ok).length} of ${results.length} passed`);
})();
