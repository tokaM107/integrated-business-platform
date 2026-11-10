// The assistant's voice end to end in a real browser (4 Nov 2026): a question spoken into a fake microphone (a WAV
// file) is written out by ElevenLabs into the box, sent, answered by Claude, and the answer read aloud by ElevenLabs.
// Needs a server running the code with ANTHROPIC_API_KEY and ELEVENLABS_API_KEY, on a throwaway site, e.g.:
//   docker run -d --name imed-wt-web --network frappe_docker_frappe_network -p 127.0.0.1:8091:8000 \
//     -e ANTHROPIC_API_KEY -e ELEVENLABS_API_KEY -e PYTHONPATH=/home/frappe/frappe-bench/apps/imed_erp \
//     -v $PWD/apps/imed_erp:/home/frappe/frappe-bench/apps/imed_erp -v frappe_docker_sites:/home/frappe/frappe-bench/sites \
//     -v $PWD/apps/imed_erp/imed_erp/public:/home/frappe/frappe-bench/assets/imed_erp -w /home/frappe/frappe-bench \
//     --entrypoint bash frappe/erpnext:v16.36.0 -c 'env/bin/pip install -q "anthropic>=2.3,<3"; bench --site restore-test serve --port 8000 --noreload'
//   PW_FILE=<file with the owner's throwaway password> WAV=<question, padded with ~5 s of silence> SHOT=out.png node assistant_voice_live.js
// The fake microphone loops its file: record longer than the sentence. Frappe Charts on the Owner Dashboard may
// throw "removeChild" from its resize observer while the panel opens (seen 1 run in 3; Frappe's code, not this app's).
const { chromium } = require("playwright");
const BASE = process.env.E2E_BASE || "http://127.0.0.1:8091";
const SITE = process.env.IMED_E2E_SITE || "restore-test";
const PASSWORD = require("fs").readFileSync(process.env.PW_FILE, "utf8").trim();
const results = [];
const record = (check, ok, evidence = "") => {
	results.push(ok);
	console.log(`${ok ? "PASS" : "FAIL"}  ${check}${evidence ? "  — " + evidence : ""}`);
};

(async () => {
	const browser = await chromium.launch({
		args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-audio-capture=${process.env.WAV}`, "--autoplay-policy=no-user-gesture-required"],
	});
	const context = await browser.newContext({ extraHTTPHeaders: { "X-Frappe-Site-Name": SITE }, permissions: ["microphone"] });
	await context.route("**/socket.io/**", (r) => r.abort());
	await context.addInitScript(() => {
		const original = Node.prototype.removeChild;
		Node.prototype.removeChild = function (child) {
			try {
				return original.call(this, child);
			} catch (e) {
				console.error("REMOVECHILD " + (new Error().stack || "").split("\n").slice(1, 9).join(" | "));
				throw e;
			}
		};
	});
	const page = await context.newPage();
	page.on("console", (m) => m.text().startsWith("REMOVECHILD") && console.log(m.text().slice(0, 1500)));
	const errors = [];
	page.on("pageerror", (e) => errors.push(String(e.stack || e).slice(0, 900)));
	const timings = {};
	page.on("response", (r) => {
		const m = r.url().match(/assistant\.api\.(\w+)/);
		if (m) timings[m[1]] = { status: r.status(), at: Date.now() };
	});

	await page.goto(BASE + "/login");
	await page.fill("#login_email", "owner@imed.local");
	await page.fill("#login_password", PASSWORD);
	await Promise.all([page.waitForURL(/\/(app|desk)/, { timeout: 60000 }), page.click(".btn-login")]);
	await page.waitForSelector(".imed-assistant-fab", { state: "attached", timeout: 60000 });
	await page.evaluate(() => document.querySelector(".imed-assistant-fab").click());
	await page.waitForTimeout(800);

	// 1. Dictation: speak, stop, the words land in the box (nothing sent).
	const t0 = Date.now();
	await page.click(".imed-assistant-mic");
	await page.waitForTimeout(7000);
	await page.click(".imed-assistant-mic");
	await page.waitForFunction(() => document.querySelector(".imed-assistant-panel textarea").value.trim().length > 3, null, { timeout: 30000 }).catch(() => {});
	const said = await page.inputValue(".imed-assistant-panel textarea");
	record("the spoken question is written into the box", /حجز|الاستوديو|استوديو/.test(said), `"${said}" in ${((Date.now() - t0) / 1000).toFixed(1)} s (incl. 7 s recording)`);
	const sentBefore = await page.locator(".imed-assistant-msg.is-user").count();
	record("nothing was sent before the user presses Send", sentBefore === 0);

	// 2. Send it: Claude answers.
	const t1 = Date.now();
	await page.click(".imed-assistant-send");
	await page.waitForFunction(() => document.querySelectorAll(".imed-assistant-msg.is-assistant:not(.is-typing):not(.is-streaming)").length > 0, null, { timeout: 90000 }).catch(() => {});
	const answer = (await page.locator(".imed-assistant-msg.is-assistant").last().textContent() || "").replace(/[🔊⏳⏹]\s*$/u, "").trim();
	record("Claude answers in Egyptian Arabic", /[؀-ۿ]/.test(answer) && !/\*\*/.test(answer), `${((Date.now() - t1) / 1000).toFixed(1)} s: ${answer.slice(0, 140)}`);

	// 3. Read aloud: the server's voice plays.
	const t2 = Date.now();
	const spoke = page.waitForResponse((r) => r.url().includes("assistant.api.speak"), { timeout: 60000 }).catch(() => null);
	await page.locator(".imed-assistant-speak").last().click();
	const response = await spoke;
	const body = response ? await response.json().catch(() => ({})) : {};
	await page.waitForTimeout(1500);
	const label = (await page.locator(".imed-assistant-speak").last().textContent()).trim();
	record("the answer is read aloud by ElevenLabs (MP3 from the server, playing)", !!(body.message && body.message.audio) && body.message.mime === "audio/mpeg" && label === "⏹", `${response ? response.status() : "-"} ${body.message ? body.message.mime : ""}, button ${label}, ${((Date.now() - t2) / 1000).toFixed(1)} s`);
	await page.screenshot({ path: process.env.SHOT });
	record("no script error", errors.length === 0, errors.join(" | "));
	await browser.close();
	console.log(`\n${results.filter(Boolean).length} of ${results.length} passed.`);
	process.exit(results.every(Boolean) ? 0 : 1);
})();
