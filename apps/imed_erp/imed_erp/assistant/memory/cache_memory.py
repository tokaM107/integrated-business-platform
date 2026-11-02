# The memory of a conversation that is not a saved chat (an API caller sending the whole conversation): this user's
# last turns in the site's cache, for a while. Keyed by user: never shared between users.

from __future__ import annotations

import frappe

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.interfaces import Completer

TTL_SECONDS = 30 * 60
TURNS = 4


class CacheMemory:
	@staticmethod
	def key(user: str) -> str:
		return f"imed_assistant_memory:{user}"

	def turns(self, context: RequestContext) -> list[dict]:
		return frappe.cache.get_value(self.key(context.user)) or []

	def context_text(self, context: RequestContext) -> str:
		turns = self.turns(context)
		if not turns:
			return "(no earlier turn)"
		return "\n".join(f"Q: {t['q']}\nA: {t['a']}\nFacts: {t['facts']}" for t in turns)

	def record(self, context: RequestContext, question: str, answer: str, facts: str) -> None:
		turns = self.turns(context)
		turns.append({"q": question[:400], "a": answer[:600], "facts": facts[:1200]})
		frappe.cache.set_value(self.key(context.user), turns[-TURNS:], expires_in_sec=TTL_SECONDS)

	def fold(self, context: RequestContext, complete: Completer) -> bool:
		return False  # nothing to fold: the cache keeps only the last turns

	def forget(self, user: str) -> None:
		frappe.cache.delete_value(self.key(user))
