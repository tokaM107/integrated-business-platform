# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# One message of an assistant chat. Readable only by the chat's user (hooks.py); numbered once per chat: a unique
# index on (chat, seq) refuses a second message with the same number, whatever two requests do at once.

import frappe
from frappe.model.document import Document


class AssistantMessage(Document):
	pass


def on_doctype_update():
	frappe.db.add_unique("Assistant Message", ["chat", "seq"], constraint_name="unique_chat_seq")


def has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	return user == "Administrator" or frappe.db.get_value("Assistant Chat", doc.chat, "user") == user


def query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return ""
	return f"`tabAssistant Message`.`chat` in (select `name` from `tabAssistant Chat` where `user` = {frappe.db.escape(user)})"
