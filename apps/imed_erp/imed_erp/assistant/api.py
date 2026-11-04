# The chat window's endpoints (public/js/imed_assistant.js): thin. Who may use the assistant, the rate limit, the
# message hygiene, the saved chats' CRUD, and the one call that answers (service.py). Everything else lives in
# core/, registry/, businesses/, tools/, memory/ and providers/.

from __future__ import annotations

import base64
import binascii
import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from imed_erp.assistant import service
from imed_erp.assistant.core.context import RequestContext, build_context
from imed_erp.assistant.core.exceptions import ModelUnavailable
from imed_erp.assistant.memory.chat_memory import ChatStore
from imed_erp.assistant.providers import get_provider, voice_provider

# Requirements section 3.2 / open question 22: the AI assistant is for the owner only (Super Admin).
# System Manager is included so the developers can test it; branch managers, the accountant and HR do not see it.
ALLOWED_ROLES = {"Super Admin", "System Manager"}

MAX_MESSAGES = 30
MAX_MESSAGE_CHARS = 4000
MESSAGES_PER_MINUTE = 20
MAX_AUDIO_BYTES = 10 * 1024 * 1024
AUDIO_TYPES = ("audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav")


def can_use() -> bool:
	return bool(ALLOWED_ROLES & set(frappe.get_roles()))


def check_access() -> None:
	if not can_use():
		frappe.throw(_("You are not allowed to use the assistant."), frappe.PermissionError)


@frappe.whitelist()
def get_status():
	if not can_use():
		return {"allowed": False}
	provider = get_provider()
	return {"allowed": True, "provider": provider.name, "connected": provider.connected, "voice": voice_provider(provider).supports_voice}


def clean_messages(messages) -> list[dict]:
	if isinstance(messages, str):
		messages = json.loads(messages or "[]")
	cleaned = []
	for m in messages[-MAX_MESSAGES:]:
		role, content = m.get("role"), (m.get("content") or "").strip()
		if role in ("user", "assistant") and content:
			cleaned.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
	return cleaned


def decode_audio(audio: str, audio_type: str) -> bytes:
	mime = (audio_type or "").split(";")[0].strip()
	if mime not in AUDIO_TYPES:
		frappe.throw(_("Unsupported audio format: {0}").format(mime or "?"))
	# SEC-11: the size is checked on the text sent, before decoding it: 4 characters of base64 carry 3 bytes.
	if len(audio or "") > (MAX_AUDIO_BYTES + 2) // 3 * 4:
		frappe.throw(_("The voice message is too long."))
	try:
		data = base64.b64decode(audio, validate=True)
	except (binascii.Error, ValueError):
		frappe.throw(_("The voice message could not be read."))
	if len(data) > MAX_AUDIO_BYTES:
		frappe.throw(_("The voice message is too long."))
	return data


# ---------------- saved chats ----------------


@frappe.whitelist()
def list_chats():
	check_access()
	return ChatStore.list()


@frappe.whitelist(methods=["POST"])
def new_chat(title=None):
	check_access()
	return ChatStore.new(title)


@frappe.whitelist()
def get_chat(chat):
	check_access()
	doc = ChatStore.own(chat)
	return {"name": doc.name, "title": doc.title, "messages": [{"role": m.role, "content": m.content} for m in ChatStore.messages(chat)]}


@frappe.whitelist(methods=["POST"])
def rename_chat(chat, title):
	check_access()
	return ChatStore.rename(chat, title)


@frappe.whitelist(methods=["POST"])
def delete_chat(chat):
	check_access()
	ChatStore.delete(chat)
	return True


# ---------------- answering ----------------


def unavailable_text(error: ModelUnavailable, context: RequestContext) -> str:
	ar = context.is_arabic
	if error.reason == "quota":
		return "حد الاستخدام بتاع مفتاح الموديل خلص مؤقتًا. جرّب بعد دقيقة، أو زوّد الحد من حساب المفتاح." if ar else "The model key's usage limit is reached for now. Try again in a minute, or raise the key's limit."
	if error.reason == "overload":
		return "الموديل مزدحم دلوقتي. جرّب بعد شوية." if ar else "The model is overloaded right now. Try again in a moment."
	if error.reason == "refused":
		return "الموديل رفض يجاوب على السؤال ده. جرّب تصيغه بشكل تاني." if ar else "The model declined to answer this one. Try asking it another way."
	return "المساعد غير مربوط بنموذج بعد." if ar else "The assistant is not connected to a model yet."


STREAM_EVENT = "imed_assistant_stream"
STREAM_EVERY_SECONDS = 0.12


