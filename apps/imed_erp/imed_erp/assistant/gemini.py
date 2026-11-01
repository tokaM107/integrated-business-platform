# The Gemini provider of the assistant (assistant/tools.py holds the tools and the instructions; read-only).
#
# Connect it (docs/ASSISTANT.md):
#   bench --site frontend set-config imed_assistant_provider imed_erp.assistant.gemini.GeminiProvider
#   bench --site frontend set-config imed_assistant_api_key AIza...            # a Gemini API key (Google AI Studio)
#   bench --site frontend set-config imed_assistant_model gemini-3.5-flash          # optional; this is the default
#
# Package: google-genai (pyproject.toml). The model gets the same five read tools as any provider, as function
# declarations; it calls, we run the tool as the asking user, we hand the result back, until it answers in text.

import json

import frappe
from frappe import _

from imed_erp.assistant.providers import AssistantProvider
from imed_erp.assistant.tools import MAX_TOOL_ROUNDS, SYSTEM, TOOLS, run_tool, user_context_line

# Tried on 1 Nov 2026 with the owner's key: gemini-3.1-pro-preview is over its quota (needs billing), gemini-3.8-flash
# ran 70-170 s a call under "high demand"; gemini-3.5-flash answered correctly in 14 s. The site config may change it.
DEFAULT_MODEL = "gemini-3.5-flash"


class QuotaExceeded(Exception):
	pass


class ModelOverloaded(Exception):
	pass


def function_declarations():
	"""The tools as Gemini function declarations (OpenAPI-style schemas; no 'strict', no 'additionalProperties')."""
	from google.genai import types

	def clean(schema):
		if isinstance(schema, dict):
			return {k: clean(v) for k, v in schema.items() if k not in ("additionalProperties", "strict")}
		if isinstance(schema, list):
			return [clean(v) for v in schema]
		return schema

	return [
		types.FunctionDeclaration(name=t["name"], description=t["description"], parameters=clean(t["input_schema"]))
		for t in TOOLS
	]


class GeminiProvider(AssistantProvider):
	name = "gemini"
	connected = True
	supports_voice = False  # the reply is read aloud in the browser; speech-to-text is a later step

	def __init__(self):
		self.api_key = frappe.conf.get("imed_assistant_api_key")
		self.model = frappe.conf.get("imed_assistant_model") or DEFAULT_MODEL
		self.connected = bool(self.api_key)

	def client(self):
		from google import genai

		if not self.api_key:
			raise frappe.ValidationError(_("The assistant has no API key (site config imed_assistant_api_key)."))
		# One client per provider instance: a client made per call was garbage-collected between the agent's two
		# calls and its HTTP session closed ("Cannot send a request, as the client has been closed").
		if not getattr(self, "_client", None):
			self._client = genai.Client(api_key=self.api_key)
		return self._client

	def complete(self, system, prompt, json_schema=None):
		"""One model call for the agent (assistant/agent.py): text in, text out; JSON out when a schema is given."""
		from google.genai import types

		config = types.GenerateContentConfig(system_instruction=system, temperature=0.1, max_output_tokens=4000)
		if json_schema:
			config.response_mime_type = "application/json"
			config.response_schema = json_schema
		try:
			response = self.client().models.generate_content(model=self.model, contents=prompt, config=config)
		except Exception as e:
			code = getattr(e, "code", None) or getattr(e, "status_code", None)
			if code == 429:
				raise QuotaExceeded()
			if code == 503:
				raise ModelOverloaded()
			raise
		return response.text or ""

	def reply(self, messages, context):
		"""Planner -> Executor -> Synthesizer with the short memory (two model calls a question, three at most)."""
		from imed_erp.assistant import agent

		try:
			return agent.run(messages[-1]["content"], context, self.complete)
		except QuotaExceeded:
			return _("The model's quota for this key is used up for now (Google's limit). Try again in a minute, or raise the key's quota in Google AI Studio.")
		except ModelOverloaded:
			return _("The model is overloaded at Google's side right now. Try again in a moment.")

	def reply_react(self, messages, context):
		"""The earlier tool-calling loop (one model call per read); kept for comparison, not used."""
		from google.genai import types

		client = self.client()
		contents = []
		for i, m in enumerate(messages):
			text = m["content"]
			if i == 0:
				text = f"[{user_context_line(context)}]\n\n{text}"
			contents.append(types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part.from_text(text=text)]))
		config = types.GenerateContentConfig(
			system_instruction=SYSTEM,
			tools=[types.Tool(function_declarations=function_declarations())],
			# The tools are ours: the SDK must not call anything on its own.
			automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
			temperature=0.2,
			max_output_tokens=8000,
		)
		rounds = 0
		while True:
			try:
				response = client.models.generate_content(model=self.model, contents=contents, config=config)
			except Exception as e:
				# Said as it is: the model's quota or availability is not the ERP's fault, and the owner should know
				# which (a 429 is the key's quota, a 503 the model's demand); anything else is logged by the API layer.
				code = getattr(e, "code", None) or getattr(e, "status_code", None)
				if code == 429:
					return _("The model's quota for this key is used up for now (Google's limit). Try again in a minute, or raise the key's quota in Google AI Studio.")
				if code == 503:
					return _("The model is overloaded at Google's side right now. Try again in a moment.")
				raise
			candidate = response.candidates[0] if response.candidates else None
			if not candidate or not candidate.content or not candidate.content.parts:
				return _("I cannot answer that question.")
			calls = [p.function_call for p in candidate.content.parts if getattr(p, "function_call", None)]
			if not calls:
				break
			rounds += 1
			contents.append(candidate.content)
			results = []
			for call in calls:
				if rounds > MAX_TOOL_ROUNDS:
					text, is_error = json.dumps({"error": "too many reads for one question: answer with what you have"}), True
				else:
					text, is_error = run_tool(call.name, dict(call.args or {}))
				payload = {"error": text} if is_error else {"result": text}
				results.append(types.Part.from_function_response(name=call.name, response=payload))
			contents.append(types.Content(role="user", parts=results))
		text = "".join(p.text for p in candidate.content.parts if getattr(p, "text", None)).strip()
		if getattr(candidate, "finish_reason", None) and str(candidate.finish_reason).endswith("MAX_TOKENS"):
			text += "\n\n" + _("(The answer was cut short; ask a narrower question.)")
		return text or _("I found nothing to say; try asking in another way.")
