# The assistant's agent: Planner -> Executor -> Synthesizer, with a short memory (the owner's choice, 1 Nov 2026,
# over the ReAct loop, which spent a model call per read).
#
#   Planner      one model call: the question, the short memory and the compact tool catalogue in; a JSON plan out:
#                the reads to make (tool, arguments), nothing else. No reasoning text is generated.
#   Executor     no model: runs the plan's reads as the asking user (tools.run_tool: permissions, rollback), in order,
#                and compacts each result to what an answer needs.
#   Synthesizer  one model call: the question, the memory and the compact results in; the answer out.
#   Re-plan      at most once, only when the planner said the answer may need a second look and the synthesizer
#                asked for more (a named read), so a question costs 2 calls, 3 at most.
#   Short memory the last turns of this user (question, answer, the facts read), kept in the site's cache for
#                30 minutes, so "وفي المواساة؟" after "رصيد الأزاريطة؟" is understood without resending the whole chat.
#
# The agent is model-agnostic: a provider gives one function `complete(system, prompt, json_schema=None) -> str`.

import json

import frappe
from frappe import _
from frappe.utils import cint, flt

from imed_erp.assistant.tools import DOCTYPES, REPORTS, SYSTEM, TOOLS, run_tool, user_context_line

MEMORY_TTL = 30 * 60
MEMORY_TURNS = 4
MAX_PLAN_STEPS = 6
MAX_ROWS_TO_MODEL = 60
MAX_CHARS_TO_MODEL = 12_000

PLAN_SCHEMA = {
	"type": "object",
	"properties": {
		"steps": {
			"type": "array",
			"items": {
				"type": "object",
				"properties": {
					"tool": {"type": "string", "enum": [t["name"] for t in TOOLS]},
					"arguments": {"type": "string", "description": "the tool's arguments as a JSON object text"},
					"why": {"type": "string", "description": "five words at most"},
				},
				"required": ["tool", "arguments"],
			},
		},
		"may_need_more": {"type": "boolean"},
		"answer_without_reading": {"type": "string", "description": "the answer, only when the question needs no data (a greeting, a question about what the assistant can do); else empty"},
	},
	"required": ["steps", "may_need_more", "answer_without_reading"],
}


def catalogue():
	"""The tools, compact, for the planner."""
	lines = []
	for t in TOOLS:
		args = ", ".join(t["input_schema"].get("properties", {}).keys()) or "no arguments"
		lines.append(f"- {t['name']}({args})")
	lines.append("Reports for run_report: " + "; ".join(f"{n} = {m}" for n, m in REPORTS.items()))
	lines.append("DocTypes for list_records/count_records: " + ", ".join(DOCTYPES))
	lines.append('Filters: [{"field": ..., "operator": "=|!=|>|<|>=|<=|like|in|between|is", "value": "text; a JSON list for in/between"}]')
	return "\n".join(lines)


PLANNER = """You plan the reads that answer a question about the IMED ERP. You do not answer; you list the tool calls, with their arguments, that fetch exactly the figures needed. Prefer one read that already holds the answer (dashboard_today for today or this month; run_report for a period or a breakdown) over several. Dates are YYYY-MM-DD. Use the memory to resolve "it", "the other one", "and last month?". If the question needs no data, put the answer in answer_without_reading and no steps. Output JSON only."""

SYNTHESIZER = SYSTEM + """

You now have the results of the reads already made (below). Answer from them only. If a result says "error", say what could not be read and why. If a figure is zero and the results show no records behind it, say it is missing data, not a result. Do not list the reads; give the answer."""


# ---------------- short memory ----------------


def memory_key(user):
	return f"imed_assistant_memory:{user}"


def recall(user):
	return frappe.cache.get_value(memory_key(user)) or []


def remember(user, question, answer, facts):
	turns = recall(user)
	turns.append({"q": question[:400], "a": answer[:600], "facts": facts[:1200]})
	frappe.cache.set_value(memory_key(user), turns[-MEMORY_TURNS:], expires_in_sec=MEMORY_TTL)


def forget(user):
	frappe.cache.delete_value(memory_key(user))


def memory_text(turns):
	if not turns:
		return "(no earlier turn)"
	return "\n".join(f"Q: {t['q']}\nA: {t['a']}\nFacts: {t['facts']}" for t in turns)


# ---------------- executor ----------------


