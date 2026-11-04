# Reading answers aloud with an ElevenLabs voice (owner's choice of 4 Nov 2026: voice I3u6waC588j43py1kDN2). Speech
# only: ElevenLabs neither answers nor writes out recordings (Claude answers, Gemini writes out dictation).
#
#   ELEVENLABS_API_KEY        the key (environment, Coolify), or site config imed_elevenlabs_api_key
#   IMED_ELEVENLABS_VOICE_ID  another voice (or site config imed_elevenlabs_voice_id); the voice must be in the
#                             key's account ("My Voices" / added from the Voice Library) for the API to use it
#   IMED_ELEVENLABS_MODEL     another model (or imed_elevenlabs_model); eleven_multilingual_v2 speaks Arabic

from __future__ import annotations

import os

import frappe

from imed_erp.assistant.core.exceptions import ModelUnavailable
from imed_erp.assistant.providers.base import AssistantProvider

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
DEFAULT_VOICE = "I3u6waC588j43py1kDN2"
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
		self.connected = bool(self.key)

	def speak(self, text: str, context) -> tuple[bytes, str] | None:
		import requests

		if not self.key:
			return None
		try:
			response = requests.post(
				API.format(voice=self.voice),
				params={"output_format": OUTPUT},
				headers={"xi-api-key": self.key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
				json={"text": text, "model_id": self.model},
				timeout=60,
			)
		except requests.RequestException as e:
			raise ModelUnavailable("overload", f"ElevenLabs did not answer: {type(e).__name__}") from e
		if response.status_code == 429:
			raise ModelUnavailable("quota", response.text[:200])
		if response.status_code >= 500:
			raise ModelUnavailable("overload", response.text[:200])
		if response.status_code != 200:
			# 401 a wrong key, 402/quota_exceeded no characters left, 404/voice_not_found a voice not in the account.
			frappe.log_error(title="ElevenLabs speech refused", message=f"{response.status_code} {response.text[:500]}")
			return None
		return response.content, "audio/mpeg"
