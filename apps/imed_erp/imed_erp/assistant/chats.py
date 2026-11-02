# Saved chats and the assistant's memory of each (owner's wish of 2 Nov 2026: like ChatGPT, a list of chats, a new
# chat any time, and a follow-up that understands the conversation).
#
#   window    the last WINDOW messages of the chat go to the model as they were said;
#   summary   everything older is folded, by one small model call, into a running summary kept on the chat
#             (Assistant Chat.summary), re-folded only when FOLD_EVERY new messages have left the window, so the
#             summary call is paid once per few turns, never per message;
#   facts     the compact results of the reads behind the last answers, so "and the other branch?" can be answered
#             without reading again when the figures are already there.
#
# A chat belongs to its user; every function here refuses another user's chat.

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

WINDOW = 5  # messages sent as they are (the last ones)
FOLD_EVERY = 4  # fold into the summary once this many messages lie beyond the window and are not in it yet
TITLE_CHARS = 60
MAX_SUMMARY_CHARS = 2500

SUMMARIZER = """You keep the running memory of a conversation between a business owner and the ERP assistant. Rewrite the summary so it holds, briefly, what the user asked about, the figures that were answered (with their dates), and any standing instruction or preference the user gave. Keep it under 250 words, in the conversation's language, plain text, no headings. Drop greetings and repetition."""


def own(chat):
	"""The chat, if it is the current user's; else a permission error."""
	doc = frappe.get_doc("Assistant Chat", chat)
	if doc.user != frappe.session.user and frappe.session.user != "Administrator":
		frappe.throw(_("Not your chat."), frappe.PermissionError)
	return doc


def list_chats(limit=50):
	return frappe.get_all(
		"Assistant Chat",
		filters={"user": frappe.session.user},
		fields=["name", "title", "last_message_at", "message_count"],
		order_by="last_message_at desc, creation desc",
		limit_page_length=cint(limit) or 50,
	)


def new_chat(title=None):
	doc = frappe.get_doc({"doctype": "Assistant Chat", "user": frappe.session.user, "title": (title or "").strip()[:TITLE_CHARS] or _("New chat")})
	doc.insert(ignore_permissions=True)
	return doc.name


def rename_chat(chat, title):
	doc = own(chat)
	doc.title = (title or "").strip()[:TITLE_CHARS] or doc.title
	doc.save(ignore_permissions=True)
	return doc.title


def delete_chat(chat):
	own(chat).delete(ignore_permissions=True)


def messages(chat, start=0, limit=None):
	own(chat)
	return frappe.get_all(
		"Assistant Message",
		filters={"chat": chat, "seq": [">", cint(start)]},
		fields=["seq", "role", "content", "facts", "creation"],
		order_by="seq asc",
		limit_page_length=limit or 0,
	)


def append(chat, role, content, facts=""):
	doc = own(chat)
	seq = cint(doc.message_count) + 1
	frappe.get_doc({"doctype": "Assistant Message", "chat": chat, "seq": seq, "role": role, "content": content, "facts": facts or ""}).insert(ignore_permissions=True)
	values = {"message_count": seq, "last_message_at": now_datetime()}
	if role == "user" and (not doc.title or doc.title == _("New chat")):
		values["title"] = content.strip().replace("\n", " ")[:TITLE_CHARS]
	frappe.db.set_value("Assistant Chat", chat, values, update_modified=False)
	return seq


def memory(chat):
	"""{summary, window: [{role, content, facts}], unsummarized: n} for the model."""
	doc = own(chat)
	rows = messages(chat)
	window = rows[-WINDOW:] if rows else []
	older = rows[: max(0, len(rows) - WINDOW)]
	unsummarized = [r for r in older if r.seq > cint(doc.summarized_upto)]
	return {"summary": doc.summary or "", "window": window, "unsummarized": unsummarized, "summarized_upto": cint(doc.summarized_upto)}


def fold(chat, complete):
	"""Fold the messages that left the window into the summary, when enough of them have (one model call)."""
	mem = memory(chat)
	if len(mem["unsummarized"]) < FOLD_EVERY:
		return False
	transcript = "\n".join(f"{r.role}: {r.content}" for r in mem["unsummarized"])
	prompt = f"Current summary:\n{mem['summary'] or '(none)'}\n\nNew turns to fold in:\n{transcript}"
	summary = (complete(SUMMARIZER, prompt) or "").strip()[:MAX_SUMMARY_CHARS]
	if not summary:
		return False
	frappe.db.set_value("Assistant Chat", chat, {"summary": summary, "summarized_upto": mem["unsummarized"][-1].seq}, update_modified=False)
	return True


def memory_text(chat):
	"""The memory as the planner and the synthesizer read it."""
	mem = memory(chat)
	parts = []
	if mem["summary"]:
		parts.append("Summary of the earlier conversation:\n" + mem["summary"])
	if mem["window"]:
		parts.append("Last messages, as said:\n" + "\n".join(f"{r.role}: {r.content}" + (f"\n  (facts read: {r.facts[:600]})" if r.facts else "") for r in mem["window"]))
	return "\n\n".join(parts) or "(a new conversation)"
