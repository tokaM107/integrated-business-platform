// The demo site's screens of 22 Oct 2026 (setup/seed_demo_22oct.py), each as the role that uses it: BA Plus payments,
// the day's counters read morning and evening, prepaid studio hours, the cash hand-over and its Arabic receipt.
// Read-only, apart from calls the server refuses. Run with IMED_E2E_SITE=demo.
setTimeout(() => { console.log("TIMEOUT"); process.exit(3); }, 400000);
const { chromium, BASE, session, record, shot, call } = require("./lib");

async function form(page, doctype, name) {
	await page.goto(`${BASE}/desk/${doctype.toLowerCase().replace(/ /g, "-")}/${encodeURIComponent(name)}`);
	await page.waitForFunction((dt) => window.cur_frm && cur_frm.doctype === dt && cur_frm.doc && cur_frm.doc.name, doctype, { timeout: 30000 });
	await page.waitForTimeout(1500);
	return page.evaluate(() => ({
		// Every banner: Frappe adds its own ("Submit this document to confirm") beside the screen's.
		intro: [...document.querySelectorAll(".form-message, .form-dashboard .alert")].map((e) => e.innerText.trim()).join(" | "),
		buttons: Object.keys(cur_frm.custom_buttons || {}),
		dir: document.documentElement.dir,
		doc: cur_frm.doc,
	}));
}

async function names(page, doctype, filters = {}) {
	const r = await call(page, "frappe.client.get_list", { doctype, filters, fields: ["name"], limit_page_length: 0 });
	return (r.message || []).map((d) => d.name);
}