def streamer(stream_id):
	"""The answer's pieces to the asking user's browser as they are written (realtime, to this user only), a few
	times a second; None without a stream id. The full answer is still returned by send_message, so a page whose
	realtime connection is down loses nothing (4 Nov 2026: the reply only showed once wholly written)."""
	if not stream_id:
		return None
	import time

	stream_id, user = str(stream_id)[:64], frappe.session.user
	state = {"pending": "", "at": 0.0}

	def flush():
		if state["pending"]:
			frappe.publish_realtime(STREAM_EVENT, {"id": stream_id, "text": state["pending"]}, user=user, after_commit=False)
			state["pending"] = ""
			state["at"] = time.monotonic()

	def on_text(piece):
		state["pending"] += piece
		if time.monotonic() - state["at"] >= STREAM_EVERY_SECONDS:
			flush()

	on_text.flush = flush
	return on_text


MAX_SPOKEN_CHARS = 1500


def speakable(text: str) -> str:
	"""An answer as it is said: no emoji or markdown marks for the voice to read out."""
	import re

	text = re.sub(r"[*_#`>|~]+", " ", text or "")
	text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", text)
	return re.sub(r"\s+", " ", text).strip()[:MAX_SPOKEN_CHARS]


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=MESSAGES_PER_MINUTE, seconds=60)
def transcribe(audio=None, audio_type=None):
	"""A recorded question as text, put in the message box for the user to read, correct and send (2 Nov 2026: the
	voice went straight to the model, unseen). Returns {"text": str}, or {"text": "", "message": why}."""
	check_access()
	provider = voice_provider(get_provider())
	context = build_context()
	data = decode_audio(audio, audio_type)
	try:
		text = provider.transcribe(data, (audio_type or "").split(";")[0].strip(), context)
	except ModelUnavailable as e:
		return {"text": "", "message": unavailable_text(e, context)}
	except Exception:
		frappe.log_error(title=f"Assistant transcription by {provider.name} failed")
		return {"text": "", "message": "ما قدرتش أكتب التسجيل، جرّب تاني أو اكتب سؤالك." if context.is_arabic else "The recording could not be written out. Try again or type your question."}
	if text is None:
		return {"text": "", "message": "المساعد مش متوصل بنموذج يكتب الصوت." if context.is_arabic else "No model is connected that can write out speech."}
	return {"text": text[:MAX_MESSAGE_CHARS]}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=MESSAGES_PER_MINUTE, seconds=60)
def speak(text=None):
	"""An answer read aloud by the model's Egyptian voice. Returns {"audio": base64, "mime": str}, or {"audio": None}
	when the provider has no voice (the browser reads it then)."""
	check_access()
	words = speakable(text)
	if not words:
		frappe.throw(_("Nothing to read."))
	provider = voice_provider(get_provider())
	context = build_context()
	try:
		spoken = provider.speak(words, context)
	except ModelUnavailable as e:
		return {"audio": None, "message": unavailable_text(e, context)}
	except Exception:
		frappe.log_error(title=f"Assistant speech by {provider.name} failed")
		return {"audio": None}
	if not spoken:
		return {"audio": None}
	data, mime = spoken
	return {"audio": base64.b64encode(data).decode(), "mime": mime}


@frappe.whitelist(methods=["POST"])
# SEC-11: each message may reach a paid model; a script calling in a loop is stopped (per address, per minute).
@rate_limit(limit=MESSAGES_PER_MINUTE, seconds=60)
def send_message(messages=None, audio=None, audio_type=None, chat=None, text=None, stream_id=None):
	"""Answer the user's message. In a saved chat (`chat` + `text`) the turn is stored and the chat's memory is the
	context; without a chat the browser sends the whole conversation (`messages`). With `audio` (base64) the user
	turn is a voice message, transcribed first if the provider can.

	Returns {"reply": str, "transcript": str | None, "chat": str | None}.
	"""
	check_access()
	provider = get_provider()
	context = build_context(chat=chat)
	if chat:
		ChatStore.check_company(chat, context.company)
		conversation = [{"role": "user", "content": (text or "").strip()[:MAX_MESSAGE_CHARS]}] if text else []
	else:
		conversation = clean_messages(messages)

	transcript = None
	if audio:
		transcript = provider.transcribe(decode_audio(audio, audio_type), audio_type, context)
		conversation.append({"role": "user", "content": transcript or ("[رسالة صوتية]" if context.is_arabic else "[voice message]")})

	if not conversation or conversation[-1]["role"] != "user":
		frappe.throw(_("Write a message first."))
	question = conversation[-1]["content"]

	earlier = conversation[:-1]
	if chat:
		ChatStore.append(chat, "user", question)
	try:
		on_text = streamer(stream_id)
		reply, _facts = service.answer(provider, question, context, earlier, on_text=on_text)
		if on_text:
			on_text.flush()
	except ModelUnavailable as e:
		reply = unavailable_text(e, context)
		if chat:
			ChatStore.append(chat, "assistant", reply)
	except Exception:
		frappe.log_error(title=f"Assistant provider {provider.name} failed")
		reply = "حصلت مشكلة وأنا بجهّز الرد، جرّب تاني بعد شوية." if context.is_arabic else "Something went wrong while preparing the answer. Please try again shortly."
		if chat:
			ChatStore.append(chat, "assistant", reply)
	return {"reply": reply, "transcript": transcript, "chat": chat}
