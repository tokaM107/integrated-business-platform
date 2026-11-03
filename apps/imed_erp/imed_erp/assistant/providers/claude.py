# Claude through the Anthropic SDK. Site config: imed_assistant_provider = claude, imed_assistant_api_key = sk-ant-...,
# imed_assistant_model (optional; the default below).

from __future__ import annotations

from imed_erp.assistant.core.exceptions import ModelUnavailable
from imed_erp.assistant.core.interfaces import JsonSchema
from imed_erp.assistant.providers.base import AssistantProvider

DEFAULT_MODEL = "claude-opus-5-5"


class ClaudeProvider(AssistantProvider):
	name = "claude"

	def __init__(self):
		self.key = self.api_key()
		self.model = self.model_setting(DEFAULT_MODEL)
		self.connected = bool(self.key)
		self._client = None

	def client(self):
		import anthropic

		if not self.key:
			raise ModelUnavailable("not_configured", "no API key in the site config")
		if self._client is None:
			self._client = anthropic.Anthropic(api_key=self.key, max_retries=2, timeout=120.0)
		return self._client

	def complete(self, system: str, prompt: str, json_schema: JsonSchema | None = None) -> str:
		import anthropic

		kwargs = {}
		if json_schema:
			kwargs["output_config"] = {"effort": "low", "format": {"type": "json_schema", "schema": json_schema}}
		try:
			response = self.client().messages.create(model=self.model, max_tokens=4000, system=system, messages=[{"role": "user", "content": prompt}], **kwargs)
		except anthropic.RateLimitError as e:
			raise ModelUnavailable("quota", str(e)[:200]) from e
		except anthropic.APIStatusError as e:
			if e.status_code >= 500:
				raise ModelUnavailable("overload", str(e)[:200]) from e
			raise
		return "".join(b.text for b in response.content if b.type == "text")