def compact(name, text, is_error):
	"""What of a tool's result goes to the synthesizer: errors as they are; a report's columns and first rows; the
	dashboard's cards and the band's totals; a list's rows up to a limit."""
	if is_error:
		return text[:600]
	try:
		data = json.loads(text)
	except ValueError:
		return text[:MAX_CHARS_TO_MODEL]
	if name == "dashboard_today":
		band = data.get("band") or {}
		money = band.get("money") or {}
		keep = {
			"cards": data.get("cards"),
			"day": band.get("day"),
			"ledger_entries_all_time": band.get("ledger_entries_all_time"),
			"money_today": {"rows": [{k: r.get(k) for k in ("business", "revenue", "expenses", "net", "external", "bookings", "paid", "due", "package_bookings")} for r in money.get("rows") or []], "total": money.get("total"), "ledger_entries_today": money.get("ledger_entries")},
			"bookings_today": band.get("bookings"),
			"halls": band.get("halls"),
			"app_fees": band.get("app"),
			"printing_warnings": (band.get("printing") or {}).get("warnings"),
			"systems": [{"name": s.get("name"), "state": s.get("state"), "detail": (s.get("detail") or "")[:160]} for s in band.get("systems") or []],
		}
		data = keep
	elif name in ("run_report", "list_records"):
		rows = data.get("rows") or []
		data = {**data, "rows": rows[:MAX_ROWS_TO_MODEL], "rows_shown": min(len(rows), MAX_ROWS_TO_MODEL), "rows_total": data.get("rows_total", len(rows))}
	out = json.dumps(data, ensure_ascii=False, default=str)
	return out if len(out) <= MAX_CHARS_TO_MODEL else out[:MAX_CHARS_TO_MODEL] + " ...(cut)"


def execute(steps):
	results = []
	for step in steps[:MAX_PLAN_STEPS]:
		name = step.get("tool")
		try:
			args = step.get("arguments")
			args = json.loads(args) if isinstance(args, str) else (args or {})
		except ValueError:
			args = {}
		text, is_error = run_tool(name, args)
		results.append({"tool": name, "arguments": args, "error": is_error, "result": compact(name, text, is_error)})
	return results


def results_text(results):
	return "\n\n".join(f"[{i + 1}] {r['tool']} {json.dumps(r['arguments'], ensure_ascii=False)}\n{r['result']}" for i, r in enumerate(results))


# ---------------- the agent ----------------


def parse_plan(text):
	try:
		plan = json.loads(text)
	except ValueError:
		start, end = text.find("{"), text.rfind("}")
		plan = json.loads(text[start : end + 1]) if start >= 0 and end > start else {}
	steps = [s for s in (plan.get("steps") or []) if isinstance(s, dict) and s.get("tool")]
	return steps, bool(plan.get("may_need_more")), (plan.get("answer_without_reading") or "").strip()


def run(question, context, complete, history=None, chat=None):
	"""Plan, read, answer. `complete(system, prompt, json_schema=None)` is the provider's one model call. With a
	saved chat (chats.py) the memory is the chat's: its summary of the older turns and the last messages as said;
	without one, the short cache memory of this user."""
	user = context.get("user")
	if chat:
		from imed_erp.assistant import chats

		chats.fold(chat, complete)  # the older turns into the summary, when enough of them have left the window
		memo = chats.memory_text(chat)
	else:
		memo = memory_text(recall(user))
	header = f"[{user_context_line(context)}]"
	plan_prompt = f"{header}\n\nTools:\n{catalogue()}\n\nMemory of this conversation:\n{memo}\n\nQuestion: {question}"
	steps, may_need_more, direct = parse_plan(complete(PLANNER, plan_prompt, PLAN_SCHEMA))
	if direct and not steps:
		if not chat:
			remember(user, question, direct, "")
		return direct

	results = execute(steps)
	answer_prompt = f"{header}\n\nMemory of this conversation:\n{memo}\n\nQuestion: {question}\n\nResults of the reads:\n{results_text(results)}"
	if may_need_more:
		answer_prompt += '\n\nIf one more read is needed to answer, reply with exactly: NEED {"tool": ..., "arguments": {...}} and nothing else.'
	answer = complete(SYNTHESIZER, answer_prompt).strip()
	if may_need_more and answer.startswith("NEED "):
		try:
			more = json.loads(answer[5:])
			results += execute([more])
		except ValueError:
			pass
		answer_prompt = f"{header}\n\nMemory of this conversation:\n{memo}\n\nQuestion: {question}\n\nResults of the reads:\n{results_text(results)}"
		answer = complete(SYNTHESIZER, answer_prompt).strip()
	facts = "; ".join(f"{r['tool']}: {r['result'][:200]}" for r in results)
	answer = answer or _("I found nothing to say; try asking in another way.")
	if chat:
		context["facts"] = facts  # the API saves the turn with its facts
	else:
		remember(user, question, answer, facts)
	return answer
