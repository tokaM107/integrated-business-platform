# The memory of a conversation that is not saved (an API caller that sends the whole conversation with each
# message): exactly what the caller sent, the last WINDOW messages of it, held for this request only. Nothing is
# kept between requests, so two tabs, two callers or two conversations of the same user never see each other's turns.

from __future__ import annotations

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.interfaces import Completer
from imed_erp.assistant.memory.chat_memory import WINDOW


class RequestMemory:
	def __init__(self, earlier: list[dict]):
		self.earlier = earlier[-WINDOW:]

	def context_text(self, context: RequestContext) -> str:
		if not self.earlier:
			return "(a new conversation)"
		return "Last messages, as said:\n" + "\n".join(f"{m['role']}: {m['content']}" for m in self.earlier)

	def record(self, context: RequestContext, question: str, answer: str, facts: str) -> None:
		pass  # the caller keeps the conversation

	def fold(self, context: RequestContext, complete: Completer) -> bool:
		return False
