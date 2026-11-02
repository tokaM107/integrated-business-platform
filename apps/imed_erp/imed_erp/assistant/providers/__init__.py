# Which model answers: `imed_assistant_provider` in the site config, a built-in name (gemini, claude, offline) or a
# dotted path to a ModelProvider class. The offline placeholder answers until a model is configured.

from __future__ import annotations

import frappe

from imed_erp.assistant.providers.base import AssistantProvider, OfflineProvider

BUILT_IN = {
	"offline": "imed_erp.assistant.providers.base.OfflineProvider",
	"gemini": "imed_erp.assistant.providers.gemini.GeminiProvider",
	"claude": "imed_erp.assistant.providers.claude.ClaudeProvider",
}
# The paths used before the package was reorganised (2 Nov 2026): a site configured with one keeps working.
LEGACY = {
	"imed_erp.assistant.gemini.GeminiProvider": "gemini",
	"imed_erp.assistant.claude.ClaudeProvider": "claude",
	"imed_erp.assistant.providers.OfflineProvider": "offline",
}


def get_provider() -> AssistantProvider:
	setting = frappe.conf.get("imed_assistant_provider") or "offline"
	setting = LEGACY.get(setting, setting)
	return frappe.get_attr(BUILT_IN.get(setting, setting))()


__all__ = ["AssistantProvider", "OfflineProvider", "get_provider"]
