# The contracts the assistant is built on. Each is a Protocol: anything with the right methods fits, no base class
# needed. The orchestration depends on these only (dependency inversion), so a model, a memory or a business can be
# swapped or added without touching it.

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from imed_erp.assistant.core.context import RequestContext

JsonSchema = dict[str, Any]


@runtime_checkable
class ModelProvider(Protocol):
	"""One model call. `complete` returns text; with `json_schema` the text is JSON of that shape."""

	name: str
	connected: bool
	supports_voice: bool

	def complete(self, system: str, prompt: str, json_schema: JsonSchema | None = None) -> str: ...

	def transcribe(self, audio: bytes, mime_type: str, context: RequestContext) -> str | None: ...


class Completer(Protocol):
	def __call__(self, system: str, prompt: str, json_schema: JsonSchema | None = None) -> str: ...


@runtime_checkable
class Tool(Protocol):
	"""A read the model may ask for. The spec may depend on who asks (what they may read); `run` reads as that user."""

	name: str

	def spec(self, context: RequestContext) -> dict[str, Any]: ...

	def run(self, arguments: dict[str, Any], context: RequestContext) -> Any: ...


@runtime_checkable
class BusinessIntegration(Protocol):
	"""A business area of the ERP: what it is called and what the assistant may read of it. The registry discovers
	them from the system (the app's Workspace Sidebars) and from the `assistant_businesses` hook."""

	key: str
	label: str

	def doctypes(self, context: RequestContext) -> list[str]: ...

	def reports(self, context: RequestContext) -> list[dict[str, str]]: ...

	def tools(self, context: RequestContext) -> list[Tool]: ...


@runtime_checkable
class ConversationMemory(Protocol):
	"""What the model is told of the conversation so far, and how a finished turn is kept."""

	def context_text(self, context: RequestContext) -> str: ...

	def record(self, context: RequestContext, question: str, answer: str, facts: str) -> None: ...

	def fold(self, context: RequestContext, complete: Completer) -> bool: ...
