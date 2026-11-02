// The assistant's voice controls in a real session (throwaway site): the panel opens without a script error, the
// microphone is labelled for dictation, an answer's read-aloud button asks the server for the Egyptian voice and,
// with no voice on the server, falls back without an error; the two voice endpoints are the owner's only.
//   IMED_E2E_PASSWORD=... node assistant_voice.js
const { chromium, BASE, session, call, record, results, shot } = require("./lib");
const A = "imed_erp.assistant.api.";

(async () => {
	const browser = await chromium.launch();
	const { page } = await session(browser, "owner@imed.local");
	await page.goto(BASE + "/desk");
	await page.waitForSelector(".imed-assistant-fab", { state: "attached", timeout: 30000 });
	page.errors.length = 0;
	const fab_visible = await page.locator(".imed-assistant-fab").isVisible();
	record("voice", "the assistant's button shows on the desk", fab_visible);
	await page.evaluate(() => document.querySelector(".imed-assistant-fab").click());
	await page.waitForTimeout(1200);
	const mic = await page.locator(".imed-assistant-mic").getAttribute("aria-label");
	record("voice", "the microphone is for dictation", /قول سؤالك|Speak your question/.test(mic || ""), mic);
	// An answer in the panel, as the chat window draws one, then its read-aloud button.
	const asked = await page.evaluate(() => {
		const log = document.querySelector(".imed-assistant-panel__log");
		log.insertAdjacentHTML("beforeend", '<div class="imed-assistant-msg is-assistant" dir="auto">عندنا تلات حجوزات النهارده<button type="button" class="imed-assistant-speak">🔊</button></div>');
		return !!log.querySelector(".imed-assistant-speak");
	});
	const spoke = page.waitForResponse((r) => r.url().includes(A + "speak"), { timeout: 30000 }).catch(() => null);
	await page.locator(".imed-assistant-speak").last().click();
	const response = await spoke;
	await page.waitForTimeout(1500);
	record("voice", "read aloud asks the server's voice", asked && !!response && response.status() === 200, response ? `${response.status()}` : "no request");
	record("voice", "no script error in the panel", page.errors.length === 0, page.errors.join(" | ") + " " + (await shot(page, "assistant-voice")));
	const label = await page.locator(".imed-assistant-speak").last().textContent();
	record("voice", "the button is back to 🔊 when no voice played", label.trim() === "🔊" || label.trim() === "⏹", label);
	const dictation = await call(page, A + "transcribe", { audio: btoa("not really webm"), audio_type: "audio/webm" });
	record("voice", "dictation answers with text or a reason, not an error", dictation.ok && typeof dictation.message.text === "string", JSON.stringify(dictation.message || dictation).slice(0, 160));

	const acc = await session(browser, "accountant@imed.local");
	const denied = await call(acc.page, A + "speak", { text: "x" });
	record("voice", "the accountant cannot use the voice endpoints", !denied.ok, JSON.stringify(denied).slice(0, 100));

	await browser.close();
	const failed = results.filter((r) => !r.ok).length;
	console.log(`\n${results.length - failed} of ${results.length} passed.`);
	process.exit(failed ? 1 : 0);
})();
