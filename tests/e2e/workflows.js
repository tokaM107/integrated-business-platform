// Business workflows through the real forms, as the people who do them. Runs on the throwaway restore-test site.
setTimeout(() => { console.log("TIMEOUT: the run took longer than 8 minutes"); process.exit(3); }, 480000);
const { chromium, BASE, session, call, shot, record, results } = require("./lib");
const fs = require("fs");
const TODAY = new Date().toISOString().slice(0, 10);

async function form(page, route) {
	await page.goto(BASE + route);
	await page.waitForFunction(() => window.cur_frm && cur_frm.doc && !cur_frm.doc.__unsaved_loading, null, { timeout: 30000 });
	await page.waitForTimeout(800);
}
async function setv(page, values) {
	for (const [k, v] of Object.entries(values)) {
		await page.evaluate(([k, v]) => cur_frm.set_value(k, v), [k, v]);
		await page.waitForTimeout(250);
	}
}
async function save(page) {
	// Not awaited in the page: saving a new form moves it to its new address.
	await page.evaluate(() => { cur_frm.save(); });
	await page.waitForFunction(() => window.cur_frm && !cur_frm.is_dirty() && !cur_frm.doc.__islocal, null, { timeout: 30000 }).catch(() => {});
	await page.waitForTimeout(800);
}
async function primary(page) {
	await page.locator(".page-head .primary-action:visible").first().click();
	await page.waitForTimeout(1500);
	const yes = page.locator(".modal.show .btn-primary:visible");
	if (await yes.count()) await yes.first().click();
	await page.waitForTimeout(2500);
}
async function submit(page) {
	// Not awaited in the page: savesubmit's promise settles only after the confirmation below is answered.
	await page.evaluate(() => { cur_frm.savesubmit(); });
	await page.waitForTimeout(1200);
	const yes = page.locator(".modal.show .btn-primary:visible");
	if (await yes.count()) await yes.first().click();
	await page.waitForFunction(() => cur_frm.doc.docstatus === 1, null, { timeout: 30000 }).catch(() => {});
	await page.waitForTimeout(1000);
}
async function shown_messages(page) {
	return page.evaluate(() => [...document.querySelectorAll(".modal.show .msgprint, .modal.show .modal-body")].map((e) => e.innerText.trim()).filter(Boolean).join(" | ").slice(0, 300));
}
async function custom_button(page, label_en) {
	const label = await page.evaluate((l) => __(l), label_en);
	const btn = page.locator(`.page-actions button:visible, .page-actions .dropdown-item`, { hasText: label });
	return { btn, label };
}

