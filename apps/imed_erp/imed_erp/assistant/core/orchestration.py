# Planner -> Executor -> Synthesizer, the assistant's reasoning flow (the owner's choice of 1 Nov 2026 over a
# tool-calling loop: two model calls a question, three at most).
#
# The orchestrator knows nothing of a model vendor, of Frappe doctypes or of where memory lives: it takes a
# Completer, a ToolCatalog and a ConversationMemory (core.interfaces) and runs the flow. The service (service.py)
# assembles the three for a request.

from __future__ import annotations

import json
from typing import Any

from frappe import _

from imed_erp.assistant.core import prompts
from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.interfaces import Completer, ConversationMemory, JsonSchema, ToolCatalog

MAX_PLAN_STEPS = 6


def plan_schema(tool_names: list[str]) -> JsonSchema:
	return {
		"type": "object",
		"properties": {
			"steps": {
				"type": "array",
				"items": {
					"type": "object",
					"properties": {
						"tool": {"type": "string", "enum": tool_names},
						"arguments": {"type": "string", "description": "the tool's arguments as a JSON object text"},
					},
					"required": ["tool", "arguments"],
				},
			},
			"may_need_more": {"type": "boolean"},
			"answer_without_reading": {"type": "string", "description": "the answer, only when the question needs no data (a greeting, a question about what the assistant can do); else empty"},
		},
		"required": ["steps", "may_need_more", "answer_without_reading"],
	}


def parse_plan(text: str) -> tuple[list[dict], bool, str]:
	try:
		plan = json.loads(text)
	except (TypeError, ValueError):
		start, end = text.find("{"), text.rfind("}")
		try:
			plan = json.loads(text[start : end + 1]) if start >= 0 and end > start else {}
		except ValueError:
			plan = {}
	steps = [s for s in (plan.get("steps") or []) if isinstance(s, dict) and s.get("tool")]
	return steps, bool(plan.get("may_need_more")), (plan.get("answer_without_reading") or "").strip()


def parse_arguments(raw: Any) -> dict:
	if isinstance(raw, dict):
		return raw
	try:
		value = json.loads(raw or "{}")
		return value if isinstance(value, dict) else {}
	except (TypeError, ValueError):
		return {}


class Orchestrator:
	def __init__(self, complete: Completer, tools: ToolCatalog, memory: ConversationMemory):
		self.complete = complete
		self.tools = tools
		self.memory = memory

	def answer(self, question: str, context: RequestContext) -> tuple[str, str]:
		"""(answer, facts) for `question`. The facts are the compact results the answer was built on."""
		self.memory.fold(context, self.complete)
		memo = self.memory.context_text(context)
		header = f"[{context.header()}]"
		system = prompts.system_text(context, self.tools.business_labels(), self.tools.prompt_notes())

		plan_prompt = f"{header}\n\nTools:\n{self.tools.catalogue(context)}\n\nMemory of this conversation:\n{memo}\n\nQuestion: {question}"
		steps, may_need_more, direct = parse_plan(self.complete(prompts.PLANNER, plan_prompt, plan_schema(self.tools.names())))
		if direct and not steps:
			self.memory.record(context, question, direct, "")
			return direct, ""

		results = self.execute(steps[:MAX_PLAN_STEPS], context)
		answer = self.synthesize(system, header, memo, question, results, may_need_more)
		if may_need_more and answer.startswith("NEED "):
			more = parse_arguments(answer[5:])
			if more.get("tool"):
				results += self.execute([more], context)
			answer = self.synthesize(system, header, memo, question, results, False)
		facts = "; ".join(f"{r['tool']}: {r['result'][:200]}" for r in results)
		answer = answer or _("I found nothing to say; try asking in another way.")
		self.memory.record(context, question, answer, facts)
		return answer, facts

	def execute(self, steps: list[dict], context: RequestContext) -> list[dict]:
		results = []
		for step in steps:
			name, arguments = step.get("tool"), parse_arguments(step.get("arguments"))
			text, is_error = self.tools.run(name, arguments, context)
			results.append({"tool": name, "arguments": arguments, "error": is_error, "result": text})
		return results

	def synthesize(self, system: str, header: str, memo: str, question: str, results: list[dict], may_need_more: bool) -> str:
		shown = "\n\n".join(f"[{i + 1}] {r['tool']} {json.dumps(r['arguments'], ensure_ascii=False)}\n{r['result']}" for i, r in enumerate(results))
		prompt = f"{header}\n\nMemory of this conversation:\n{memo}\n\nQuestion: {question}\n\nResults of the reads:\n{shown}"
		if may_need_more:
			prompt += prompts.NEED_MORE
		return (self.complete(system + prompts.SYNTHESIZER_TAIL, prompt) or "").strip()
