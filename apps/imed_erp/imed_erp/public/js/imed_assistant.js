// IMED ERP assistant: an animated character on the home screen that opens a chat panel at the side.
// Text and voice messages go to imed_erp.assistant.api.send_message; which AI answers is decided on
// the server (imed_erp/assistant/providers.py), so this file does not change when a model is connected.
//
// Shown only to users the server allows (the owner; see ALLOWED_ROLES in assistant/api.py). Mounted on
// Frappe's "desktop_screen" event; the conversation is kept in memory for the browser tab.
(() => {
	const is_ar = () => (frappe.boot.lang || "").startsWith("ar");
	// Strings for this file only; the full Arabic translation of the app is planned for week 11.
	const t = (en, ar) => (is_ar() ? ar : en);
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	const first_name = () => {
		const first = (frappe.session.user_fullname || "").trim().split(/\s+/)[0] || "";
		return first.charAt(0).toUpperCase() + first.slice(1);
	};

	const API = "imed_erp.assistant.api";
	const AUDIO_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
	const MAX_RECORD_SECONDS = 120;

	const SUGGESTIONS = () => [
		t("How much did we sell today?", "بعنا بكام النهارده؟"),
		t("Who owes us money?", "مين عليه فلوس لينا؟"),
		t("Paper stock in each store", "رصيد الورق في كل مخزن"),
		t("Doctors due for settlement", "الدكاترة اللي عليهم تسوية"),
	];

	// The character: a teal head with a face screen and an antenna ending in the logo's amber dot.
	const character = (cls) => `
		<svg class="imed-bot ${cls || ""}" viewBox="0 0 96 96" aria-hidden="true">
			<g class="imed-bot__body">
				<line class="imed-bot__antenna" x1="48" y1="22" x2="48" y2="10" />
				<circle class="imed-bot__dot" cx="48" cy="8" r="5.5" />
				<rect class="imed-bot__head" x="14" y="22" width="68" height="58" rx="22" />
				<rect class="imed-bot__screen" x="23" y="32" width="50" height="36" rx="14" />
				<g class="imed-bot__eyes">
					<ellipse cx="38" cy="48" rx="4.6" ry="6" />
					<ellipse cx="58" cy="48" rx="4.6" ry="6" />
				</g>
				<path class="imed-bot__smile" d="M40 58c4.5 4 11.5 4 16 0" />
				<circle class="imed-bot__cheek" cx="30" cy="58" r="3.2" />
				<circle class="imed-bot__cheek" cx="66" cy="58" r="3.2" />
				<rect class="imed-bot__ear" x="8" y="42" width="8" height="18" rx="4" />
				<rect class="imed-bot__ear" x="80" y="42" width="8" height="18" rx="4" />
			</g>
		</svg>`;

	const state = {
		status: null, // promise of get_status()
		history: [], // [{role, content}] sent to the server
		items: [], // what the panel shows: {role, text?, audio_url?, transcript?}
		busy: false,
		recorder: null,
		chunks: [],
		record_started: 0,
		record_timer: null,
	};

	function get_status() {
		if (!state.status) {
			state.status = frappe
				.xcall(`${API}.get_status`)
				.catch(() => ({ allowed: false }));
		}
		return state.status;
	}

	// ------------------------------------------------------------------ mount
	function mount(container) {
		const $root = $(`
			<div class="imed-assistant">
				<button type="button" class="imed-assistant-fab" aria-haspopup="dialog" aria-expanded="false"
					aria-label="${esc(t("Open the AI assistant", "افتح المساعد الذكي"))}">
					${character()}
					<span class="imed-assistant-fab__hint" aria-hidden="true">${esc(t("Ask me!", "اسألني!"))}</span>
				</button>
				<aside class="imed-assistant-panel" role="dialog" aria-modal="false" aria-labelledby="imed-assistant-title" hidden>
					<header class="imed-assistant-panel__head">
						<div class="imed-assistant-panel__avatar">${character("imed-bot--small")}</div>
						<div class="imed-assistant-panel__titles">
							<h2 id="imed-assistant-title">${esc(t("AI Assistant", "المساعد الذكي"))}</h2>
						</div>
						<button type="button" class="imed-assistant-panel__close" aria-label="${esc(t("Close", "إغلاق"))}">
							${frappe.utils.icon("x", "md")}
						</button>
					</header>
					<div class="imed-assistant-panel__log" role="log" aria-live="polite"></div>
					<div class="imed-assistant-panel__suggestions"></div>
					<form class="imed-assistant-composer">
						<div class="imed-assistant-recording" hidden>
							<span class="imed-assistant-recording__dot"></span>
							<span class="imed-assistant-recording__label">${esc(t("Recording", "بيسجّل"))}</span>
							<span class="imed-assistant-recording__time">0:00</span>
							<button type="button" class="imed-assistant-recording__cancel">${esc(t("Cancel", "إلغاء"))}</button>
						</div>
						<div class="imed-assistant-composer__row">
							<textarea rows="1" dir="auto" maxlength="4000"
								placeholder="${esc(t("Ask about sales, stock, doctors…", "اسأل عن المبيعات، المخازن، الدكاترة…"))}"
								aria-label="${esc(t("Message", "الرسالة"))}"></textarea>
							<button type="button" class="imed-assistant-mic" aria-pressed="false"
								aria-label="${esc(t("Record a voice message", "سجّل رسالة صوتية"))}"
								title="${esc(t("Record a voice message", "سجّل رسالة صوتية"))}">
								${frappe.utils.icon("mic", "md")}
							</button>
							<button type="submit" class="imed-assistant-send" aria-label="${esc(t("Send", "إرسال"))}"
								title="${esc(t("Send", "إرسال"))}">
								${frappe.utils.icon("send", "md")}
							</button>
						</div>
						<p class="imed-assistant-composer__note">
							${esc(t("Answers only; the assistant never changes your data.", "المساعد بيجاوب بس، ومش بيعدّل أي بيانات."))}
						</p>
					</form>
				</aside>
			</div>`);

		$(container).append($root);
		bind($root);
		render($root);
	}

	// ------------------------------------------------------------------ open / close
	function open($root) {
		$root.addClass("is-open");
		$root.find(".imed-assistant-panel").prop("hidden", false);
		$root.find(".imed-assistant-fab").attr("aria-expanded", "true");
		setTimeout(() => $root.find("textarea").trigger("focus"), 50);
		scroll_to_end($root);
	}

	function close($root) {
		stop_recording($root, true);
		$root.removeClass("is-open");
		$root.find(".imed-assistant-fab").attr("aria-expanded", "false").trigger("focus");
		// Keep the slide-out animation, then hide it from assistive technology.
		setTimeout(() => {
			if (!$root.hasClass("is-open")) $root.find(".imed-assistant-panel").prop("hidden", true);
		}, 250);
	}

	function bind($root) {
		$root.find(".imed-assistant-fab").on("click", () =>
			$root.hasClass("is-open") ? close($root) : open($root)
		);
		$root.find(".imed-assistant-panel__close").on("click", () => close($root));
		// Page-level, so Esc works even when focus left the panel (e.g. a button got disabled while sending).
		$(document)
			.off("keydown.imed-assistant")
			.on("keydown.imed-assistant", (e) => {
				if (e.key === "Escape" && $root.hasClass("is-open") && document.contains($root[0])) close($root);
			});

		const $input = $root.find("textarea");
		$input.on("input", () => autosize($input));
		$input.on("keydown", (e) => {
			// Enter sends, Shift+Enter makes a new line.
			if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
				e.preventDefault();
				$root.find("form").trigger("submit");
			}
		});
		$root.find("form").on("submit", (e) => {
			e.preventDefault();
			const text = $input.val().trim();
			if (!text || state.busy) return;
			$input.val("");
			autosize($input);
			send_text($root, text);
		});

		$root.find(".imed-assistant-mic").on("click", () =>
			state.recorder ? stop_recording($root) : start_recording($root)
		);
		$root.find(".imed-assistant-recording__cancel").on("click", () => stop_recording($root, true));
	}

	function autosize($input) {
		$input.css("height", "auto");
		$input.css("height", Math.min($input[0].scrollHeight, 140) + "px");
	}

	// ------------------------------------------------------------------ rendering
	function render($root) {
		const $log = $root.find(".imed-assistant-panel__log").empty();

		if (!state.items.length) {
			$log.append(`
				<div class="imed-assistant-welcome">
					${character("imed-bot--welcome")}
					<p class="imed-assistant-welcome__title">
						${esc(t("Hi", "أهلًا"))}${first_name() ? ` ${esc(first_name())}` : ""} 👋
					</p>
					<p class="imed-assistant-welcome__text">
						${esc(
							t(
								"Ask me about the business in plain words, typed or spoken.",
								"اسألني عن الشغل بكلامك العادي، كتابة أو بالصوت."
							)
						)}
					</p>
				</div>`);
		}

		state.items.forEach((item) => $log.append(bubble(item)));
		if (state.busy) {
			$log.append(`
				<div class="imed-assistant-msg is-assistant is-typing" aria-label="${esc(t("Typing", "بيكتب"))}">
					<span></span><span></span><span></span>
				</div>`);
		}

		const $sugg = $root.find(".imed-assistant-panel__suggestions").empty();
		if (!state.items.length) {
			SUGGESTIONS().forEach((s) =>
				$(`<button type="button" class="imed-assistant-chip" dir="auto">${esc(s)}</button>`)
					.on("click", () => send_text($root, s))
					.appendTo($sugg)
			);
		}

		$root.find(".imed-assistant-send, .imed-assistant-mic").prop("disabled", state.busy);
		scroll_to_end($root);
	}

	function bubble(item) {
		const cls = item.role === "user" ? "is-user" : item.error ? "is-assistant is-error" : "is-assistant";
		if (item.audio_url) {
			return `
				<div class="imed-assistant-msg ${cls} is-voice">
					<audio controls preload="metadata" src="${esc(item.audio_url)}"></audio>
					${item.transcript ? `<div class="imed-assistant-msg__transcript" dir="auto">${esc(item.transcript)}</div>` : ""}
				</div>`;
		}
		return `<div class="imed-assistant-msg ${cls}" dir="auto">${esc(item.text)}</div>`;
	}

	function scroll_to_end($root) {
		const log = $root.find(".imed-assistant-panel__log")[0];
		if (log) log.scrollTop = log.scrollHeight;
	}

	// ------------------------------------------------------------------ sending
	function send_text($root, text) {
		state.items.push({ role: "user", text });
		state.history.push({ role: "user", content: text });
		request($root, { messages: JSON.stringify(state.history) });
	}

	function send_voice($root, blob, mime) {
		const item = { role: "user", audio_url: URL.createObjectURL(blob) };
		state.items.push(item);
		const reader = new FileReader();
		reader.onloadend = () => {
			const audio = String(reader.result).split(",")[1] || "";
			request($root, { messages: JSON.stringify(state.history), audio, audio_type: mime }, item);
		};
		reader.readAsDataURL(blob);
	}

	function request($root, args, voice_item) {
		state.busy = true;
		render($root);
		frappe
			.xcall(`${API}.send_message`, args)
			.then((r) => {
				if (voice_item) {
					voice_item.transcript = r.transcript || "";
					state.history.push({
						role: "user",
						content: r.transcript || t("[voice message]", "[رسالة صوتية]"),
					});
				}
				state.items.push({ role: "assistant", text: r.reply });
				state.history.push({ role: "assistant", content: r.reply });
			})
			.catch(() => {
				// Keep the history consistent: drop the user turn that got no answer.
				if (!voice_item) state.history.pop();
				state.items.push({
					role: "assistant",
					error: true,
					text: t("The message could not be sent. Try again.", "الرسالة ما اتبعتتش، جرّب تاني."),
				});
			})
			.finally(() => {
				state.busy = false;
				render($root);
			});
	}

	// ------------------------------------------------------------------ voice
	async function start_recording($root) {
		if (!navigator.mediaDevices || !window.MediaRecorder) {
			frappe.show_alert({ message: t("This browser cannot record audio.", "المتصفح ده مش بيدعم التسجيل."), indicator: "orange" });
			return;
		}
		let stream;
		try {
			stream = await navigator.mediaDevices.getUserMedia({ audio: true });
		} catch (e) {
			frappe.show_alert({
				message: t("Allow microphone access to record.", "اسمح للمتصفح يستخدم الميكروفون عشان تسجّل."),
				indicator: "orange",
			});
			return;
		}
		const mime = AUDIO_TYPES.find((m) => MediaRecorder.isTypeSupported(m)) || "";
		const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
		state.recorder = recorder;
		state.chunks = [];
		state.cancelled = false;
		recorder.ondataavailable = (e) => e.data.size && state.chunks.push(e.data);
		recorder.onstop = () => {
			stream.getTracks().forEach((track) => track.stop());
			const type = (recorder.mimeType || mime || "audio/webm").split(";")[0];
			const blob = new Blob(state.chunks, { type });
			state.recorder = null;
			set_recording_ui($root, false);
			if (!state.cancelled && blob.size) send_voice($root, blob, type);
		};
		recorder.start();
		state.record_started = Date.now();
		set_recording_ui($root, true);
		state.record_timer = setInterval(() => {
			const s = Math.floor((Date.now() - state.record_started) / 1000);
			$root.find(".imed-assistant-recording__time").text(`${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`);
			if (s >= MAX_RECORD_SECONDS) stop_recording($root);
		}, 250);
	}

	function stop_recording($root, cancel) {
		if (!state.recorder) return;
		state.cancelled = !!cancel;
		clearInterval(state.record_timer);
		state.recorder.stop();
	}

	function set_recording_ui($root, on) {
		$root.toggleClass("is-recording", on);
		$root.find(".imed-assistant-recording").prop("hidden", !on);
		$root
			.find(".imed-assistant-mic")
			.attr("aria-pressed", on ? "true" : "false")
			.attr("aria-label", on ? t("Stop and send", "وقّف وابعت") : t("Record a voice message", "سجّل رسالة صوتية"));
		$root.find(".imed-assistant-recording__time").text("0:00");
	}

	// ------------------------------------------------------------------ hook
	function attach(scope) {
		get_status().then((status) => {
			if (!status || !status.allowed) return;
			const $wrapper = $(scope || document).find(".desktop-wrapper").first();
			if ($wrapper.length && !$wrapper.find(".imed-assistant").length) mount($wrapper);
		});
	}

	$(document).on("desktop_screen", (e, args) => {
		attach(args && args.desktop && args.desktop.page ? args.desktop.page.body : document);
	});
	// In case the home screen was drawn before this file loaded.
	$(() => attach(document));
})();
