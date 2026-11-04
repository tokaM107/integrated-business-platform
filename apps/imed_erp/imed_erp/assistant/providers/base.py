# The model port's base. A provider is only a model: `complete` (text in, text out; JSON out with a schema) and, if
# it can, `transcribe`. It knows nothing of tools, memory or the flow (service.py runs those).

from __future__ import annotations

import os

import frappe

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.exceptions import ModelUnavailable
from imed_erp.assistant.core.interfaces import JsonSchema


class AssistantProvider:
	name = "base"
	connected = False
	supports_voice = False

	def complete(self, system: str, prompt: str, json_schema: JsonSchema | None = None) -> str:
		raise NotImplementedError

	def transcribe(self, audio: bytes, mime_type: str, context: RequestContext) -> str | None:
		return None

	def speak(self, text: str, context: RequestContext) -> tuple[bytes, str] | None:
		"""(audio, its mime type) for an answer read aloud, or None when the provider has no voice."""
		return None

	@staticmethod
	def api_key() -> str:
		return frappe.conf.get("imed_assistant_api_key") or ""

	@staticmethod
	def secret(own_setting: str, env_names: tuple[str, ...], shared_prefixes: tuple[str, ...]) -> str:
		"""A provider's key: its own site-config setting, else the server's environment (Coolify), else the shared
		`imed_assistant_api_key` when it is this provider's kind of key (by its prefix). Never logged."""
		value = frappe.conf.get(own_setting) or next((os.environ[n] for n in env_names if os.environ.get(n)), "")
		if value:
			return value.strip()
		shared = (frappe.conf.get("imed_assistant_api_key") or "").strip()
		return shared if shared.startswith(shared_prefixes) else ""

	@staticmethod
	def model_setting(default: str) -> str:
		return frappe.conf.get("imed_assistant_model") or default


class OfflineProvider(AssistantProvider):
	"""No model configured: every call says so (the API answers that the assistant is not connected)."""

	name = "offline"

	def complete(self, system: str, prompt: str, json_schema: JsonSchema | None = None) -> str:
		raise ModelUnavailable("not_configured")
