# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A conversation with the assistant (owner's wish of 2 Nov 2026: chats saved and listed, a new chat any time). The
# messages are Assistant Message rows; the chat keeps the rolling summary of the older turns, the assistant's long
# memory for this conversation (assistant/chats.py). A chat belongs to its user: the API serves nobody else's.

import frappe
from frappe import _
from frappe.model.document import Document


class AssistantChat(Document):
	def validate(self):
		if not self.user:
			self.user = frappe.session.user
		if self.user != frappe.session.user and "Administrator" != frappe.session.user:
			frappe.throw(_("A chat belongs to the user who opened it."), frappe.PermissionError)

	def on_trash(self):
		frappe.db.delete("Assistant Message", {"chat": self.name})
