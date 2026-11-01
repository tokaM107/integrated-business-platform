# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The assistant's endpoint before a paid model is connected (SEC-11): a voice message too long is refused before it
# is decoded, and the endpoint is rate limited.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_assistant

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.assistant import api


class IntegrationTestAssistant(IntegrationTestCase):
	def test_sec11_a_voice_message_too_long_is_refused_before_decoding(self):
		too_long = "A" * ((api.MAX_AUDIO_BYTES + 2) // 3 * 4 + 4)
		with patch("base64.b64decode") as decode:
			self.assertRaisesRegex(frappe.ValidationError, "too long", api.decode_audio, too_long, "audio/webm")
		decode.assert_not_called()

	def test_sec11_the_endpoint_is_rate_limited(self):
		# Inside a web request from one address: the first MESSAGES_PER_MINUTE calls go through (stopped here
		# right after the limit, before any model is asked), the next is refused.
		class Reached(Exception):
			pass

		request = frappe._dict(method="POST")
		with patch.object(frappe.local, "request", request, create=True), patch.object(
			frappe.local, "request_ip", "203.0.113.7", create=True
		), patch.object(frappe.local, "form_dict", frappe._dict(cmd="imed_erp.assistant.api.send_message")), patch.object(
			api, "check_access", side_effect=Reached
		):
			frappe.cache.delete_keys("rl:imed_erp.assistant.api.send_message")
			try:
				for _ in range(api.MESSAGES_PER_MINUTE):
					self.assertRaises(Reached, api.send_message, messages="[]")
				self.assertRaises(frappe.RateLimitExceededError, api.send_message, messages="[]")
			finally:
				frappe.cache.delete_keys("rl:imed_erp.assistant.api.send_message")


class FakeBlock:
	def __init__(self, **kw):
		self.__dict__.update(kw)


class FakeResponse:
	def __init__(self, content, stop_reason):
		self.content, self.stop_reason = content, stop_reason


class FakeClaude:
	"""Stands in for anthropic.Anthropic: first asks for the tools the test scripts, then answers with text."""

	def __init__(self, calls):
		self.calls = list(calls)
		self.requests = []
		self.beta = self
		self.messages = self

	def create(self, **kwargs):
		self.requests.append(kwargs)
		step = self.calls.pop(0)
		if step[0] == "tool":
			return FakeResponse([FakeBlock(type="tool_use", id=f"t{len(self.requests)}", name=step[1], input=step[2])], "tool_use")
		return FakeResponse([FakeBlock(type="text", text=step[1])], "end_turn")


class IntegrationTestAssistantClaude(IntegrationTestCase):
	"""The read-only Claude provider (assistant/claude.py): the tools read as the asking user, nothing is written,
	the loop ends with the model's text. A fake model: nothing leaves the site."""

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("assistant_claude")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="assistant_claude")

	def provider(self, calls):
		from imed_erp.assistant.claude import ClaudeProvider

		p = ClaudeProvider()
		p.api_key = "test"
		p.client = lambda: FakeClaude(calls)
		return p

	def test_the_loop_reads_then_answers_and_never_writes(self):
		from imed_erp.assistant import claude

		before = (frappe.db.count("GL Entry"), frappe.db.count("Booking"))
		p = self.provider([("tool", "dashboard_today", {}), ("tool", "count_records", {"doctype": "Booking", "filters": []}), ("text", "الإيراد النهارده صفر.")])
		reply = p.reply([{"role": "user", "content": "إيه إيراد النهارده؟"}], {"user": "Administrator", "full_name": "Admin", "lang": "ar", "company": "Mohamed Mamdouh group"})
		self.assertEqual(reply, "الإيراد النهارده صفر.")
		self.assertEqual((frappe.db.count("GL Entry"), frappe.db.count("Booking")), before)
		# The tool results went back to the model, as tool_result blocks on a user turn, not as errors.
		text, is_error = claude.run_tool("dashboard_today", {})
		self.assertFalse(is_error)
		data = json.loads(text)
		self.assertIn("cards", data)
		self.assertIn("band", data)
		self.assertIn("Revenue This Month", data["cards"])

	def test_tools_refuse_what_is_not_allowed_and_say_so(self):
		from imed_erp.assistant import claude

		text, is_error = claude.run_tool("count_records", {"doctype": "User", "filters": []})
		self.assertTrue(is_error)
		self.assertIn("may not read", text)
		text, is_error = claude.run_tool("run_report", {"report": "General Ledger", "filters": {}})
		self.assertTrue(is_error)
		text, is_error = claude.run_tool("no_such_tool", {})
		self.assertTrue(is_error)
		text, is_error = claude.run_tool("account_balance", {"account": "no such account", "date": ""})
		self.assertTrue(is_error)

	def test_tools_read_as_the_asking_user(self):
		from imed_erp.assistant import claude

		# The owner reads the cash boxes report and an account's balance.
		frappe.set_user("owner@imed.local")
		text, is_error = claude.run_tool("run_report", {"report": "Cash Box Balances", "filters": {}})
		self.assertFalse(is_error, text)
		self.assertIn("rows", json.loads(text))
		text, is_error = claude.run_tool("account_balance", {"account": "خزينة مكتبة الأزاريطة - MMG", "date": ""})
		self.assertFalse(is_error, text)
		self.assertIn("balance", json.loads(text))
		# A branch manager (were the chat ever opened to her) is refused the owner's figures and sees only her records.
		frappe.set_user("raghad@imed.local")
		text, is_error = claude.run_tool("dashboard_today", {})
		self.assertTrue(is_error)
		text, is_error = claude.run_tool("run_report", {"report": "Cash Box Balances", "filters": {}})
		self.assertTrue(is_error)
		text, is_error = claude.run_tool("list_records", {"doctype": "Booking", "filters": [{"field": "status", "operator": "!=", "value": "Cancelled"}], "fields": ["name", "cost_center"], "order_by": "", "limit": 50})
		self.assertFalse(is_error, text)
		rows = json.loads(text)["rows"]
		self.assertTrue(all(r.get("cost_center") == "مكتبة المواساة - MMG" for r in rows), rows[:3])

	def test_filters_from_the_model_are_turned_into_frappe_filters(self):
		from imed_erp.assistant.claude import parse_filters

		self.assertEqual(
			parse_filters([
				{"field": "booking_date", "operator": ">=", "value": "2026-11-01"},
				{"field": "status", "operator": "in", "value": '["Tentative", "Confirmed"]'},
				{"field": "hours", "operator": ">", "value": "2"},
				{"field": "source_system", "operator": "is", "value": "set"},
			]),
			[["booking_date", ">=", "2026-11-01"], ["status", "in", ["Tentative", "Confirmed"]], ["hours", ">", 2], ["source_system", "is", "set"]],
		)
