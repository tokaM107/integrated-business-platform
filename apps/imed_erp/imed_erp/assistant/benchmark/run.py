# Run the assistant's benchmark (cases.py) and score it. Each question goes through the real flow (planner, reads,
# answer) as the given user, with a fresh memory (nothing saved, nothing written: the reads are read-only); the
# right answer is worked out from the ERP at the same moment (the cases' oracles). It calls the configured models,
# which costs money: it refuses to run without paid_calls=1.
#
#   bench --site <site> execute imed_erp.assistant.benchmark.run.run --kwargs '{"paid_calls": 1}'
#   options: user (default owner@imed.local), only ("H02,H07"), repeat (default 1), out (a folder)
#
# Writes results.json (every run: plan, reads, answer, timings, scores), results.csv and summary.md (the numbers)
# under sites/<site>/private/assistant-benchmark/<timestamp>/, and prints the summary.

from __future__ import annotations

import csv
import json
import os
import re
import statistics
import time

import frappe
from frappe.utils import now_datetime

from imed_erp.assistant.benchmark.cases import CASES

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")
NO_DATA = re.compile(r"مفيش|ما فيش|مش متسجل|مش موجود|لسه ما|مالهاش|مش بيتسجل|مش متاح|ما بيتسجلش|لا توجد|no record|not (in|tracked)", re.I)
READ_ONLY = re.compile(r"بقرأ بس|بقرا بس|مش بقدر|ما أقدرش|ما اقدرش|مقدرش|من الشاشة|من شاشة|في الـ?ERP|read-only|only read", re.I)
MSA = re.compile(r"لدينا|لا يوجد|اليوم\b|تم |أخبرني|لم أ|سوف |هناك ")
EGYPTIAN = re.compile(r"عندنا|النهارده|مفيش|ده|دي|اتعمل|بتاع|كام|لسه|عشان|علشان|دلوقتي")
MARKDOWN = re.compile(r"\*\*|^#|^\s*[-*•]\s|\|.*\|", re.M)


def numbers_in(text: str) -> list[float]:
	text = (text or "").translate(ARABIC_DIGITS).replace("٬", "").replace(",", "")
	return [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)]


def has_number(answer: str, value: float) -> bool:
	found = numbers_in(answer)
	if not value:
		return any(n == 0 for n in found) or bool(NO_DATA.search(answer))
	return any(abs(n - value) <= max(0.01 * abs(value), 0.5 if float(value).is_integer() else 0.01) for n in found)


def score(case, oracle: dict, answer: str, tools_used: list[str], tool_errors: int) -> dict:
	"""Each score in 0..1. correct: the answer holds what the oracle says (or says honestly that it cannot);
	grounded: it read what holds the answer, and gave no figure the ERP does not have; style: Arabic, Egyptian, plain."""
	notes = []
	if case.kind == "readonly":
		correct = 1.0 if READ_ONLY.search(answer) or "تنبيه" in answer or "Reorder" in answer else 0.0
	elif case.kind == "unavailable" and not oracle.get("available", False):
		invented = [n for n in numbers_in(answer) if n not in (9, 30, 9.5)]  # the question's own "9:30" is not an invented figure
		correct = 1.0 if NO_DATA.search(answer) and not invented else 0.0
		if invented:
			notes.append(f"gave figures for data the ERP does not hold: {invented[:5]}")
	elif not oracle.get("has_records", True):
		correct = 1.0 if NO_DATA.search(answer) else 0.0
		if not correct:
			notes.append("the ERP holds no records for this; the answer did not say so")
	else:
		facts = oracle.get("facts") or {}
		items = oracle.get("items") or []
		hits = [k for k, v in facts.items() if has_number(answer, v)]
		named = [i for i in items if i and str(i).split(" - ")[0] in answer]
		parts = []
		if facts:
			parts.append(len(hits) / len(facts))
			if len(hits) < len(facts):
				notes.append(f"figures missing: {[k for k in facts if k not in hits][:6]}")
		if case.kind == "list" and items:
			parts.append(len(named) / len(items))
			if len(named) < len(items):
				notes.append(f"items missing: {[i for i in items if i not in named][:6]}")
		correct = round(sum(parts) / len(parts), 2) if parts else 0.0
		if oracle.get("ink_tracked") is False and "حبر" in case.question.replace("أحبار", "حبر").replace("الأحبار", "حبر"):
			# Ink is not a stock item: half the answer is saying so.
			honest = bool(NO_DATA.search(answer)) and ("حبر" in answer or "أحبار" in answer or "الأحبار" in answer)
			correct = round((correct + (1.0 if honest else 0.0)) / 2, 2)
			if not honest:
				notes.append("did not say the ink is not tracked")
	expected = set(case.expected_tools)
	grounded = 1.0 if (not expected or expected & set(tools_used)) else 0.0
	if case.kind in ("unavailable", "readonly"):
		grounded = 1.0
	arabic = len(re.findall(r"[؀-ۿ]", answer)) >= 0.5 * max(1, len(re.findall(r"[A-Za-z؀-ۿ]", answer)))
	style = round((arabic + (not MSA.search(answer)) + bool(EGYPTIAN.search(answer)) + (not MARKDOWN.search(answer))) / 4, 2)
	if MSA.search(answer):
		notes.append(f"MSA: {MSA.search(answer).group(0)}")
	if MARKDOWN.search(answer):
		notes.append("markdown in the answer")
	if tool_errors:
		notes.append(f"{tool_errors} read(s) failed")
	return {"correct": correct, "grounded": grounded, "style": style, "notes": "; ".join(notes)}