(async () => {
	const browser = await chromium.launch();

	// ---------- An expense, from Sara's request to the accountant's approval ----------
	{
		const { context, page } = await session(browser, "sara@imed.local");
		await form(page, "/desk/expense/new");
		const receipt = await page.evaluate(async () => {
			const fd = new FormData();
			fd.append("file", new Blob([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]), String(Date.now()) + Math.random()], { type: "image/png" }), `e2e-receipt-${Date.now()}.png`);
			fd.append("is_private", "1");
			const r = await fetch("/api/method/upload_file", { method: "POST", body: fd, headers: { "X-Frappe-CSRF-Token": frappe.csrf_token } });
			return (await r.json()).message.file_url;
		});
		await setv(page, { posting_date: TODAY, activity: "مكتبة الأزاريطة - MMG", expense_category: "الكهرباء", amount: 345, treasury: "خزينة مكتبة الأزاريطة - MMG", description: "E2E electricity" });
		await setv(page, { receipt });
		await save(page);
		const name = await page.evaluate(() => cur_frm.doc.name);
		record("workflow", "Sara saves an expense with its receipt", !name.startsWith("new-"), `${name}; ${await shown_messages(page)}`);
		await primary(page); // Request Approval
		const status = await page.evaluate(() => cur_frm.doc.approval_status);
		record("workflow", "Sara asks for approval", status === "Pending Approval", `status ${status}; ${await shot(page, "wf-expense-requested")}`);
		await context.close();

		const acc = await session(browser, "accountant@imed.local");
		await form(acc.page, `/desk/expense/${name}`);
		await primary(acc.page); // Approve
		await acc.page.reload();
		await acc.page.waitForFunction(() => window.cur_frm && cur_frm.doc && cur_frm.doc.name, null, { timeout: 30000 });
		const done = await acc.page.evaluate(() => ({ docstatus: cur_frm.doc.docstatus, je: cur_frm.doc.journal_entry, by: cur_frm.doc.approved_by }));
		record("workflow", "the accountant approves it and it is posted", done.docstatus === 1 && !!done.je && done.by === "accountant@imed.local", JSON.stringify(done));
		await acc.context.close();
	}

	// ---------- A transfer, sent by Sara and confirmed by the accountant ----------
	{
		const { context, page } = await session(browser, "sara@imed.local");
		const period = (await call(page, "frappe.client.get_list", { doctype: "Academic Period", filters: { period_type: "Term", is_closed: 0 }, fields: ["name"], limit_page_length: 1 })).message[0].name;
		await form(page, "/desk/inter-business-transfer/new");
		await setv(page, { posting_date: TODAY, from_business: "مكتبة الأزاريطة - MMG", from_treasury: "خزينة مكتبة الأزاريطة - MMG", to_business: "قاعات Imed - MMG", to_treasury: "خزينة سنتر Imed - MMG", amount: 120, reason: "E2E transfer", period });
		await save(page);
		await submit(page);
		const sent = await page.evaluate(() => ({ name: cur_frm.doc.name, docstatus: cur_frm.doc.docstatus, status: cur_frm.doc.status }));
		record("workflow", "Sara sends a transfer to the halls", sent.docstatus === 1 && sent.status === "Sent", JSON.stringify(sent) + " " + (await shown_messages(page)));
		await context.close();

		const acc = await session(browser, "accountant@imed.local");
		await form(acc.page, `/desk/inter-business-transfer/${sent.name}`);
		const { btn, label } = await custom_button(acc.page, "Confirm Receipt");
		if (await btn.count()) {
			await btn.first().click();
			await acc.page.waitForTimeout(1200);
			const yes = acc.page.locator(".modal.show .btn-primary:visible");
			if (await yes.count()) await yes.first().click();
			await acc.page.waitForTimeout(2500);
		}
		const got = await call(acc.page, "frappe.client.get_value", { doctype: "Inter Business Transfer", filters: { name: sent.name }, fieldname: ["status", "received_by"] });
		record("workflow", "the accountant confirms the receipt", got.ok && got.message.status === "Received", `button "${label}"; ${JSON.stringify(got.message)}`);
		await acc.context.close();
	}

	// ---------- An obsolete edition disposed of as scrap (owner, 21 Oct 2026) ----------
	{
		const { context, page } = await session(browser, "accountant@imed.local");
		const eds = await call(page, "frappe.client.get_list", { doctype: "Book Edition", filters: { status: "Cancelled", docstatus: 1, remaining_qty: [">", 0] }, fields: ["name", "agreement", "remaining_qty"], limit_page_length: 1 });
		const ed = eds.ok && eds.message[0];
		if (!ed) {
			record("workflow", "Dispose as Scrap on an obsolete edition", false, "no obsolete edition with copies left on this site");
		} else {
			const before = await call(page, "frappe.client.get_value", { doctype: "Doctor Agreement", filters: { name: ed.agreement }, fieldname: "balance" });
			await form(page, `/desk/book-edition/${encodeURIComponent(ed.name)}`);
			const { btn, label } = await custom_button(page, "Dispose as Scrap");
			record("ui", "an obsolete edition offers Dispose as Scrap", (await btn.count()) > 0, `button "${label}"; ${await shot(page, "wf-edition-obsolete")}`);
			if (await btn.count()) {
				// In the "Edition" menu, as a user reaches it: open the menu, then the item.
				const group = await page.evaluate(() => __("Edition"));
				await page.locator(".page-actions .inner-group-button button", { hasText: group }).first().click();
				await page.waitForTimeout(500);
				await btn.first().click();
				await page.waitForTimeout(1000);
				await page.locator(".modal.show .btn-primary:visible").first().click();
				await page.waitForURL(/damaged-stock-entry/, { timeout: 30000 }).catch(() => {});
				await page.waitForFunction(() => window.cur_frm && cur_frm.doctype === "Damaged Stock Entry", null, { timeout: 30000 }).catch(() => {});
				const draft = await page.evaluate(() => window.cur_frm && cur_frm.doctype === "Damaged Stock Entry" ? { name: cur_frm.doc.name, edition: cur_frm.doc.book_edition, qty: cur_frm.doc.items[0].qty } : null);
				record("workflow", "it makes the disposal as a draft for the edition's copies left", !!draft && draft.edition === ed.name && draft.qty === ed.remaining_qty, JSON.stringify(draft) + " " + (await shown_messages(page)));
				if (draft) {
					await submit(page);
					const posted = await page.evaluate(() => ({ docstatus: cur_frm.doc.docstatus, loss: cur_frm.doc.total_loss }));
					const edition = await call(page, "frappe.client.get_value", { doctype: "Book Edition", filters: { name: ed.name }, fieldname: ["disposed_qty", "remaining_qty"] });
					const after = await call(page, "frappe.client.get_value", { doctype: "Doctor Agreement", filters: { name: ed.agreement }, fieldname: "balance" });
					record(
						"workflow",
						"submitted: the copies leave the edition, the loss is the library's, the doctor's balance is untouched",
						posted.docstatus === 1 && edition.message.disposed_qty === ed.remaining_qty && edition.message.remaining_qty === 0 && after.message.balance === before.message.balance,
						`${JSON.stringify(posted)} edition ${JSON.stringify(edition.message)} balance ${before.message.balance} -> ${after.message.balance}; ${await shown_messages(page)}`
					);
				}
			}
		}
		await context.close();
	}

	// ---------- The doctor statement, with its filters ----------
	{
		const { context, page } = await session(browser, "accountant@imed.local");
		const ag = (await call(page, "frappe.client.get_list", { doctype: "Doctor Agreement", filters: { agreement_type: "Books", docstatus: 1 }, fields: ["name"], limit_page_length: 1 })).message[0].name;
		const per = (await call(page, "frappe.client.get_list", { doctype: "Academic Period", filters: { period_type: "Term" }, fields: ["name"], limit_page_length: 1 })).message[0].name;
		await page.goto(`${BASE}/desk/query-report/Doctor Statement?agreement=${encodeURIComponent(ag)}&period=${encodeURIComponent(per)}`);
		await page.waitForTimeout(4000);
		const rows = await page.evaluate(() => (frappe.query_report && frappe.query_report.data ? frappe.query_report.data.length : -1));
		record("workflow", "the accountant reads a doctor's statement", rows >= 2 && page.errors.length === 0, `${rows} rows; ${await shot(page, "wf-doctor-statement")} ${page.errors.join("|")}`);
		await context.close();
	}

	// ---------- A booking by the studio manager ----------
	{
		const { context, page } = await session(browser, "gilan@imed.local");
		const res = await call(page, "frappe.client.get_list", { doctype: "Booking Resource", filters: { cost_center: "استوديو X - MMG", disabled: 0 }, fields: ["name"], limit_page_length: 1 });
		const cust = await call(page, "frappe.client.get_list", { doctype: "Customer", filters: { customer_group: ["!=", "طبيب"] }, fields: ["name"], limit_page_length: 1 });
		if (!(res.ok && res.message.length)) {
			record("workflow", "Gilan books the studio", false, "no studio resource Gilan may book on this site");
		} else {
			// A different day each run, so a run never meets its own earlier booking.
			const day = new Date(Date.now() + (10 + Math.floor(Math.random() * 60)) * 86400000).toISOString().slice(0, 10);
			await form(page, "/desk/booking/new");
			await setv(page, { resource: res.message[0].name, customer: cust.message[0].name, booking_date: day, from_time: "13:00:00", to_time: "14:30:00" });
			await save(page);
			const b = await page.evaluate(() => ({ name: cur_frm.doc.name, hours: cur_frm.doc.hours, total: cur_frm.doc.total_amount, status: cur_frm.doc.status }));
			record("workflow", "Gilan books the studio for an hour and a half", !b.name.startsWith("new-") && b.hours === 1.5 && b.total > 0, JSON.stringify(b) + " " + (await shown_messages(page)));
		}
		await context.close();
	}

	// ---------- An app subscription by the app manager ----------
	{
		const { context, page } = await session(browser, "menna@imed.local");
		const course = await call(page, "frappe.client.get_list", { doctype: "App Course", filters: { status: "Active" }, fields: ["name"], limit_page_length: 1 });
		if (!(course.ok && course.message.length)) {
			record("workflow", "Menna subscribes a student", false, "no course Menna may see: " + JSON.stringify(course).slice(0, 120));
		} else {
			const group = (await call(page, "frappe.client.get_list", { doctype: "Customer Group", filters: { is_group: 0, name: ["!=", "طبيب"] }, fields: ["name"], limit_page_length: 1 })).message[0].name;
			const student = await call(page, "frappe.client.insert", { doc: { doctype: "Customer", customer_name: `E2E Student ${Date.now()}`, customer_group: group } });
			const stu = student.ok ? student.message.name : null;
			await form(page, "/desk/app-subscription/new");
			await setv(page, { student: stu, course: course.message[0].name, subscription_date: TODAY, cost_center: "تطبيق BA Plus - MMG" });
			await save(page);
			await submit(page);
			const s = await page.evaluate(() => ({ name: cur_frm.doc.name, docstatus: cur_frm.doc.docstatus, fee: cur_frm.doc.platform_fee }));
			record("workflow", "Menna subscribes a student and the fee is worked out", s.docstatus === 1 && s.fee > 0, JSON.stringify(s) + " customer " + JSON.stringify(student).slice(0, 120) + " " + (await shown_messages(page)));
		}
		await context.close();
	}

	await browser.close();
	fs.writeFileSync(__dirname + "/workflows-results.json", JSON.stringify(results, null, 1));
	console.log(`\n${results.filter((r) => r.ok).length} of ${results.length} passed`);
})();
