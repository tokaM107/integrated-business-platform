# Who is asking, in which language, for which company, in which chat: resolved once per request from Frappe's
# session and defaults, never guessed. Carried through every layer; nothing here is global.

from __future__ import annotations

from dataclasses import dataclass, field

import frappe
from frappe.utils import get_first_day, get_last_day, nowdate


@dataclass(frozen=True)
class RequestContext:
	user: str
	full_name: str
	lang: str
	company: str
	currency: str
	chat: str | None = None
	today: str = field(default_factory=nowdate)

	@property
	def is_arabic(self) -> bool:
		return self.lang.startswith("ar")

	def header(self) -> str:
		"""One line the model gets with every request: who, when, which company."""
		return (
			f"Asking user: {self.full_name} ({self.user}). Today: {self.today}. "
			f"This month: {get_first_day(self.today)} to {get_last_day(self.today)}. "
			f"Company: {self.company} ({self.currency}). Language: {self.lang}."
		)


def build_context(chat: str | None = None) -> RequestContext:
	company = frappe.defaults.get_user_default("company") or frappe.defaults.get_global_default("company")
	currency = frappe.get_cached_value("Company", company, "default_currency") if company else ""
	return RequestContext(
		user=frappe.session.user,
		full_name=frappe.utils.get_fullname(frappe.session.user),
		lang=frappe.local.lang or "en",
		company=company or "",
		currency=currency or "",
		chat=chat,
	)
