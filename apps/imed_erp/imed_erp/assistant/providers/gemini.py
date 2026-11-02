# Gemini through google-genai. Site config: imed_assistant_provider = gemini, imed_assistant_api_key = AIza...,
# imed_assistant_model (optional; the default below). Tried on 1 Nov 2026: gemini-3.1-pro-preview is over a free
# key's quota, gemini-3.8-flash ran minutes under demand, gemini-3.5-flash answered correctly in 14 s.

from __future__ import annotations

from imed_erp.assistant.core.exceptions import ModelUnavailable
from imed_erp.assistant.core.interfaces import JsonSchema
from imed_erp.assistant.providers.base import AssistantProvider

DEFAULT_MODEL = "gemini-3.5-flash"


class GeminiProvider(AssistantProvider):
	name = "gemini"

	def __init__(self):
		self.key = self.api_key()
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
