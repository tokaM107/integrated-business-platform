// IMED ERP assistant: an animated character in the corner of every page that opens a chat panel at the side.
// Text and voice messages go to imed_erp.assistant.api.send_message; which AI answers is decided on
// the server (imed_erp/assistant/providers/), so this file does not change when a model is connected.
//
// Shown only to users the server allows (the owner; see ALLOWED_ROLES in assistant/api.py). Mounted on
// the page once Frappe has started; the conversation is kept in memory for the browser tab.
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
		chat: null, // the saved chat open now (its name), or null before the first message
		chats: [], // the user's saved chats [{name, title, last_message_at}]
		list_open: false,
		history: [], // [{role, content}] shown; the server keeps the saved chat's own memory
		items: [], // what the panel shows: {role, text?, audio_url?, transcript?}
		audio_urls: [], // the voice messages' object URLs, released when the page goes
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
							<small class="imed-assistant-panel__chat-title"></small>
						</div>
						<button type="button" class="imed-assistant-panel__chats" aria-label="${esc(t("Chats", "المحادثات"))}" title="${esc(t("Chats", "المحادثات"))}">
							${frappe.utils.icon("list", "md")}
						</button>
						<button type="button" class="imed-assistant-panel__new" aria-label="${esc(t("New chat", "محادثة جديدة"))}" title="${esc(t("New chat", "محادثة جديدة"))}">
							${frappe.utils.icon("add", "md")}
						</button>
						<button type="button" class="imed-assistant-panel__close" aria-label="${esc(t("Close", "إغلاق"))}">
							${frappe.utils.icon("x", "md")}
						</button>
					</header>
					<div class="imed-assistant-chatlist" hidden></div>
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
		$root.find(".imed-assistant-panel__new").on("click", () => start_new_chat($root));
		$root.find(".imed-assistant-panel__chats").on("click", () => toggle_list($root));
		$root.on("click", ".imed-assistant-chatlist__item", function () { open_chat($root, $(this).data("name")); });
		$root.on("click", ".imed-assistant-chatlist__delete", function (e) { e.stopPropagation(); delete_chat($root, $(this).closest(".imed-assistant-chatlist__item").data("name")); });
		$root.on("click", ".imed-assistant-chatlist__rename", function (e) { e.stopPropagation(); rename_chat($root, $(this).closest(".imed-assistant-chatlist__item").data("name")); });
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
		bind_speak($root);
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
		// An answer is read aloud by the model's Egyptian voice (api.speak); the browser's own voice only when the
		// server has none (2 Nov 2026: the browser's read Arabic letter by letter, in no dialect).
		const speak = item.role === "assistant" && !item.error
			? `<button type="button" class="imed-assistant-speak" title="${esc(t("Read aloud", "اقرأ بصوت"))}" aria-label="${esc(t("Read aloud", "اقرأ بصوت"))}">🔊</button>`
			: "";
		return `<div class="imed-assistant-msg ${cls}" dir="auto">${esc(item.text)}${speak}</div>`;
	}

	function speak_text(text) {
		if (!window.speechSynthesis) return;
		window.speechSynthesis.cancel();
		const utter = new SpeechSynthesisUtterance(text);
		utter.lang = /[\u0600-\u06FF]/.test(text) ? "ar-EG" : "en-US";
		const voice = window.speechSynthesis.getVoices().find((v) => v.lang && v.lang.toLowerCase().startsWith(utter.lang.slice(0, 2)));
		if (voice) utter.voice = voice;
		utter.rate = 0.95;
		window.speechSynthesis.speak(utter);
	}

	// One answer plays at a time; each answer's audio is fetched once and kept for the page.
	const spoken = new Map();
	let playing = null; // {audio, $btn}

	function stop_playing() {
		if (window.speechSynthesis) window.speechSynthesis.cancel();
		if (!playing) return;
		playing.audio.pause();
		playing.$btn.text("🔊").removeClass("is-playing");
		playing = null;
	}

	function play(url, $btn) {
		const audio = new Audio(url);
		playing = { audio, $btn };
		$btn.text("⏹").addClass("is-playing");
		audio.addEventListener("ended", () => stop_playing());
		audio.play().catch(() => stop_playing());
	}

	function speak_answer($btn, text) {
		if (playing && playing.$btn[0] === $btn[0]) return stop_playing();
		stop_playing();
		if (spoken.has(text)) return play(spoken.get(text), $btn);
		$btn.text("⏳").prop("disabled", true);
		frappe
			.xcall(`${API}.speak`, { text })
			.then((r) => {
				if (r && r.audio) {
					const url = `data:${r.mime || "audio/wav"};base64,${r.audio}`;
					spoken.set(text, url);
					play(url, $btn);
				} else {
					if (r && r.message) frappe.show_alert({ message: r.message, indicator: "orange" });
					speak_text(text); // no voice on the server: the browser's own
				}
			})
			.catch(() => speak_text(text))
			.finally(() => $btn.prop("disabled", false).text(playing && playing.$btn[0] === $btn[0] ? "⏹" : "🔊"));
	}

	function bind_speak($root) {
		$root.off("click.imed-speak").on("click.imed-speak", ".imed-assistant-speak", function () {
			const $btn = $(this);
			speak_answer($btn, $btn.closest(".imed-assistant-msg").text().replace(/[🔊⏳⏹]\s*$/u, "").trim());
		});
	}

	function scroll_to_end($root) {
		const log = $root.find(".imed-assistant-panel__log")[0];
		if (log) log.scrollTop = log.scrollHeight;
	}

	// ------------------------------------------------------------------ sending
	function send_text($root, text) {
		state.items.push({ role: "user", text });
		state.history.push({ role: "user", content: text });
		ensure_chat($root).then((chat) => request($root, chat ? { chat, text } : { messages: JSON.stringify(state.history) }));
	}

	// ------------------------------------------------------------------ saved chats
	function ensure_chat($root) {
		if (state.chat) return Promise.resolve(state.chat);
		return frappe
			.xcall(`${API}.new_chat`, {})
			.then((name) => {
				state.chat = name;
				return name;
			})
			.catch(() => null); // without a saved chat the whole conversation is sent, as before
	}

	function start_new_chat($root) {
		state.chat = null;
		state.history = [];
		state.items = [];
		state.list_open = false;
		$root.find(".imed-assistant-chatlist").prop("hidden", true);
		$root.find(".imed-assistant-panel__chat-title").text("");
		render($root);
		$root.find("textarea").trigger("focus");
	}

	function load_chats($root) {
		return frappe
			.xcall(`${API}.list_chats`)
			.then((rows) => {
				state.chats = rows || [];
				render_list($root);
			})
			.catch(() => {});
	}

	function toggle_list($root) {
		state.list_open = !state.list_open;
		$root.find(".imed-assistant-chatlist").prop("hidden", !state.list_open);
		if (state.list_open) load_chats($root);
	}

	function render_list($root) {
		const $list = $root.find(".imed-assistant-chatlist").empty();
		if (!state.chats.length) {
			$list.append(`<p class="imed-assistant-chatlist__empty">${esc(t("No saved chats yet.", "مافيش محادثات محفوظة لسه."))}</p>`);
			return;
		}
		state.chats.forEach((c) => {
			const when = c.last_message_at ? frappe.datetime.prettyDate(c.last_message_at) : "";
			$list.append(`
				<div class="imed-assistant-chatlist__item ${c.name === state.chat ? "is-current" : ""}" data-name="${esc(c.name)}" role="button" tabindex="0">
					<div class="imed-assistant-chatlist__text" dir="auto"><b>${esc(c.title || t("New chat", "محادثة جديدة"))}</b><small>${esc(when)}</small></div>
					<button type="button" class="imed-assistant-chatlist__rename" title="${esc(t("Rename", "إعادة تسمية"))}">${frappe.utils.icon("edit", "sm")}</button>
					<button type="button" class="imed-assistant-chatlist__delete" title="${esc(t("Delete", "حذف"))}">${frappe.utils.icon("delete", "sm")}</button>
				</div>`);
		});
	}

	function open_chat($root, name) {
		frappe
			.xcall(`${API}.get_chat`, { chat: name })
			.then((chat) => {
				state.chat = chat.name;
				state.history = chat.messages.map((m) => ({ role: m.role, content: m.content }));
				state.items = chat.messages.map((m) => ({ role: m.role, text: m.content }));
				state.list_open = false;
				$root.find(".imed-assistant-chatlist").prop("hidden", true);
				$root.find(".imed-assistant-panel__chat-title").text(chat.title || "");
				render($root);
			})
			.catch(() => frappe.show_alert({ message: t("Could not open the chat.", "ما قدرتش أفتح المحادثة."), indicator: "orange" }));
	}

	function delete_chat($root, name) {
		frappe.confirm(t("Delete this chat?", "تحذف المحادثة دي؟"), () => {
			frappe.xcall(`${API}.delete_chat`, { chat: name }).then(() => {
				if (state.chat === name) start_new_chat($root);
				load_chats($root);
			});
		});
	}

	function rename_chat($root, name) {
		const current = (state.chats.find((c) => c.name === name) || {}).title || "";
		frappe.prompt({ fieldname: "title", fieldtype: "Data", label: t("Title", "العنوان"), default: current, reqd: 1 }, (v) => {
			frappe.xcall(`${API}.rename_chat`, { chat: name, title: v.title }).then(() => {
				if (state.chat === name) $root.find(".imed-assistant-panel__chat-title").text(v.title);
				load_chats($root);
			});
		}, t("Rename the chat", "إعادة تسمية المحادثة"));
	}

	// A recording is written out into the message box (api.transcribe), for the user to read, correct and send,
	// as in a chat app's dictation (owner, 2 Nov 2026); nothing is sent until they press Send.
	function transcribe_to_input($root, blob, mime) {
		const $input = $root.find("textarea");
		const $mic = $root.find(".imed-assistant-mic");
		const placeholder = $input.attr("placeholder");
		$mic.prop("disabled", true).addClass("is-transcribing");
		$input.prop("disabled", true).attr("placeholder", t("Writing out what you said…", "بكتب كلامك…"));
		const reader = new FileReader();
		reader.onloadend = () => {
			const audio = String(reader.result).split(",")[1] || "";
			frappe
				.xcall(`${API}.transcribe`, { audio, audio_type: mime })
				.then((r) => {
					const text = ((r && r.text) || "").trim();
					if (!text) {
						frappe.show_alert({ message: (r && r.message) || t("Nothing was heard. Try again.", "ما سمعتش كلام واضح، جرّب تاني."), indicator: "orange" });
						return;
					}
					const before = $input.val().trim();
					$input.val(before ? `${before} ${text}` : text);
				})
				.catch(() => frappe.show_alert({ message: t("The recording could not be written out.", "ما قدرتش أكتب التسجيل."), indicator: "orange" }))
				.finally(() => {
					$mic.prop("disabled", state.busy).removeClass("is-transcribing");
					$input.prop("disabled", false).attr("placeholder", placeholder);
					autosize($input);
					$input.trigger("focus");
					const end = $input.val().length;
					$input[0].setSelectionRange(end, end);
				});
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
				if (state.chat && !$root.find(".imed-assistant-panel__chat-title").text()) {
					const first = (state.history.find((m) => m.role === "user") || {}).content || "";
					$root.find(".imed-assistant-panel__chat-title").text(first.slice(0, 60));
				}
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
		// A microphone unplugged mid-recording ends its track: stop there, or the timer would run on.
		stream.getAudioTracks().forEach((track) => track.addEventListener("ended", () => stop_recording($root)));
		recorder.onerror = () => stop_recording($root, true);
		recorder.onstop = () => {
			stream.getTracks().forEach((track) => track.stop());
			const type = (recorder.mimeType || mime || "audio/webm").split(";")[0];
			const blob = new Blob(state.chunks, { type });
			state.recorder = null;
			set_recording_ui($root, false);
			if (!state.cancelled && blob.size) transcribe_to_input($root, blob, type);
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
		clearInterval(state.record_timer);
		if (!state.recorder || state.recorder.state === "inactive") return;
		state.cancelled = !!cancel;
		state.recorder.stop();
	}

	window.addEventListener("pagehide", () => state.audio_urls.forEach((url) => URL.revokeObjectURL(url)));

	function set_recording_ui($root, on) {
		$root.toggleClass("is-recording", on);
		$root.find(".imed-assistant-recording").prop("hidden", !on);
		$root
			.find(".imed-assistant-mic")
			.attr("aria-pressed", on ? "true" : "false")
			.attr("aria-label", on ? t("Stop and write it out", "وقّف واكتب الكلام") : t("Speak your question", "قول سؤالك"));
		$root.find(".imed-assistant-recording__time").text("0:00");
	}

	// ------------------------------------------------------------------ hook
	// On every page, not only the home screen (owner's request of 21 Oct 2026: the owner opens on her dashboard,
	// with the assistant). The button and the panel are fixed to the window, so they sit in the body once and stay
	// there from page to page, the conversation with them.
	function attach() {
		get_status().then((status) => {
			if (!status || !status.allowed) return;
			if (!$("body > .imed-assistant").length) mount($("body"));
		});
	}

	$(() => attach());
})();
