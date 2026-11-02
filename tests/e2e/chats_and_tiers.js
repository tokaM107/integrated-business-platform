// Saved assistant chats and hall price tiers, in real sessions on the throwaway site (after a migrate, with
// setup/e2e_fixtures.py run). No model is configured there: the assistant answers that it is not connected, and the
// user's turn is still kept. Makes two chats and two bookings on that site.
//   IMED_E2E_PASSWORD=... node chats_and_tiers.js
const { chromium, BASE, session, call, record, results, shot } = require("./lib");
const A = "imed_erp.assistant.api.";

(async () => {
	const browser = await chromium.launch();

	// ---------- saved chats ----------
	const owner = await session(browser, "owner@imed.local");
	const status = await call(owner.page, A + "get_status");
	record("chats", "the owner may use the assistant", status.ok && status.message.allowed, JSON.stringify(status.message));
	const chat = await call(owner.page, A + "new_chat", { title: "e2e chat" });
	record("chats", "the owner opens a new chat", chat.ok && !!chat.message, JSON.stringify(chat.message));
	const sent = await call(owner.page, A + "send_message", { chat: chat.message, text: "كام حجز النهارده؟" });
	const kept = await call(owner.page, A + "get_chat", { chat: chat.message });
	const turns = (kept.message && kept.message.messages) || [];
	record("chats", "the question is kept in the chat, the answer says the model is not connected", sent.ok && turns.some((m) => m.role === "user"), JSON.stringify(sent.message || sent).slice(0, 160));
	const listed = await call(owner.page, A + "list_chats");
	record("chats", "the chat is in the owner's list", listed.ok && listed.message.some((c) => c.name === chat.message));
	owner.page.errors.length = 0;
	await owner.page.goto(BASE + "/desk");
	await owner.page.waitForTimeout(2500);
	record("chats", "the desk with the chat window opens without a script error", owner.page.errors.length === 0, owner.page.errors.join(" | ") + " " + (await shot(owner.page, "chats-desk")));

	const acc = await session(browser, "accountant@imed.local");
	const accStatus = await call(acc.page, A + "get_status");
	record("chats", "the accountant may not use the assistant (policy unchanged)", accStatus.ok && accStatus.message.allowed === false, JSON.stringify(accStatus.message));
	const peek = await call(acc.page, A + "get_chat", { chat: chat.message });
	record("chats", "the accountant cannot open the owner's chat through the API", !peek.ok, JSON.stringify(peek).slice(0, 120));
	const desk = await call(acc.page, "frappe.client.get", { doctype: "Assistant Chat", name: chat.message });
	record("chats", "nor through the desk's REST", !desk.ok, JSON.stringify(desk).slice(0, 120));

	// ---------- hall price tiers ----------
	const nour = await session(browser, "nour@imed.local");
	const customer = await call(nour.page, "frappe.client.get_list", { doctype: "Customer", filters: { customer_group: ["!=", "طبيب"] }, fields: ["name"], limit_page_length: 1 });
	const day = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
	for (const [to, hours, expected] of [["11:30:00", 1.5, 1200], ["14:30:00", 2.5, 1900]]) {
		const from = hours === 1.5 ? "10:00:00" : "12:00:00";
		const made = await call(nour.page, "frappe.client.insert", {
			doc: {
				doctype: "Booking", resource: "قاعة 1", booking_date: day, from_time: from, to_time: to, status: "Tentative",
				hall_booking_type: "Fixed-fee Rental", rental_model: "Fixed Rent", activity: "e2e tier check",
				responsible_name: "E2E", responsible_phone: "01012345678", customer: customer.message[0].name,
			},
		});
		const total = made.ok ? made.message.total_amount : null;
		record("tiers", `${hours} h in قاعة 1 is priced by its tier (${expected})`, made.ok && total === expected, JSON.stringify(made.ok ? { name: made.message.name, hours: made.message.hours, total } : made).slice(0, 200));
	}
	nour.page.errors.length = 0;
	await nour.page.goto(BASE + "/desk/hall-price-tier");
	await nour.page.waitForTimeout(2000);
	record("tiers", "the halls manager's tier list opens without a script error", nour.page.errors.length === 0, nour.page.errors.join(" | "));

	await browser.close();
	const failed = results.filter((r) => !r.ok).length;
	console.log(`\n${results.length - failed} of ${results.length} passed.`);
	process.exit(failed ? 1 : 0);
})();
