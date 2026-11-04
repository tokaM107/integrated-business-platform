# Gemini through google-genai. Site config: imed_assistant_provider = gemini, imed_assistant_api_key = AIza...,
# imed_assistant_model (optional; the default below). Tried on 1 Nov 2026: gemini-3.1-pro-preview is over a free
# key's quota, gemini-3.8-flash ran minutes under demand, gemini-3.5-flash answered correctly in 14 s.

from __future__ import annotations

import struct

import frappe

from imed_erp.assistant.core.exceptions import ModelUnavailable
from imed_erp.assistant.core.interfaces import JsonSchema
from imed_erp.assistant.providers.base import AssistantProvider

DEFAULT_MODEL = "gemini-3.5-flash"
# Reading aloud (2 Nov 2026: the browser's own voice read Arabic letter by letter, in no dialect): Google's speech
# model with one of its Egyptian Arabic voices (GET /v1beta/voices, language_code ar-EG). Site config
# imed_assistant_tts_model and imed_assistant_voice change them.
DEFAULT_TTS_MODEL = "gemini-3.8-flash-tts"
DEFAULT_VOICE = "ar-eg-techagent-6"  # female, "natural and clear"
# Dictation: gemini-3.5-flash wrote an Egyptian recording out word for word, dialect kept (2 Nov 2026). Its own
# setting (imed_assistant_stt_model), since a free key's daily quota is per model.
DEFAULT_STT_MODEL = "gemini-3.5-flash"
TRANSCRIBE = (
	"اكتب الكلام اللي في التسجيل ده بالظبط زي ما اتقال، بنفس اللغة واللهجة (العامية المصرية تفضل عامية)، "
	"من غير ترجمة ولا تصحيح ولا تلخيص ولا أي كلمة زيادة. الأرقام بالأرقام. لو مفيش كلام مفهوم رجّع نص فاضي."
)


def gemini_key() -> str:
	"""Site config imed_assistant_gemini_key, else GEMINI_API_KEY / GOOGLE_API_KEY in the environment, else
	imed_assistant_api_key unless that is an Anthropic key."""
	key = AssistantProvider.secret("imed_assistant_gemini_key", ("GEMINI_API_KEY", "GOOGLE_API_KEY"), ("",))
	return "" if key.startswith("sk-ant-") else key


def as_wav(pcm: bytes, rate: int = 24000) -> bytes:
	"""16-bit mono PCM (what the speech model sends as audio/L16) with a RIFF header, so a browser plays it."""
	return b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm


def rate_of(mime: str) -> int:
	for part in (mime or "").replace(" ", "").split(";"):
		if part.lower().startswith("rate="):
			return int(part.split("=", 1)[1])
	return 24000


class GeminiProvider(AssistantProvider):
	name = "gemini"
	supports_voice = True

	def __init__(self):
		self.key = gemini_key()
		self.model = self.model_setting(DEFAULT_MODEL)
		self.connected = bool(self.key)
		self._client = None

	def client(self):
		from google import genai

		if not self.key:
			raise ModelUnavailable("not_configured", "no API key in the site config")
		if self._client is None:  # one HTTP session per provider instance (a client per call closed it mid-flow)
			self._client = genai.Client(api_key=self.key)
		return self._client

	def complete(self, system: str, prompt: str, json_schema: JsonSchema | None = None) -> str:
		from google.genai import types

		config = types.GenerateContentConfig(system_instruction=system, temperature=0.1, max_output_tokens=4000)
		if json_schema:
			config.response_mime_type = "application/json"
			config.response_schema = json_schema
		try:
			response = self.client().models.generate_content(model=self.model, contents=prompt, config=config)
		except Exception as e:
			code = getattr(e, "code", None) or getattr(e, "status_code", None)
			if code == 429:
				raise ModelUnavailable("quota", str(e)[:200]) from e
			if code == 503:
				raise ModelUnavailable("overload", str(e)[:200]) from e
			raise
		return response.text or ""

	@staticmethod
	def unavailable(e: Exception):
		code = getattr(e, "code", None) or getattr(e, "status_code", None)
		if code == 429:
			return ModelUnavailable("quota", str(e)[:200])
		if code == 503:
			return ModelUnavailable("overload", str(e)[:200])
		return None

	def transcribe(self, audio: bytes, mime_type: str, context) -> str | None:
		"""What was said, as text, for the user to read and send (like a chat app's dictation)."""
		from google.genai import types

		try:
			response = self.client().models.generate_content(
				# Its own setting: a free key's daily quota is per model, so dictation need not use up the answers'.
				model=frappe.conf.get("imed_assistant_stt_model") or DEFAULT_STT_MODEL,
				contents=[types.Part.from_bytes(data=audio, mime_type=mime_type), TRANSCRIBE],
				config=types.GenerateContentConfig(temperature=0, max_output_tokens=2000),
			)
		except Exception as e:
			raise (self.unavailable(e) or e) from e
		return (response.text or "").strip()

	def speak(self, text: str, context) -> tuple[bytes, str] | None:
		from google.genai import types

		voice = frappe.conf.get("imed_assistant_voice") or DEFAULT_VOICE
		config = types.GenerateContentConfig(
			response_modalities=["AUDIO"],
			speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
		)
		try:
			response = self.client().models.generate_content(
				model=frappe.conf.get("imed_assistant_tts_model") or DEFAULT_TTS_MODEL, contents=text, config=config
			)
		except Exception as e:
			raise (self.unavailable(e) or e) from e
		for part in (response.candidates[0].content.parts if response.candidates else []):
			blob = getattr(part, "inline_data", None)
			if blob and blob.data:
				mime = (blob.mime_type or "").lower()
				if "wav" in mime:
					return blob.data, "audio/wav"
				if "l16" in mime or "pcm" in mime:
					return as_wav(blob.data, rate_of(mime)), "audio/wav"
				return blob.data, blob.mime_type
		return None