def ask(case, user):
	"""One question through the real flow, timed; nothing saved."""
	from imed_erp.assistant.core.context import build_context
	from imed_erp.assistant.core.orchestration import Orchestrator
	from imed_erp.assistant.memory.request_memory import RequestMemory
	from imed_erp.assistant.providers import get_provider
	from imed_erp.assistant.registry.businesses import discover
	from imed_erp.assistant.registry.tools import ToolRegistry

	frappe.set_user(user)
	context = build_context()
	provider = get_provider()
	calls, reads, first = [], [], []
	started = time.monotonic()

	def complete(system, prompt, json_schema=None, on_text=None):
		t = time.monotonic()
		out = provider.complete(system, prompt, json_schema, on_text) if on_text else provider.complete(system, prompt, json_schema)
		calls.append({"step": "plan" if json_schema else "answer", "seconds": round(time.monotonic() - t, 2), "prompt_chars": len(system) + len(prompt), "output_chars": len(out or "")})
		return out

	def on_text(piece):
		if not first:
			first.append(round(time.monotonic() - started, 2))

	registry = ToolRegistry(discover(context), context)
	run_tool = registry.run

	def timed_run(name, arguments, ctx):
		t = time.monotonic()
		text, is_error = run_tool(name, arguments, ctx)
		reads.append({"tool": name, "arguments": arguments, "error": is_error, "seconds": round(time.monotonic() - t, 3), "result": text[:600]})
		return text, is_error

	registry.run = timed_run
	try:
		answer, _facts = Orchestrator(complete, registry, RequestMemory([]), on_text=on_text).answer(case.question, context)
		failure = ""
	except Exception as e:
		answer, failure = "", f"{type(e).__name__}: {str(e)[:300]}"
	return {
		"answer": answer, "failure": failure, "provider": provider.name, "model": getattr(provider, "model", ""),
		"planner_model": getattr(provider, "planner_model", ""), "calls": calls, "reads": reads,
		"first_words_s": first[0] if first else None, "total_s": round(time.monotonic() - started, 2), "company": context.company,
	}


