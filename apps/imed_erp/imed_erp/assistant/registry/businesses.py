# Which integrations the assistant has: whatever the installed apps register under the `assistant_businesses` hook
# (dotted paths to callables `f(context) -> list[BusinessIntegration]`). The registry knows no business, no sidebar
# and no app: an integration is added or removed in its own app's hooks.py, and the core does not change.

from __future__ import annotations

import frappe

from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.interfaces import BusinessIntegration

HOOK = "assistant_businesses"


def hooked_paths() -> list[str]:
	return list(frappe.get_hooks(HOOK) or [])


def load(path: str):
	return frappe.get_attr(path)


def discover(context: RequestContext) -> list[BusinessIntegration]:
	found: list[BusinessIntegration] = []
	for path in hooked_paths():
		for integration in load(path)(context) or []:
			if not isinstance(integration, BusinessIntegration):
				raise TypeError(f"{path} returned {integration!r}, which does not fulfil BusinessIntegration")
			found.append(integration)
	return found
