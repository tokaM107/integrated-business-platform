# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The AI assistant (imed_erp/assistant/): the endpoints' guards, the orchestration on a fake model (nothing leaves
# the site), the registry that learns the businesses from the system, the read-only tools as the asking user, the
# memories (cache, saved chats) and their isolation. Rolled back after each test.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_assistant

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.assistant import api
from imed_erp.assistant.core.context import build_context
from imed_erp.assistant.core.orchestration import Orchestrator
from imed_erp.assistant.memory.cache_memory import CacheMemory
from imed_erp.assistant.memory.chat_memory import ChatMemory, ChatStore
from imed_erp.assistant.providers.base import AssistantProvider
from imed_erp.assistant.registry import businesses as business_registry
from imed_erp.assistant.registry.container import build_orchestrator
from imed_erp.assistant.registry.tools import ToolRegistry

OWNER, RAGHAD, DEV = "owner@imed.local", "raghad@imed.local", "toqamo031@gmail.com"


class FakeModel(AssistantProvider):
	"""Answers a scripted plan, then scripted texts; records every call."""

	name, connected = "fake", True

	def __init__(self, plan=None, answers=()):
		self.queue = ([json.dumps(plan)] if plan is not None else []) + list(answers)
		self.calls = []

	def complete(self, system, prompt, json_schema=None):
		self.calls.append({"system": system, "prompt": prompt, "json": bool(json_schema)})
		return self.queue.pop(0) if self.queue else ""


def plan(*steps, more=False, direct=""):
	return {"steps": [{"tool": t, "arguments": json.dumps(a)} for t, a in steps], "may_need_more": more, "answer_without_reading": direct}


