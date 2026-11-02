# The model providers' base: `reply` runs the assistant's flow (core.orchestration) with the provider's single
# model call; a provider implements `complete` (text in, text out; JSON out with a schema) and, if it can,
# `transcribe`. AI-02: the assistant only answers; the reads are the tools', as the asking user; no provider writes.

from __future__ import annotations

import frappe

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.interfaces import JsonSchema


class AssistantProvider:
	name = "base"
	connected = False
	supports_voice = False

	def complete(self, system: str, prompt: str, json_schema: JsonSchema | None = None) -> str:
		raise NotImplementedError

	def transcribe(self, audio: bytes, mime_type: str, context: RequestContext) -> str | None:
		return None

	def reply(self, question: str, context: RequestContext) -> tuple[str, str]:
		"""(answer, facts) to `question` for `context`, through the planner, executor and synthesizer."""
		from imed_erp.assistant.registry.container import build_orchestrator

		return build_orchestrator(self, context).answer(question, context)

	@staticmethod
	def api_key() -> str:
		return frappe.conf.get("imed_assistant_api_key") or ""

	@staticmethod
	def model_setting(default: str) -> str:
		return frappe.conf.get("imed_assistant_model") or default


class OfflineProvider(AssistantProvider):
	"""Until a model is configured: says so, so the window, voice and permissions can be used and tested."""

	name = "offline"

	def reply(self, question: str, context: RequestContext) -> tuple[str, str]:
		if context.is_arabic:
			return (
				"أنا المساعد الذكي، لسه ما اتربطتش بنموذج ذكاء اصطناعي، فمش هقدر أجاوب دلوقتي.\n"
				f"رسالتك وصلت: «{question}»"
			), ""
		return f"I'm the assistant. I'm not connected to an AI model yet, so I can't answer for now.\nYour message arrived: \"{question}\"", ""
