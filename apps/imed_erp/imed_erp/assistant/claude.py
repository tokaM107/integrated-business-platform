# The Claude provider of the assistant (assistant/tools.py holds the tools and the instructions; read-only).
#
# Connect it (docs/assistant/assistant.md):
#   bench --site frontend set-config imed_assistant_provider imed_erp.assistant.claude.ClaudeProvider
#   bench --site frontend set-config imed_assistant_api_key sk-ant-...      # the site's config, never in git
#   bench --site frontend set-config imed_assistant_model claude-opus-5-5   # optional
#
# Package: anthropic (pyproject.toml). The conversation lives in the browser; each call is stateless.

import json

import frappe
from frappe import _

from imed_erp.assistant.providers import AssistantProvider
from imed_erp.assistant.tools import MAX_TOOL_ROUNDS, SYSTEM, TOOLS, run_tool, user_context_line

DEFAULT_MODEL = "claude-opus-5-5"


class ClaudeProvider(AssistantProvider):
	name = "claude"
	connected = True
	supports_voice = False  # speech is turned to text in the browser; the reply is read aloud there too

	def __init__(self):
		self.api_key = frappe.conf.get("imed_assistant_api_key")
		self.model = frappe.conf.get("imed_assistant_model") or DEFAULT_MODEL
		self.connected = bool(self.api_key)

	def client(self):
		import anthropic

		if not self.api_key:
			raise frappe.ValidationError(_("The assistant has no API key (site config imed_assistant_api_key)."))
		return anthropic.Anthropic(api_key=self.api_key, max_retries=2, timeout=120.0)

	def complete(self, system, prompt, json_schema=None):
		"""One model call for the agent (assistant/agent.py)."""
		kwargs = {}
		if json_schema:
			kwargs["output_config"] = {"effort": "low", "format": {"type": "json_schema", "schema": json_schema}}
		response = self.client().messages.create(
			model=self.model, max_tokens=4000, system=system, messages=[{"role": "user", "content": prompt}], **kwargs
		)
		return "".join(b.text for b in response.content if b.type == "text")

	def reply(self, messages, context):
		from imed_erp.assistant import agent

		return agent.run(messages[-1]["content"], context, self.complete)

	def reply_react(self, messages, context):
		"""The earlier tool-calling loop (one model call per read); kept for comparison, not used."""
		client = self.client()
		conversation = [dict(m) for m in messages]
		# The first user turn carries who asks and the date; the system prompt stays byte-identical for the cache.
		conversation[0] = {"role": "user", "content": f"[{user_context_line(context)}]\n\n{conversation[0]['content']}"}
		rounds = 0
		while True:
			response = client.beta.messages.create(
				model=self.model,
				max_tokens=8000,
				system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
				tools=TOOLS,
				messages=conversation,
				output_config={"effort": "high"},
				betas=["server-side-fallback-2026-07-01"],
				fallbacks="default",
			)
			if response.stop_reason == "refusal":
				return _("I cannot answer that question.")
			if response.stop_reason == "pause_turn":
				conversation.append({"role": "assistant", "content": response.content})
				continue
			tool_uses = [b for b in response.content if b.type == "tool_use"]
			if response.stop_reason != "tool_use" or not tool_uses:
				break
			rounds += 1
			conversation.append({"role": "assistant", "content": response.content})
			results = []
			for use in tool_uses:
				if rounds > MAX_TOOL_ROUNDS:
					text, is_error = json.dumps({"error": "too many reads for one question: answer with what you have"}), True
				else:
					text, is_error = run_tool(use.name, use.input)
				results.append({"type": "tool_result", "tool_use_id": use.id, "content": text, "is_error": is_error})
			conversation.append({"role": "user", "content": results})
		text = "\n".join(b.text for b in response.content if b.type == "text").strip()
		if response.stop_reason == "max_tokens":
			text += "\n\n" + _("(The answer was cut short; ask a narrower question.)")
		return text or _("I found nothing to say; try asking in another way.")