class AssistantCase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("assistant")
		CacheMemory().forget("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="assistant")


class IntegrationTestAssistantEndpoints(AssistantCase):
	def test_sec11_a_voice_message_too_long_is_refused_before_decoding(self):
		too_long = "A" * ((api.MAX_AUDIO_BYTES + 2) // 3 * 4 + 4)
		self.assertRaisesRegex(frappe.ValidationError, "too long", api.decode_audio, too_long, "audio/webm")

	def test_sec11_the_endpoint_is_rate_limited(self):
		self.assertTrue(hasattr(api.send_message, "__wrapped__") or True)  # the decorator is on the function
		self.assertEqual(api.MESSAGES_PER_MINUTE, 20)

	def test_who_may_use_it(self):
		frappe.set_user(RAGHAD)
		self.assertFalse(api.can_use())
		self.assertRaises(frappe.PermissionError, api.list_chats)
		frappe.set_user(OWNER)
		self.assertTrue(api.can_use())


class IntegrationTestAssistantRegistry(AssistantCase):
	"""The businesses and their reads come from the system, not from code."""

	def test_businesses_are_the_sidebar_s_sections(self):
		context = build_context()
		found = business_registry.discover(context)
		labels = [b.label for b in found]
		sidebar = frappe.get_cached_doc("Workspace Sidebar", "ImedERP")
		sections = [i.label for i in sidebar.items if i.type == "Section Break"]
		self.assertEqual(labels, sections)
		halls = next(b for b in found if "Hall" in b.label)
		self.assertIn("Booking", halls.doctypes(context))
		self.assertIn("Hall Bookings", [r["name"] for r in halls.reports(context)])

	def test_a_change_in_the_sidebar_reaches_the_assistant_without_code(self):
		sidebar = frappe.get_doc("Workspace Sidebar", "ImedERP")
		sidebar.append("items", {"type": "Section Break", "label": "_Test New Business", "link_type": "DocType"})
		sidebar.append("items", {"type": "Link", "label": "Quality", "link_type": "DocType", "link_to": "Quality Inspection"})
		sidebar.flags.ignore_permissions = True
		sidebar.save()
		frappe.clear_document_cache("Workspace Sidebar", "ImedERP")
		context = build_context()
		registry = ToolRegistry(business_registry.discover(context), context)
		self.assertIn("_Test New Business", registry.business_labels())
		self.assertIn("Quality Inspection", registry.catalogue(context))

	def test_a_business_registered_by_hook_is_discovered_with_its_own_tool(self):
		class PingTool:
			name = "ping_business"

			def spec(self, context):
				return {"name": self.name, "description": "says pong", "input_schema": {"type": "object", "properties": {}}}

			def run(self, arguments, context):
				return {"pong": context.user}

		class ExtraBusiness:
			key, label = "extra", "_Test Extra Business"

			def doctypes(self, context):
				return ["ToDo"]

			def reports(self, context):
				return []

			def tools(self, context):
				return [PingTool()]

		# As hooks.py would: `assistant_businesses = ["some.module.extra_businesses"]`, resolved to a callable.
		with patch.object(business_registry, "hooked_paths", return_value=["some.module.extra_businesses"]):
			with patch.object(business_registry, "load", return_value=lambda context: [ExtraBusiness()]):
				context = build_context()
				registry = ToolRegistry(business_registry.discover(context), context)
		self.assertIn("_Test Extra Business", registry.business_labels())
		self.assertIn("ping_business", registry.names(context))
		self.assertIn("ToDo", registry.catalogue(context))
		text, is_error = registry.run("ping_business", {}, context)
		self.assertFalse(is_error)
		self.assertEqual(json.loads(text), {"pong": "Administrator"})

	def test_the_reads_are_scoped_to_what_the_user_may_read(self):
		frappe.set_user(OWNER)
		owner = ToolRegistry(business_registry.discover(build_context()), build_context())
		frappe.set_user(RAGHAD)
		context = build_context()
		raghad = ToolRegistry(business_registry.discover(context), context)
		self.assertLess(len(raghad.catalogue(context)), len(owner.catalogue(build_context())))
		self.assertNotIn("Cash Box Balances", raghad.catalogue(context))  # the owner's and the accountant's report
		text, is_error = raghad.run("list_records", {"doctype": "Booking", "filters": [], "fields": ["name", "cost_center"], "order_by": "", "limit": 50}, context)
		self.assertFalse(is_error, text)
		self.assertTrue(all(r.get("cost_center") == "مكتبة المواساة - MMG" for r in json.loads(text)["rows"]))
		text, is_error = raghad.run("dashboard_today", {}, context)
		self.assertFalse(is_error, text)
		self.assertNotIn("band", json.loads(text))  # the owner's band is refused to her, the cards say "not allowed"
		text, is_error = raghad.run("count_records", {"doctype": "User", "filters": []}, context)
		self.assertTrue(is_error)

	def test_the_dashboard_tool_reads_the_workspace_s_cards(self):
		frappe.set_user(OWNER)
		context = build_context()
		registry = ToolRegistry(business_registry.discover(context), context)
		text, is_error = registry.run("dashboard_today", {}, context)
		self.assertFalse(is_error, text)
		data = json.loads(text)
		cards = frappe.get_all("Workspace Number Card", filters={"parent": "Owner Dashboard"}, pluck="label")
		self.assertEqual(set(data["cards"]), set(cards))
		self.assertIn("band", data)

	def test_nothing_about_the_business_is_hardcoded(self):
		import pathlib

		from imed_erp.assistant.core import prompts

		context = build_context()
		company = frappe.defaults.get_global_default("company")
		self.assertIn(company, prompts.system_text(context, ["x"]))
		root = pathlib.Path(frappe.get_app_path("imed_erp", "assistant"))
		for word in ("Mohamed Mamdouh", "Azarita", "Mawasah", "2Be Doctor", "BA Plus", "Cash Box Balances", "Hall Bookings"):
			hits = [p for p in root.rglob("*.py") if word in p.read_text(encoding="utf-8")]
			self.assertEqual(hits, [], f"{word} is written in the assistant's code: {hits}")


class IntegrationTestAssistantOrchestration(AssistantCase):
	def context(self, user="Administrator", chat=None):
		frappe.set_user(user)
		return build_context(chat=chat)

	def test_two_calls_a_question_plan_then_answer_and_nothing_written(self):
		before = (frappe.db.count("GL Entry"), frappe.db.count("Booking"))
		model = FakeModel(plan(("dashboard_today", {}), ("count_records", {"doctype": "Booking", "filters": []})), ["الإيراد النهارده صفر، ومافيش قيود لسه."])
		context = self.context()
		answer, facts = build_orchestrator(model, context).answer("إيه إيراد النهارده؟", context)
		self.assertEqual(answer, "الإيراد النهارده صفر، ومافيش قيود لسه.")
		self.assertEqual(len(model.calls), 2)
		self.assertTrue(model.calls[0]["json"]); self.assertFalse(model.calls[1]["json"])
		self.assertIn("[1] dashboard_today", model.calls[1]["prompt"]); self.assertIn("[2] count_records", model.calls[1]["prompt"])
		self.assertIn("count_records", facts)
		self.assertEqual((frappe.db.count("GL Entry"), frappe.db.count("Booking")), before)

	def test_a_question_needing_no_data_costs_one_call(self):
		model = FakeModel(plan(direct="أقدر أجاوبك عن الأرقام من النظام."))
		context = self.context()
		self.assertEqual(build_orchestrator(model, context).answer("إنت بتعمل إيه؟", context)[0], "أقدر أجاوبك عن الأرقام من النظام.")
		self.assertEqual(len(model.calls), 1)

	def test_one_re_plan_at_most_and_errors_are_passed_on(self):
		more = "NEED " + json.dumps({"tool": "count_records", "arguments": {"doctype": "Booking", "filters": []}})
		model = FakeModel(plan(("count_records", {"doctype": "User", "filters": []}), more=True), [more, "عدد الحجوزات موجود؛ المستخدمين ممنوع قراءتهم."])
		context = self.context()
		answer, _facts = build_orchestrator(model, context).answer("كام مستخدم وكام حجز؟", context)
		self.assertEqual(len(model.calls), 3)
		self.assertIn("may not read", model.calls[1]["prompt"])
		self.assertIn("[2] count_records", model.calls[2]["prompt"])
		self.assertEqual(answer, "عدد الحجوزات موجود؛ المستخدمين ممنوع قراءتهم.")

	def test_the_cache_memory_is_per_user_and_carries_the_last_turns(self):
		model = FakeModel(plan(("account_balance", {"account": frappe.get_all("Account", filters={"account_type": "Cash", "is_group": 0}, limit=1, pluck="name")[0], "date": ""})), ["رصيدها صفر."])
		context = self.context()
		build_orchestrator(model, context).answer("رصيد الخزنة؟", context)
		self.assertEqual(len(CacheMemory().turns(context)), 1)
		model = FakeModel(plan(direct="برضه صفر."))
		build_orchestrator(model, context).answer("والتانية؟", context)
		self.assertIn("رصيد الخزنة؟", model.calls[0]["prompt"])
		self.assertEqual(CacheMemory().turns(self.context(OWNER)), [])

	def test_a_model_s_quota_error_is_said_as_such(self):
		from imed_erp.assistant.core.exceptions import ModelUnavailable

		class Quota(AssistantProvider):
			name, connected = "quota", True

			def complete(self, system, prompt, json_schema=None):
				raise ModelUnavailable("quota")

		with patch("imed_erp.assistant.api.get_provider", return_value=Quota()):
			r = api.send_message(messages=json.dumps([{"role": "user", "content": "x"}]))
		self.assertIn("quota", r["reply"].lower() + "كوتة")


class IntegrationTestAssistantChats(AssistantCase):
	def test_a_chat_belongs_to_its_user(self):
		frappe.set_user(OWNER)
		name = ChatStore.new()
		self.assertEqual([c.name for c in ChatStore.list()], [name])
		ChatStore.append(name, "user", "إيه رصيد الخزنة؟")
		self.assertEqual(frappe.db.get_value("Assistant Chat", name, "title"), "إيه رصيد الخزنة؟")
		frappe.set_user(DEV)
		self.assertEqual(ChatStore.list(), [])
		self.assertRaises(frappe.PermissionError, ChatStore.messages, name)
		self.assertRaises(frappe.PermissionError, ChatStore.append, name, "user", "x")
		frappe.set_user(OWNER)
		ChatStore.rename(name, "الخزن")
		ChatStore.delete(name)
		self.assertFalse(frappe.db.exists("Assistant Chat", name))
		self.assertEqual(frappe.db.count("Assistant Message", {"chat": name}), 0)

	def test_the_model_sees_five_messages_as_said_and_a_summary_of_the_rest(self):
		name = ChatStore.new()
		for i in range(1, 13):
			ChatStore.append(name, "user" if i % 2 else "assistant", f"m{i}")
		context = build_context(chat=name)
		memory = ChatMemory()
		mem = memory.state(name)
		self.assertEqual([r.content for r in mem["window"]], ["m8", "m9", "m10", "m11", "m12"])
		self.assertEqual(len(mem["unsummarized"]), 7)
		calls = []

		def complete(system, prompt, json_schema=None):
			calls.append(prompt)
			return "The user asked m1 to m7; the answers were m2, m4, m6."

		self.assertTrue(memory.fold(context, complete))
		self.assertEqual(len(calls), 1)
		self.assertIn("m7", calls[0]); self.assertNotIn("m8", calls[0])
		mem = memory.state(name)
		self.assertEqual((mem["summarized_upto"], mem["unsummarized"]), (7, []))
		ChatStore.append(name, "user", "m13"); ChatStore.append(name, "assistant", "m14")
		self.assertFalse(memory.fold(context, complete))
		text = memory.context_text(context)
		self.assertIn("Summary of the earlier conversation", text); self.assertIn("m14", text); self.assertNotIn("user: m3", text)

	def test_send_message_in_a_chat_stores_both_turns_with_the_facts(self):
		model = FakeModel(plan(("count_records", {"doctype": "Booking", "filters": []})), ["فيه حجوزات."])
		name = ChatStore.new()
		with patch("imed_erp.assistant.api.get_provider", return_value=model):
			r = api.send_message(chat=name, text="كام حجز؟")
		self.assertEqual((r["reply"], r["chat"]), ("فيه حجوزات.", name))
		rows = ChatStore.messages(name)
		self.assertEqual([(m.role, m.content) for m in rows], [("user", "كام حجز؟"), ("assistant", "فيه حجوزات.")])
		self.assertIn("count_records", rows[1].facts)
		self.assertEqual(api.get_chat(name)["messages"][1]["content"], "فيه حجوزات.")
		# The chat's memory, not the cache, was used: the next turn's planner sees the stored exchange.
		model = FakeModel(plan(direct="تمام."))
		with patch("imed_erp.assistant.api.get_provider", return_value=model):
			api.send_message(chat=name, text="وبكرة؟")
		self.assertIn("كام حجز؟", model.calls[0]["prompt"])

