# Claude through the Anthropic SDK (owner's choice of 2 Nov 2026: Claude Sonnet 4.6 answers). The key: site config
# imed_assistant_anthropic_key, else the environment's ANTHROPIC_API_KEY (Coolify), else imed_assistant_api_key when
# it is an Anthropic key. The model: imed_assistant_claude_model or IMED_ASSISTANT_CLAUDE_MODEL, else the default
# below (its own setting: imed_assistant_model may still name a Gemini model). Claude neither hears nor speaks: the
# voice stays with Gemini when a Gemini key is set (providers/__init__.py, voice_provider).

from __future__ import annotations

import os

import frappe

from imed_erp.assistant.core.exceptions import ModelUnavailable
from imed_erp.assistant.core.interfaces import JsonSchema
from imed_erp.assistant.providers.base import AssistantProvider

DEFAULT_MODEL = "claude-sonnet-4-6"


def strict(schema):
	"""The planner's schema as Claude's structured output requires it: every object closed (additionalProperties
	false; the API answers 400 otherwise). A copy; Gemini keeps the schema as it is."""
	if isinstance(schema, dict):
		out = {k: strict(v) for k, v in schema.items()}
		if out.get("type") == "object":
			out["additionalProperties"] = False
		return out
	if isinstance(schema, list):
		return [strict(v) for v in schema]
	return schema


def anthropic_key() -> str:
	return AssistantProvider.secret("imed_assistant_anthropic_key", ("ANTHROPIC_API_KEY",), ("sk-ant-",))


class ClaudeProvider(AssistantProvider):
	name = "claude"

	def __init__(self):
		self.key = anthropic_key()
		self.model = frappe.conf.get("imed_assistant_claude_model") or os.environ.get("IMED_ASSISTANT_CLAUDE_MODEL") or DEFAULT_MODEL
		self.connected = bool(self.key)
		self._client = None

	def client(self):
		import anthropic

		if not self.key:
			raise ModelUnavailable("not_configured", "no Anthropic API key")
		if self._client is None:
			self._client = anthropic.Anthropic(api_key=self.key, max_retries=2, timeout=120.0)
		return self._client

	def complete(self, system: str, prompt: str, json_schema: JsonSchema | None = None) -> str:
		import anthropic

		# The planner's JSON at low effort (it only lists reads); the answer at the model's default.
		kwargs = {"output_config": {"effort": "low", "format": {"type": "json_schema", "schema": strict(json_schema)}}} if json_schema else {}
		try:
			response = self.client().messages.create(
				model=self.model, max_tokens=4000, system=system, messages=[{"role": "user", "content": prompt}], **kwargs
			)
		except anthropic.RateLimitError as e:
			raise ModelUnavailable("quota", str(e)[:200]) from e
		except anthropic.APIStatusError as e:
			if e.status_code >= 500:
				raise ModelUnavailable("overload", str(e)[:200]) from e
			raise
		except anthropic.APIConnectionError as e:
			raise ModelUnavailable("overload", str(e)[:200]) from e
		if response.stop_reason == "refusal":
			raise ModelUnavailable("refused", "the model declined the request")
		return "".join(b.text for b in response.content if b.type == "text")
