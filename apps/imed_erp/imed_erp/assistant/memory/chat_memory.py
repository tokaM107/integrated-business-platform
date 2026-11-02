# Saved chats and their memory (owner's wish of 2 Nov 2026: like ChatGPT, a list of chats, a new chat any time, a
# follow-up that understands the conversation).
#
#   ChatStore   the chats and their messages (Assistant Chat, Assistant Message): list, new, rename, delete, append.
#               A chat belongs to its user; every method refuses another user's chat.
#   ChatMemory  what the model is told: the last WINDOW messages as said, a running summary of everything older
#               (folded by one small model call once FOLD_EVERY messages have left the window, never per message),
#               and the facts behind the last answers.
#
# Conversational memory is never the source of truth for business figures: the facts are what was read at the time,
# labelled as such; a fresh question reads again.

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from imed_erp.assistant.core import prompts
from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.interfaces import Completer
from imed_erp.assistant.core.prompts import data_block

WINDOW = 5
FOLD_EVERY = 4
TITLE_CHARS = 60
MAX_SUMMARY_CHARS = 2500


class ChatStore:
	@staticmethod
	def own(chat: str):
		doc = frappe.get_doc("Assistant Chat", chat)
		if doc.user != frappe.session.user and frappe.session.user != "Administrator":
			frappe.throw(_("Not your chat."), frappe.PermissionError)
		return doc

	@staticmethod
	def list(limit: int = 50) -> list[dict]:
		return frappe.get_all(
			"Assistant Chat",
			filters={"user": frappe.session.user},
			fields=["name", "title", "last_message_at", "message_count"],
			order_by="last_message_at desc, creation desc",
			limit=cint(limit) or 50,
		)

	@staticmethod
	def new(title: str | None = None, company: str | None = None) -> str:
		if not company:
			from imed_erp.assistant.core.context import build_context

			company = build_context().company  # a company the user may read, never a bare default
		doc = frappe.get_doc({"doctype": "Assistant Chat", "user": frappe.session.user, "company": company, "title": (title or "").strip()[:TITLE_CHARS] or _("New chat")})
		doc.insert(ignore_permissions=True)
		return doc.name

	@classmethod
	def check_company(cls, chat: str, company: str) -> None:
		"""A chat's memory holds figures of the company it was opened in: never carried into another company's."""
		doc = cls.own(chat)
		if not doc.company:
			# A chat saved before chats had a company: bound to the first company it is used in.
			frappe.db.set_value("Assistant Chat", doc.name, "company", company, update_modified=False)
			return
		chat_company = doc.company
		if chat_company != company:
			frappe.throw(_("This chat belongs to {0}; you are working in {1}. Start a new chat.").format(chat_company, company), frappe.PermissionError)

	@classmethod
	def rename(cls, chat: str, title: str) -> str:
		doc = cls.own(chat)
		doc.title = (title or "").strip()[:TITLE_CHARS] or doc.title
		doc.save(ignore_permissions=True)
		return doc.title

	@classmethod
	def delete(cls, chat: str) -> None:
		cls.own(chat).delete(ignore_permissions=True)

	@classmethod
	def messages(cls, chat: str, after: int = 0) -> list[dict]:
		cls.own(chat)
		return frappe.get_all("Assistant Message", filters={"chat": chat, "seq": [">", cint(after)]}, fields=["seq", "role", "content", "facts", "creation"], order_by="seq asc")

	@classmethod
	def append(cls, chat: str, role: str, content: str, facts: str = "") -> int:
		"""The next message of the chat. The chat's row is locked first, so two requests on the same chat (two tabs,
		a double click) number their messages one after the other, never twice the same (a unique index on
		(chat, seq) backs this up)."""
		cls.own(chat)
		doc = frappe.get_doc("Assistant Chat", chat, for_update=True)
		seq = cint(doc.message_count) + 1
		frappe.get_doc({"doctype": "Assistant Message", "chat": chat, "seq": seq, "role": role, "content": content, "facts": facts or ""}).insert(ignore_permissions=True)
		values = {"message_count": seq, "last_message_at": now_datetime()}
		if role == "user" and (not doc.title or doc.title == _("New chat")):
			values["title"] = content.strip().replace("\n", " ")[:TITLE_CHARS]
		frappe.db.set_value("Assistant Chat", chat, values, update_modified=False)
		return seq


class ChatMemory:
	def state(self, chat: str) -> dict:
		"""The summary, the window and what lies between them. Only the messages after the summary are read: the cost
		of a request does not grow with the length of the chat."""
		doc = ChatStore.own(chat)
		rows = ChatStore.messages(chat, after=cint(doc.summarized_upto))
		window = rows[-WINDOW:]
		return {
			"summary": doc.summary or "",
			"window": window,
			"unsummarized": rows[: max(0, len(rows) - WINDOW)],
			"summarized_upto": cint(doc.summarized_upto),
		}

	def context_text(self, context: RequestContext) -> str:
		mem = self.state(context.chat)
		parts = []
		if mem["summary"]:
			parts.append("Summary of the earlier conversation:\n" + mem["summary"])
		if mem["window"]:
			parts.append("Last messages, as said:\n" + "\n".join(f"{r.role}: {r.content}" + (f"\n  {data_block('facts read', r.facts[:600])}" if r.facts else "") for r in mem["window"]))
		return "\n\n".join(parts) or "(a new conversation)"

	def record(self, context: RequestContext, question: str, answer: str, facts: str) -> None:
		# The API stores the user's turn before the model runs (so a failure still leaves the question); the answer
		# with its facts is stored here, once.
		ChatStore.append(context.chat, "assistant", answer, facts)

	def fold(self, context: RequestContext, complete: Completer) -> bool:
		mem = self.state(context.chat)
		if len(mem["unsummarized"]) < FOLD_EVERY:
			return False
		transcript = "\n".join(f"{r.role}: {r.content}" for r in mem["unsummarized"])
		summary = (complete(prompts.SUMMARIZER, f"Current summary:\n{mem['summary'] or '(none)'}\n\nNew turns to fold in:\n{transcript}") or "").strip()[:MAX_SUMMARY_CHARS]
		if not summary:
			return False
		frappe.db.set_value("Assistant Chat", context.chat, {"summary": summary, "summarized_upto": mem["unsummarized"][-1].seq}, update_modified=False)
		return True
