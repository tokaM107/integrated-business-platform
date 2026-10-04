# Endpoints for the assistant chat window (public/js/imed_assistant.js).
#
# The conversation lives in the browser and is sent with every message, so the server keeps no state.
# The provider that answers is chosen in providers.py.

import base64
import binascii
import json

import frappe
from frappe import _

from imed_erp.assistant.providers import get_provider

# Requirements section 3.2 / open question 22: the AI assistant is for the owner only (Super Admin).
# System Manager is included so the developers can test it; branch managers, the accountant and HR
# do not see it.
ALLOWED_ROLES = {"Super Admin", "System Manager"}

MAX_MESSAGES = 30  # conversation turns sent to the provider
MAX_MESSAGE_CHARS = 4000
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # about 10 minutes of compressed speech
AUDIO_TYPES = ("audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav")


def can_use() -> bool:
	return bool(ALLOWED_ROLES & set(frappe.get_roles()))


def check_access():
	if not can_use():
		frappe.throw(_("You are not allowed to use the assistant."), frappe.PermissionError)


def user_context() -> dict:
	return {
		"user": frappe.session.user,
		"full_name": frappe.utils.get_fullname(frappe.session.user),
		"lang": frappe.local.lang or "en",
		"company": frappe.defaults.get_user_default("Company"),
	}


@frappe.whitelist()
def get_status():
	"""What the chat window needs before it shows itself."""
	if not can_use():
		return {"allowed": False}
	provider = get_provider()
	return {
		"allowed": True,
		"provider": provider.name,
		"connected": provider.connected,
		"voice": provider.supports_voice,
	}


def clean_messages(messages) -> list[dict]:
	if isinstance(messages, str):
		messages = json.loads(messages or "[]")
	cleaned = []
	for m in messages[-MAX_MESSAGES:]:
		role, content = m.get("role"), (m.get("content") or "").strip()
		if role not in ("user", "assistant") or not content:
			continue
		cleaned.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
	return cleaned


def decode_audio(audio: str, audio_type: str) -> bytes:
	mime = (audio_type or "").split(";")[0].strip()
	if mime not in AUDIO_TYPES:
		frappe.throw(_("Unsupported audio format: {0}").format(mime or "?"))
	try:
		data = base64.b64decode(audio, validate=True)
	except (binascii.Error, ValueError):
		frappe.throw(_("The voice message could not be read."))
	if len(data) > MAX_AUDIO_BYTES:
		frappe.throw(_("The voice message is too long."))
	return data


@frappe.whitelist(methods=["POST"])
def send_message(messages=None, audio=None, audio_type=None):
	"""Answer the last user message. With `audio` (base64) the last user turn is a voice message: it is
	transcribed first, if the provider can, and the transcript becomes that turn's text.

	Returns {"reply": str, "transcript": str | None}.
	"""
	check_access()
	provider = get_provider()
	context = user_context()
	conversation = clean_messages(messages)

	transcript = None
	if audio:
		data = decode_audio(audio, audio_type)
		transcript = provider.transcribe(data, audio_type, context)
		voice_turn = transcript or (
			"[رسالة صوتية]" if context["lang"].startswith("ar") else "[voice message]"
		)
		conversation.append({"role": "user", "content": voice_turn})

	if not conversation or conversation[-1]["role"] != "user":
		frappe.throw(_("Write a message first."))

	try:
		reply = provider.reply(conversation, context)
	except Exception:
		frappe.log_error(title=f"Assistant provider {provider.name} failed")
		reply = (
			"حصلت مشكلة وأنا بجهّز الرد، جرّب تاني بعد شوية."
			if context["lang"].startswith("ar")
			else "Something went wrong while preparing the answer. Please try again shortly."
		)
	return {"reply": reply, "transcript": transcript}