def run(paid_calls=0, user="owner@imed.local", only=None, repeat=1, out=None):
	if not int(paid_calls or 0):
		print("REFUSED: the benchmark calls the configured models (paid). Run it with --kwargs '{\"paid_calls\": 1}'.")
		return
	wanted = {c.strip() for c in (only or "").split(",") if c.strip()}
	cases = [c for c in CASES if not wanted or c.id in wanted]
	folder = out or os.path.join(frappe.get_site_path("private", "assistant-benchmark"), now_datetime().strftime("%Y%m%d-%H%M%S"))
	os.makedirs(folder, exist_ok=True)
	results = []
	for case in cases:
		for attempt in range(int(repeat or 1)):
			frappe.set_user("Administrator")
			company = frappe.defaults.get_global_default("company")
			try:
				oracle = case.oracle(company) if case.oracle else {"available": False}
			except Exception as e:
				oracle = {"available": False, "oracle_error": f"{type(e).__name__}: {e}"}
			asked = ask(case, user)
			tools_used = [r["tool"] for r in asked["reads"]]
			scores = score(case, oracle, asked["answer"], tools_used, sum(1 for r in asked["reads"] if r["error"])) if not asked["failure"] else {"correct": 0.0, "grounded": 0.0, "style": 0.0, "notes": asked["failure"]}
			results.append({"id": case.id, "attempt": attempt + 1, "question": case.question, "kind": case.kind, "category": case.category,
				"uncertain_reading": case.uncertain, "oracle": oracle, **asked, "tools_used": tools_used, **scores})
			print(f"{case.id} correct {scores['correct']} grounded {scores['grounded']} style {scores['style']} | {asked['total_s']} s | {asked['answer'][:90]}")
			frappe.db.rollback()
	frappe.set_user("Administrator")
	with open(os.path.join(folder, "results.json"), "w", encoding="utf-8") as f:
		json.dump(results, f, ensure_ascii=False, indent=1, default=str)
	with open(os.path.join(folder, "results.csv"), "w", encoding="utf-8", newline="") as f:
		w = csv.writer(f)
		w.writerow(["id", "attempt", "kind", "category", "correct", "grounded", "style", "first_words_s", "total_s", "plan_s", "answer_s", "reads", "read_errors", "notes", "question", "answer"])
		for r in results:
			plan = sum(c["seconds"] for c in r["calls"] if c["step"] == "plan")
			ans = sum(c["seconds"] for c in r["calls"] if c["step"] == "answer")
			w.writerow([r["id"], r["attempt"], r["kind"], r["category"], r["correct"], r["grounded"], r["style"], r["first_words_s"], r["total_s"], round(plan, 2), round(ans, 2),
				len(r["reads"]), sum(1 for x in r["reads"] if x["error"]), r["notes"], r["question"], r["answer"]])
	summary = summarize(results)
	with open(os.path.join(folder, "summary.md"), "w", encoding="utf-8") as f:
		f.write(summary)
	print("\n" + summary + f"\nFiles: {folder}")
	return {"folder": folder, "cases": len(results)}


def summarize(results: list[dict]) -> str:
	def pct(values):
		return f"{100 * statistics.mean(values):.0f}%" if values else "-"

	def p(values, q):
		values = sorted(v for v in values if v is not None)
		return f"{values[min(len(values) - 1, int(q * len(values)))]:.1f} s" if values else "-"

	lines = [
		"# Assistant benchmark",
		"",
		f"Runs: {len(results)} · model {results[0]['model'] if results else '-'} · planner {results[0]['planner_model'] if results else '-'}",
		"",
		"| Measure | Value |",
		"|---|---|",
		f"| Correct (mean) | {pct([r['correct'] for r in results])} |",
		f"| Fully correct answers | {sum(1 for r in results if r['correct'] >= 1)} of {len(results)} |",
		f"| Grounded (read the right source) | {pct([r['grounded'] for r in results])} |",
		f"| Style (Arabic, Egyptian, plain text) | {pct([r['style'] for r in results])} |",
		f"| Honest when the ERP has no data | {pct([r['correct'] for r in results if r['kind'] in ('unavailable',) or not r['oracle'].get('has_records', True)])} |",
		f"| First words, median / 90th | {p([r['first_words_s'] for r in results], 0.5)} / {p([r['first_words_s'] for r in results], 0.9)} |",
		f"| Whole answer, median / 90th | {p([r['total_s'] for r in results], 0.5)} / {p([r['total_s'] for r in results], 0.9)} |",
		f"| Reads that failed | {sum(1 for r in results for x in r['reads'] if x['error'])} of {sum(len(r['reads']) for r in results)} |",
		f"| Questions that crashed | {sum(1 for r in results if r['failure'])} |",
		"",
		"| By category | Correct | Runs |",
		"|---|---|---|",
	]
	for category in sorted({r["category"] for r in results}):
		rows = [r for r in results if r["category"] == category]
		lines.append(f"| {category} | {pct([r['correct'] for r in rows])} | {len(rows)} |")
	lines += ["", "| Case | Correct | Grounded | Style | Total | Notes |", "|---|---|---|---|---|---|"]
	for r in results:
		lines.append(f"| {r['id']}{' (?)' if r['uncertain_reading'] else ''} | {r['correct']} | {r['grounded']} | {r['style']} | {r['total_s']} s | {(r['notes'] or '').replace('|', '/')[:120]} |")
	lines += ["", "(?) the handwriting's reading is to be confirmed with the owner.", ""]
	return "\n".join(lines)
