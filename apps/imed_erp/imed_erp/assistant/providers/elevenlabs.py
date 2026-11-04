# The assistant's voice, ElevenLabs only (owner, 4 Nov 2026: no Gemini): answers read aloud by the owner's voice
# I3u6waC588j43py1kDN2 ("Fatima - Expressive Egyptian"), and recordings written out by Scribe (scribe_v2). Claude
# answers. A library voice needs a paid ElevenLabs plan (the API answers 402 paid_plan_required on the free one):
# until then a voice of the account (IMED_ELEVENLABS_FALLBACK_VOICE_ID, Sarah by default) reads instead.
#
#   ELEVENLABS_API_KEY        the key (environment, Coolify), or site config imed_elevenlabs_api_key
#   IMED_ELEVENLABS_VOICE_ID  another voice (or site config imed_elevenlabs_voice_id); the voice must be in the
#                             key's account ("My Voices" / added from the Voice Library) for the API to use it
#   IMED_ELEVENLABS_MODEL     another model (or imed_elevenlabs_model); eleven_multilingual_v2 speaks Arabic
#   IMED_ELEVENLABS_FALLBACK_VOICE_ID   the voice used while the chosen one is refused for the plan

from __future__ import annotations

import os

import frappe

from imed_erp.assistant.core.exceptions import ModelUnavailable
from imed_erp.assistant.providers.base import AssistantProvider

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
STT_API = "https://api.elevenlabs.io/v1/speech-to-text"
STT_MODEL = "scribe_v2"  # tried 4 Nov 2026: an Egyptian sentence written back word for word in 1.1 s
DEFAULT_VOICE = "I3u6waC588j43py1kDN2"
FALLBACK_VOICE = "EXAVITQu4vr4xnSDxMaL"  # Sarah, a voice every account has (the free plan included)
DEFAULT_MODEL = "eleven_multilingual_v2"
OUTPUT = "mp3_44100_128"


def elevenlabs_key() -> str:
	return AssistantProvider.secret("imed_elevenlabs_api_key", ("ELEVENLABS_API_KEY", "XI_API_KEY"), ("\0",))


def setting(conf_name: str, env_name: str, default: str) -> str:
	return frappe.conf.get(conf_name) or os.environ.get(env_name) or default


class ElevenLabsVoice(AssistantProvider):
	name = "elevenlabs"
	supports_voice = True

	def __init__(self):
		self.key = elevenlabs_key()
		self.voice = setting("imed_elevenlabs_voice_id", "IMED_ELEVENLABS_VOICE_ID", DEFAULT_VOICE)
		self.model = setting("imed_elevenlabs_model", "IMED_ELEVENLABS_MODEL", DEFAULT_MODEL)
		self.fallback_voice = setting("imed_elevenlabs_fallback_voice_id", "IMED_ELEVENLABS_FALLBACK_VOICE_ID", FALLBACK_VOICE)
		self.connected = bool(self.key)

	def transcribe(self, audio: bytes, mime_type: str, context) -> str | None:
		"""What was said, as text (Scribe), for the user to read, correct and send."""
		import requests

		if not self.key:
			return None
		extension = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav"}.get(mime_type, "webm")
		try:
			response = requests.post(
				STT_API,
				headers={"xi-api-key": self.key},
				data={"model_id": STT_MODEL, "tag_audio_events": "false"},
				files={"file": (f"question.{extension}", audio, mime_type or "application/octet-stream")},
				timeout=60,
			)
		except requests.RequestException as e:
			raise ModelUnavailable("overload", f"ElevenLabs did not answer: {type(e).__name__}") from e
		if response.status_code == 429:
			raise ModelUnavailable("quota", response.text[:200])
		if response.status_code >= 500:
			raise ModelUnavailable("overload", response.text[:200])
		if response.status_code != 200:
			frappe.log_error(title="ElevenLabs transcription refused", message=f"{response.status_code} {response.text[:500]}")
			raise frappe.ValidationError("ElevenLabs refused the recording")
		return (response.json().get("text") or "").strip()

	def speak(self, text: str, context) -> tuple[bytes, str] | None:
		if not self.key:
			return None
		response = self.say(text, self.voice)
		if response.status_code == 402 and self.fallback_voice and self.fallback_voice != self.voice:
			# The chosen voice is refused for the plan (a library voice on the free plan): the account's own voice.
			response = self.say(text, self.fallback_voice)
		if response.status_code == 429:
			raise ModelUnavailable("quota", response.text[:200])
		if response.status_code >= 500:
			raise ModelUnavailable("overload", response.text[:200])
		if response.status_code != 200:
			# 401 a wrong key, 402 a plan without this voice or no characters left, 404 a voice not in the account.
			frappe.log_error(title="ElevenLabs speech refused", message=f"{response.status_code} {response.text[:500]}")
			return None
		return response.content, "audio/mpeg"

	def say(self, text: str, voice: str):
		import requests

		try:
			return requests.post(
				API.format(voice=voice),
				params={"output_format": OUTPUT},
				headers={"xi-api-key": self.key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
				json={"text": text, "model_id": self.model},
				timeout=60,
			)
		except requests.RequestException as e:
			raise ModelUnavailable("overload", f"ElevenLabs did not answer: {type(e).__name__}") from e
