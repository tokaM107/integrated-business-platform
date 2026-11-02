# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A conversation with the assistant (owner's wish of 2 Nov 2026: chats saved and listed, a new chat any time). The
# messages are Assistant Message rows; the chat keeps the rolling summary of its older turns (assistant/memory/).
# A chat is its user's alone: in the chat window, the desk and the REST API (has_permission, query_conditions;
# hooks.py). Administrator alone sees every chat.

import frappe
from frappe import _
from frappe.model.document import Document


class AssistantChat(Document):
	def validate(self):
		if not self.user:
			self.user = frappe.session.user
		if self.user != frappe.session.user and frappe.session.user != "Administrator":
			frappe.throw(_("A chat belongs to the user who opened it."), frappe.PermissionError)

	def on_trash(self):
		frappe.db.delete("Assistant Message", {"chat": self.name})


def has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	return user == "Administrator" or doc.user == user


def query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return ""
	return f"`tabAssistant Chat`.`user` = {frappe.db.escape(user)}"
