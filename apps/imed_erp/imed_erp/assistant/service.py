# The application service: one question answered for one request. Composes the model (providers/), the tools of
# the request (registry/, scoped to the user), and the conversation's memory (memory/), and runs the flow
# (core/orchestration.py). This is the only place they meet.

from __future__ import annotations

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.interfaces import ConversationMemory, ModelProvider
from imed_erp.assistant.core.orchestration import Orchestrator
from imed_erp.assistant.memory.chat_memory import ChatMemory
from imed_erp.assistant.memory.request_memory import RequestMemory
from imed_erp.assistant.registry.businesses import discover
from imed_erp.assistant.registry.tools import ToolRegistry


def memory_for(context: RequestContext, earlier: list[dict]) -> ConversationMemory:
	return ChatMemory() if context.chat else RequestMemory(earlier)


def answer(provider: ModelProvider, question: str, context: RequestContext, earlier: list[dict] | None = None) -> tuple[str, str]:
	"""(answer, facts). Raises ModelUnavailable when the model cannot be reached."""
	tools = ToolRegistry(discover(context), context)
	return Orchestrator(provider.complete, tools, memory_for(context, earlier or [])).answer(question, context)
