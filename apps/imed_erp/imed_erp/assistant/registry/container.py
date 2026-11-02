# The composition root: where the model, the memory and the tools of a request are chosen and wired together.
# Everything else takes them as arguments. Site config (`imed_assistant_provider`, `imed_assistant_api_key`,
# `imed_assistant_model`) is application configuration, read here and nowhere else.

from __future__ import annotations

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.interfaces import ConversationMemory, ModelProvider
from imed_erp.assistant.core.orchestration import Orchestrator
from imed_erp.assistant.registry.businesses import discover
from imed_erp.assistant.registry.tools import ToolRegistry


def memory_for(context: RequestContext) -> ConversationMemory:
	if context.chat:
		from imed_erp.assistant.memory.chat_memory import ChatMemory

		return ChatMemory()
	from imed_erp.assistant.memory.cache_memory import CacheMemory

	return CacheMemory()


def build_orchestrator(provider: ModelProvider, context: RequestContext, memory: ConversationMemory | None = None) -> Orchestrator:
	return Orchestrator(provider, ToolRegistry(discover(context), context), memory or memory_for(context))