(async () => {
	const browser = await chromium.launch();
	const as = {};
	for (const u of ["sara", "raghad", "owner", "accountant", "gilan"]) as[u] = (await session(browser, `${u}@imed.local`)).page;

	// BA Plus payments: Sara sees her branch's cash payment only; the owner sees all four in the report.
	const saraPays = await names(as.sara, "App Payment");
	record("payments", "Sara sees her own branch's payments only", saraPays.length === 1, saraPays.join(","));
	const pay = await form(as.sara, "App Payment", saraPays[0]);
	record("payments", "A cash payment says it is held for the doctor, in Arabic", pay.dir === "rtl" && /الدكتور/.test(pay.intro) && pay.doc.payment_method === "Cash", pay.intro);
	console.log(await shot(as.sara, "d22-app-payment"));
	const report = await call(as.owner, "frappe.desk.query_report.run", { report_name: "App Payments", filters: { from_date: "2026-10-01", to_date: "2026-10-31" } });
	const rows = ((report.message || {}).result || []).filter((r) => r && r.name);
	record("payments", "The owner's App Payments report lists cash and electronic payments", rows.length >= 4 && rows.some((r) => r.reference_no), `${rows.length} rows`);
	await as.owner.goto(`${BASE}/desk/query-report/App Payments?from_date=2026-10-01&to_date=2026-10-31`);
	await as.owner.waitForTimeout(5000);
	console.log(await shot(as.owner, "d22-app-payments-report"));

	// Counters: Raghad's morning-only day; Sara's full day with its gap.
	const morning = (await names(as.raghad, "Daily Counter Reading", { docstatus: 0 }))[0];
	const m = await form(as.raghad, "Daily Counter Reading", morning);
	const rowsShown = await as.raghad.evaluate(() => cur_frm.fields_dict.machines.grid.grid_rows.length);
	record("counters", "Raghad's day waits for the evening readings, morning ones kept", /آخر اليوم|Evening/.test(m.intro) && m.doc.opening_recorded_by === "raghad@imed.local" && rowsShown >= 3, m.intro);
	console.log(await shot(as.raghad, "d22-counters-morning"));
	const day = (await names(as.sara, "Daily Counter Reading", { docstatus: 1, reading_date: ["=", "2026-10-21"] }))[0];
	const d = await form(as.sara, "Daily Counter Reading", day);
	record("counters", "Sara's day shows printed sheets and the gap since last closing", d.doc.total_gap === 35 && d.doc.total_consumed > 0, `gap ${d.doc.total_gap}, printed ${d.doc.total_consumed}`);
	console.log(await shot(as.sara, "d22-counters-gap"));

	// Prepaid studio hours: Gilan's package shows what is left.
	const pkg = (await names(as.gilan, "Studio Hour Package"))[0];
	const p = await form(as.gilan, "Studio Hour Package", pkg);
	record("studio", "The package shows 23.5 of 30 hours left with its sessions", p.doc.hours_remaining === 23.5 && p.doc.usage.length === 3 && /23/.test(p.intro), p.intro);
	console.log(await shot(as.gilan, "d22-package"));
	const sara_pkg = await names(as.sara, "Studio Hour Package");
	record("studio", "A library manager does not see the studio's packages", sara_pkg.length === 0, `${sara_pkg.length}`);

	// The hand-over: branch isolation, the receiver's button, the confirmed one with its receipt.
	const saraHo = await names(as.sara, "Cash Handover");
	const raghadHo = await names(as.raghad, "Cash Handover");
	record("handover", "Each branch sees its own hand-overs", saraHo.length === 1 && raghadHo.length === 1 && saraHo[0] !== raghadHo[0], `${saraHo} / ${raghadHo}`);
	const pendingAsRaghad = await form(as.raghad, "Cash Handover", raghadHo[0]);
	record("handover", "Raghad's pending hand-over: print, no confirm for her", pendingAsRaghad.buttons.includes("اطبع الإيصال") && !pendingAsRaghad.buttons.includes("Confirm Receipt") && pendingAsRaghad.dir === "rtl", JSON.stringify(pendingAsRaghad.buttons));
	const refused = await call(as.raghad, "imed_erp.imederp.doctype.cash_handover.cash_handover.confirm_receipt", { name: raghadHo[0], received_amount: 1200 });
	record("handover", "The branch manager cannot confirm her own hand-over", refused.ok === false, JSON.stringify(refused));
	const pendingAsAccountant = await form(as.accountant, "Cash Handover", raghadHo[0]);
	const noScan = await call(as.accountant, "imed_erp.imederp.doctype.cash_handover.cash_handover.confirm_receipt", { name: raghadHo[0], received_amount: 1200 });
	record("handover", "The accountant (the receiver) has Confirm, refused without the signed receipt", pendingAsAccountant.buttons.length >= 2 && noScan.ok === false, JSON.stringify({ buttons: pendingAsAccountant.buttons, noScan }));
	console.log(await shot(as.accountant, "d22-handover-pending"));
	const done = await form(as.owner, "Cash Handover", saraHo[0]);
	record("handover", "The owner's confirmed hand-over: received, with its signed receipt and entry", done.doc.status === "Received" && !!done.doc.signed_receipt && !!done.doc.journal_entry, done.intro);
	console.log(await shot(as.owner, "d22-handover-received"));
	const scan = await as.raghad.evaluate(async (url) => (await fetch(url)).status, done.doc.signed_receipt);
	const scanOwner = await as.owner.evaluate(async (url) => (await fetch(url)).status, done.doc.signed_receipt);
	record("handover", "The signed receipt opens for the owner, not for another branch", scanOwner === 200 && scan !== 200, `owner ${scanOwner}, raghad ${scan}`);
	await as.owner.goto(`${BASE}/printview?doctype=Cash%20Handover&name=${encodeURIComponent(saraHo[0])}&format=Cash%20Handover%20Receipt`);
	await as.owner.waitForTimeout(4000);
	const print = await as.owner.evaluate(() => {
		const frame = document.querySelector("iframe");
		const doc = frame ? frame.contentDocument : document;
		return doc.body.innerText;
	});
	record("handover", "The receipt prints in Arabic with the amount in words and the signature space", /إيصال استلام نقدية/.test(print) && /ألفان و خمسمائة جنيه/.test(print) && /توقيع المستلم/.test(print), print.slice(0, 120).replace(/\n/g, " "));
	console.log(await shot(as.owner, "d22-receipt"));

	for (const [u, page] of Object.entries(as)) console.log("errors", u, page.errors.filter((e) => !/417 POST .*confirm_receipt/.test(e)));
	await browser.close();
	process.exit(0);
})();
