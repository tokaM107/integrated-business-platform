# Which model answers: `imed_assistant_provider` in the site config, a built-in name (gemini, claude, offline) or a
# dotted path to a ModelProvider class. Unset, the offline placeholder: the assistant says it is not connected.

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


def setting() -> str:
	"""Which provider answers. IMED_ASSISTANT_PROVIDER in the environment decides when set; otherwise Claude whenever
	an Anthropic key is there (owner, 2 Nov 2026: "use it instead of Gemini"), else the site config's
	imed_assistant_provider, else Gemini when a Gemini key is there, else the offline placeholder."""
	import os

	from imed_erp.assistant.providers.claude import anthropic_key
	from imed_erp.assistant.providers.gemini import gemini_key

	chosen = os.environ.get("IMED_ASSISTANT_PROVIDER") or ("claude" if anthropic_key() else frappe.conf.get("imed_assistant_provider"))
	if not chosen:
		chosen = "gemini" if gemini_key() else "offline"
	return LEGACY.get(chosen, chosen)


def get_provider() -> AssistantProvider:
	chosen = setting()
	return frappe.get_attr(BUILT_IN.get(chosen, chosen))()


def voice_provider(provider: AssistantProvider) -> AssistantProvider:
	"""Who hears and speaks: ElevenLabs when its key is set (owner, 4 Nov 2026: the voice is ElevenLabs', never
	Gemini's when another model answers), else the answering provider itself (Gemini has a voice when it answers;
	Claude has none, and the browser reads then)."""
	from imed_erp.assistant.providers.elevenlabs import ElevenLabsVoice, elevenlabs_key

	return ElevenLabsVoice() if elevenlabs_key() else provider


speech_provider = voice_provider  # reading aloud and writing out recordings go to the same voice


__all__ = ["AssistantProvider", "OfflineProvider", "get_provider", "voice_provider", "speech_provider"]
