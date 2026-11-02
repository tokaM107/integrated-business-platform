# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The assistant's endpoint before a paid model is connected (SEC-11): a voice message too long is refused before it
# is decoded, and the endpoint is rate limited.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_assistant

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


class IntegrationTestAssistantChats(IntegrationTestCase):
	"""Saved chats (assistant/chats.py; owner's wish of 2 Nov 2026): a chat belongs to its user, the model sees the
	last five messages as said and a folded summary of the rest, and every turn is stored with its facts."""

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("assistant_chats")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="assistant_chats")

	def test_a_chat_belongs_to_its_user(self):
		from imed_erp.assistant import chats

		frappe.set_user("owner@imed.local")
		name = chats.new_chat()
		self.assertEqual([c.name for c in chats.list_chats()], [name])
		chats.append(name, "user", "إيه رصيد الخزنة؟")
		self.assertEqual(frappe.db.get_value("Assistant Chat", name, "title"), "إيه رصيد الخزنة؟")
		frappe.set_user("toqamo031@gmail.com")
		self.assertEqual(chats.list_chats(), [])
		self.assertRaises(frappe.PermissionError, chats.messages, name)
		self.assertRaises(frappe.PermissionError, chats.append, name, "user", "x")
		frappe.set_user("owner@imed.local")
		chats.rename_chat(name, "الخزن")
		chats.delete_chat(name)
		self.assertFalse(frappe.db.exists("Assistant Chat", name))
		self.assertEqual(frappe.db.count("Assistant Message", {"chat": name}), 0)

	def test_the_model_sees_five_messages_as_said_and_a_summary_of_the_rest(self):
		from imed_erp.assistant import chats

		name = chats.new_chat()
		for i in range(1, 13):  # 12 messages: 6 turns
			chats.append(name, "user" if i % 2 else "assistant", f"m{i}")
		mem = chats.memory(name)
		self.assertEqual([r.content for r in mem["window"]], ["m8", "m9", "m10", "m11", "m12"])
		self.assertEqual(len(mem["unsummarized"]), 7)  # m1..m7 left the window and are not folded yet
		calls = []

		def complete(system, prompt, json_schema=None):
			calls.append(prompt)
			return "The user asked m1 to m7; the answers were m2, m4, m6."

		self.assertTrue(chats.fold(name, complete))
		self.assertEqual(len(calls), 1)
		self.assertIn("m7", calls[0]); self.assertNotIn("m8", calls[0])
		mem = chats.memory(name)
		self.assertEqual(mem["summarized_upto"], 7)
		self.assertEqual(mem["unsummarized"], [])
		self.assertIn("m1 to m7", mem["summary"])
		# One more turn: nothing to fold yet (fewer than FOLD_EVERY beyond the window); no model call.
		chats.append(name, "user", "m13"); chats.append(name, "assistant", "m14")
		self.assertFalse(chats.fold(name, complete))
		self.assertEqual(len(calls), 1)
		text = chats.memory_text(name)
		self.assertIn("Summary of the earlier conversation", text); self.assertIn("m14", text); self.assertNotIn("user: m3", text)

	def test_send_message_in_a_chat_stores_both_turns_with_the_facts(self):
		from imed_erp.assistant import api, chats
		from imed_erp.assistant.providers import AssistantProvider

		class Fake(AssistantProvider):
			name, connected = "fake", True

			def reply(self, messages, context):
				from imed_erp.assistant import agent

				plan = {"steps": [{"tool": "count_records", "arguments": json.dumps({"doctype": "Booking", "filters": []})}], "may_need_more": False, "answer_without_reading": ""}
				queue = [json.dumps(plan), "فيه حجوزات."]
				return agent.run(messages[-1]["content"], context, lambda s, p, j=None: queue.pop(0), chat=context.get("chat"))

		name = chats.new_chat()
		with patch("imed_erp.assistant.api.get_provider", return_value=Fake()):
			r = api.send_message(chat=name, text="كام حجز؟")
		self.assertEqual((r["reply"], r["chat"]), ("فيه حجوزات.", name))
		rows = chats.messages(name)
		self.assertEqual([(m.role, m.content) for m in rows], [("user", "كام حجز؟"), ("assistant", "فيه حجوزات.")])
		self.assertIn("count_records", rows[1].facts)
		self.assertEqual(frappe.db.get_value("Assistant Chat", name, "message_count"), 2)
		self.assertEqual(api.get_chat(name)["messages"][1]["content"], "فيه حجوزات.")
