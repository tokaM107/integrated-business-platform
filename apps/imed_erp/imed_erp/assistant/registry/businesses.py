# Where the assistant learns which businesses exist: the app's Workspace Sidebars (every section is one), plus any
# integration another app or module registers through the `assistant_businesses` hook (a dotted path to a callable
# returning BusinessIntegration objects). Adding a business = a sidebar section, or one hook entry; the core
# does not change.

from __future__ import annotations

import frappe

from imed_erp.assistant.businesses.sidebar import from_sidebars
from imed_erp.assistant.core.context import RequestContext
from imed_erp.assistant.core.interfaces import BusinessIntegration

APP = "imed_erp"
HOOK = "assistant_businesses"


def hooked_paths() -> list[str]:
	return list(frappe.get_hooks(HOOK) or [])


def load(path: str):
	return frappe.get_attr(path)


def discover(context: RequestContext) -> list[BusinessIntegration]:
	found: list[BusinessIntegration] = list(from_sidebars(APP))
	for path in hooked_paths():
		found.extend(load(path)(context) or [])
	return found
