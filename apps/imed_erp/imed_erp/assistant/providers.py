# The one place where an AI model plugs into the assistant chat.
#
# To connect a model later:
#   1. Write a class that subclasses AssistantProvider and implements reply() (and transcribe() for
#      voice), e.g. in imed_erp/assistant/claude.py.
#   2. Point the site at it:
#        bench --site frontend set-config imed_assistant_provider "imed_erp.assistant.claude.ClaudeProvider"
# Nothing in the chat window or the API needs to change.
#
# Requirements (AI-02): in the first release the assistant only answers questions; it never creates,
# changes or deletes records. A provider must respect that: read data with the user's own permissions
# (frappe.get_list / frappe.get_doc as the current user), never with ignore_permissions.

import frappe


class AssistantProvider:
	"""Base class. `messages` is the whole conversation, oldest first:

	    [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]

	the same shape the Claude Messages API (and most model APIs) take, so it can be passed on as is.
	The last message is always the user's new one. `context` carries who is asking:
	{"user": ..., "full_name": ..., "lang": "ar" | "en", "company": ...}.
	"""

	name = "base"
	# False until a real model is behind the provider; the chat shows a "not connected" badge.
	connected = False
	# True if transcribe() can turn speech into text.
	supports_voice = False

	def reply(self, messages: list[dict], context: dict) -> str:
		raise NotImplementedError

	def transcribe(self, audio: bytes, mime_type: str, context: dict) -> str | None:
		"""Speech to text. Return None if the provider cannot transcribe."""
		return None


class OfflineProvider(AssistantProvider):
	"""Placeholder used until a model is connected: answers that the assistant is not connected yet,
	so the chat window, voice recording and permissions can be used and tested end to end."""

	name = "offline"

	def reply(self, messages, context):
		question = messages[-1]["content"].strip()
		if context.get("lang", "").startswith("ar"):
			return (
				"أنا المساعد الذكي لـ IMED، لسه ما اتربطتش بنموذج ذكاء اصطناعي، فمش هقدر أجاوب دلوقتي.\n"
				f"رسالتك وصلت: «{question}»\n"
				"أول ما يتربط المساعد هتقدر تسأل عن المبيعات والمخازن ومستحقات الأطباء."
			)
		return (
			"I'm the IMED assistant. I'm not connected to an AI model yet, so I can't answer for now.\n"
			f"Your message arrived: \"{question}\"\n"
			"Once I'm connected you'll be able to ask about sales, stock and doctors' balances."
		)


BUILT_IN = {"offline": OfflineProvider}


def get_provider() -> AssistantProvider:
	"""The provider named in site config `imed_assistant_provider` (a built-in name or a dotted path to a
	class), or the offline placeholder."""
	setting = frappe.conf.get("imed_assistant_provider") or "offline"
	cls = BUILT_IN.get(setting) or frappe.get_attr(setting)
	return cls()
