# The contracts the assistant is built on. Each is a Protocol: anything with the right members fits, no base class
# needed. The orchestration depends on these only (dependency inversion), so a model, a memory, a tool catalogue
# or a business integration can be swapped or added without touching it.

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from imed_erp.assistant.core.context import RequestContext

JsonSchema = dict[str, Any]


class Completer(Protocol):
	"""One model call: text in, text out; JSON of `json_schema`'s shape when one is given."""

	def __call__(self, system: str, prompt: str, json_schema: JsonSchema | None = None) -> str: ...


@runtime_checkable
class ModelProvider(Protocol):
	name: str
	connected: bool
	supports_voice: bool

	def complete(self, system: str, prompt: str, json_schema: JsonSchema | None = None) -> str: ...

	def transcribe(self, audio: bytes, mime_type: str, context: RequestContext) -> str | None: ...


@runtime_checkable
class Tool(Protocol):
	"""A read the model may ask for. The spec may depend on who asks; `run` reads as that user and must not write."""

	name: str

	def spec(self, context: RequestContext) -> dict[str, Any]: ...

	def run(self, arguments: dict[str, Any], context: RequestContext) -> Any: ...


@runtime_checkable
class BusinessIntegration(Protocol):
	"""An integration contributes a business domain to the assistant, independently of the core:

	- `businesses`: the business units it covers, as the asking user may see them (for the prompt);
	- `doctypes`, `reports`, `workspaces`: what the common read tools may reach for that user;
	- `tools`: reads of its own (its own services, data sources, permission checks);
	- `prompt_notes`: rules of meaning specific to its domain ("held" bookings, an external system's "due").

	Integrations are registered in an app's hooks.py under `assistant_businesses` (registry/businesses.py)."""

	key: str
	label: str

	def businesses(self, context: RequestContext) -> list[str]: ...

	def doctypes(self, context: RequestContext) -> list[str]: ...

	def reports(self, context: RequestContext) -> list[dict[str, str]]: ...

	def workspaces(self, context: RequestContext) -> list[str]: ...

	def tools(self, context: RequestContext) -> list[Tool]: ...

	def prompt_notes(self, context: RequestContext) -> str: ...


class ToolCatalog(Protocol):
	"""What the orchestrator needs of the tools of a request."""

	def names(self) -> list[str]: ...

	def catalogue(self, context: RequestContext) -> str: ...

	def business_labels(self) -> list[str]: ...

	def prompt_notes(self) -> str: ...

	def run(self, name: str, arguments: dict[str, Any], context: RequestContext) -> tuple[str, bool]: ...


@runtime_checkable
class ConversationMemory(Protocol):
	"""What the model is told of the conversation so far, and how a finished turn is kept."""

	def context_text(self, context: RequestContext) -> str: ...

	def record(self, context: RequestContext, question: str, answer: str, facts: str) -> None: ...

	def fold(self, context: RequestContext, complete: Completer) -> bool: ...
