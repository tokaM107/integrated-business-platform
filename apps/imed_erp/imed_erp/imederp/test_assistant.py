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


class IntegrationTestAssistantAgent(IntegrationTestCase):
	"""The Planner -> Executor -> Synthesizer agent with its short memory (assistant/agent.py), on a fake model:
	nothing leaves the site. The tools read as the asking user; nothing is written."""

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("assistant_agent")
		from imed_erp.assistant import agent

		agent.forget("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="assistant_agent")

	def fake(self, plan, answers):
		"""complete(): the plan first (JSON), then the answers in order; every call is recorded."""
		calls = []
		queue = [json.dumps(plan)] + list(answers)

		def complete(system, prompt, json_schema=None):
			calls.append({"system": system[:40], "prompt": prompt, "json": bool(json_schema)})
			return queue.pop(0)

		return complete, calls

	def context(self, user="Administrator"):
		return {"user": user, "full_name": "x", "lang": "ar", "company": "Mohamed Mamdouh group"}

	def test_two_calls_a_question_plan_then_answer_and_nothing_written(self):
		from imed_erp.assistant import agent

		before = (frappe.db.count("GL Entry"), frappe.db.count("Booking"))
		plan = {"steps": [{"tool": "dashboard_today", "arguments": "{}"}, {"tool": "count_records", "arguments": json.dumps({"doctype": "Booking", "filters": []})}], "may_need_more": False, "answer_without_reading": ""}
		complete, calls = self.fake(plan, ["الإيراد النهارده صفر، ومافيش قيود لسه."])
		answer = agent.run("إيه إيراد النهارده؟", self.context(), complete)
		self.assertEqual(answer, "الإيراد النهارده صفر، ومافيش قيود لسه.")
		self.assertEqual(len(calls), 2)
		self.assertTrue(calls[0]["json"]); self.assertFalse(calls[1]["json"])
		# The synthesizer saw the compact results of both reads, not the raw dashboard JSON.
		self.assertIn("[1] dashboard_today", calls[1]["prompt"]); self.assertIn("[2] count_records", calls[1]["prompt"])
		self.assertIn('"cards"', calls[1]["prompt"]); self.assertNotIn('"machines"', calls[1]["prompt"])
		self.assertEqual((frappe.db.count("GL Entry"), frappe.db.count("Booking")), before)

	def test_the_short_memory_carries_the_last_turns(self):
		from imed_erp.assistant import agent

		plan = {"steps": [{"tool": "account_balance", "arguments": json.dumps({"account": "خزينة مكتبة الأزاريطة - MMG", "date": ""})}], "may_need_more": False, "answer_without_reading": ""}
		complete, calls = self.fake(plan, ["رصيد الأزاريطة صفر (مافيش قيود)."])
		agent.run("رصيد الأزاريطة؟", self.context(), complete)
		turns = agent.recall("Administrator")
		self.assertEqual(len(turns), 1)
		self.assertEqual(turns[0]["q"], "رصيد الأزاريطة؟")
		self.assertIn("account_balance", turns[0]["facts"])
		# The next question's planner sees the memory.
		complete, calls = self.fake({"steps": [], "may_need_more": False, "answer_without_reading": "وفي المواساة برضه صفر."}, [])
		answer = agent.run("وفي المواساة؟", self.context(), complete)
		self.assertIn("رصيد الأزاريطة؟", calls[0]["prompt"])
		self.assertEqual(answer, "وفي المواساة برضه صفر.")
		self.assertEqual(len(agent.recall("Administrator")), 2)
		# Another user has his own memory.
		self.assertEqual(agent.recall("owner@imed.local"), [])

	def test_a_question_needing_no_data_costs_one_call(self):
		from imed_erp.assistant import agent

		complete, calls = self.fake({"steps": [], "may_need_more": False, "answer_without_reading": "أقدر أجاوبك عن الأرقام من النظام."}, [])
		self.assertEqual(agent.run("إنت بتعمل إيه؟", self.context(), complete), "أقدر أجاوبك عن الأرقام من النظام.")
		self.assertEqual(len(calls), 1)

	def test_one_re_plan_at_most_and_errors_are_passed_on(self):
		from imed_erp.assistant import agent

		plan = {"steps": [{"tool": "count_records", "arguments": json.dumps({"doctype": "User", "filters": []})}], "may_need_more": True, "answer_without_reading": ""}
		more = 'NEED ' + json.dumps({"tool": "count_records", "arguments": {"doctype": "Booking", "filters": []}})
		complete, calls = self.fake(plan, [more, "عدد الحجوزات موجود؛ المستخدمين ممنوع قراءتهم."])
		answer = agent.run("كام مستخدم وكام حجز؟", self.context(), complete)
		self.assertEqual(len(calls), 3)
		self.assertIn("may not read", calls[1]["prompt"])  # the refused read reached the model as an error
		self.assertIn("[2] count_records", calls[2]["prompt"])
		self.assertEqual(answer, "عدد الحجوزات موجود؛ المستخدمين ممنوع قراءتهم.")

	def test_reads_run_as_the_asking_user(self):
		from imed_erp.assistant import agent

		frappe.set_user("raghad@imed.local")
		plan = {"steps": [{"tool": "dashboard_today", "arguments": "{}"}, {"tool": "list_records", "arguments": json.dumps({"doctype": "Booking", "filters": [], "fields": ["name", "cost_center"], "order_by": "", "limit": 50})}], "may_need_more": False, "answer_without_reading": ""}
		complete, calls = self.fake(plan, ["ok"])
		agent.run("x", self.context("raghad@imed.local"), complete)
		prompt = calls[1]["prompt"]
		self.assertIn("Only the owner", prompt)  # the dashboard refused her
		self.assertNotIn("مكتبة الأزاريطة - MMG", prompt.split("[2] list_records")[1])  # only her branch's bookings

	def test_the_providers_route_through_the_agent(self):
		from imed_erp.assistant.gemini import GeminiProvider, function_declarations
		from imed_erp.assistant.claude import ClaudeProvider

		self.assertEqual({d.name for d in function_declarations()}, {"dashboard_today", "run_report", "list_records", "count_records", "account_balance"})
		for cls in (GeminiProvider, ClaudeProvider):
			p = cls()
			p.api_key = "test"
			p.complete = lambda system, prompt, json_schema=None: json.dumps({"steps": [], "may_need_more": False, "answer_without_reading": "تمام"})
			self.assertEqual(p.reply([{"role": "user", "content": "أهلًا"}], self.context()), "تمام")

	def test_filters_from_the_model_are_turned_into_frappe_filters(self):
		from imed_erp.assistant.tools import parse_filters

		self.assertEqual(
			parse_filters([
				{"field": "booking_date", "operator": ">=", "value": "2026-11-01"},
				{"field": "status", "operator": "in", "value": '["Tentative", "Confirmed"]'},
				{"field": "hours", "operator": ">", "value": "2"},
				{"field": "source_system", "operator": "is", "value": "set"},
			]),
			[["booking_date", ">=", "2026-11-01"], ["status", "in", ["Tentative", "Confirmed"]], ["hours", ">", 2], ["source_system", "is", "set"]],
		)

	def test_tools_refuse_what_is_not_allowed_and_say_so(self):
		from imed_erp.assistant import tools

		for name, args in (("count_records", {"doctype": "User", "filters": []}), ("run_report", {"report": "General Ledger", "filters": {}}), ("no_such_tool", {}), ("account_balance", {"account": "no such account", "date": ""})):
			text, is_error = tools.run_tool(name, args)
			self.assertTrue(is_error, name)
