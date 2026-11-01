# The Gemini provider of the assistant (assistant/tools.py holds the tools and the instructions; read-only).
#
# Connect it (docs/ASSISTANT.md):
#   bench --site frontend set-config imed_assistant_provider imed_erp.assistant.gemini.GeminiProvider
#   bench --site frontend set-config imed_assistant_api_key AIza...            # a Gemini API key (Google AI Studio)
#   bench --site frontend set-config imed_assistant_model gemini-3.1-pro-preview   # optional; this is the default
#
# Package: google-genai (pyproject.toml). The model gets the same five read tools as any provider, as function
# declarations; it calls, we run the tool as the asking user, we hand the result back, until it answers in text.

import json

import frappe
from frappe import _

from imed_erp.assistant.providers import AssistantProvider
from imed_erp.assistant.tools import MAX_TOOL_ROUNDS, SYSTEM, TOOLS, run_tool, user_context_line

DEFAULT_MODEL = "gemini-3.1-pro-preview"


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
		return genai.Client(api_key=self.api_key)

	def reply(self, messages, context):
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
			response = client.models.generate_content(model=self.model, contents=contents, config=config)
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
