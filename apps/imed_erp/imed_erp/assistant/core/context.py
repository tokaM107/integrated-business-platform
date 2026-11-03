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
	# Every company the user may read (Company user permissions applied), and whether that is every company of the
	# site: a read that is not limited to one company (most of the app's reports, the dashboard's cards) is only for
	# a user who may read them all (security review of 2 Nov 2026).
	companies: tuple[str, ...] = ()
	all_companies: bool = False

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


def readable_companies() -> tuple[list[str], bool]:
	"""(the companies the session user may read, whether that is all of them). Through get_list, so Company user
	permissions apply; a user who may not read Company at all reads none."""
	try:
		allowed = frappe.get_list("Company", pluck="name", limit=0, order_by="name")
	except frappe.PermissionError:
		frappe.clear_messages()
		return [], False
	every = frappe.get_all("Company", pluck="name", limit=0)
	return allowed, bool(allowed) and set(allowed) == set(every)


def resolve_company(allowed: list[str]) -> str:
	"""The request's company: the user's default, else the site's, else the only one the user may read; never one
	the user may not read, whatever a default says (a default is a preference anyone can set for themselves)."""
	for candidate in (frappe.defaults.get_user_default("company"), frappe.defaults.get_global_default("company")):
		if candidate and candidate in allowed:
			return candidate
	if len(allowed) == 1:
		return allowed[0]
	frappe.throw(
		frappe._("Choose your company first (Session Defaults): the assistant answers for one company you may read."),
		frappe.PermissionError,
	)


def build_context(chat: str | None = None) -> RequestContext:
	allowed, every = readable_companies()
	company = resolve_company(allowed)
	currency = frappe.get_cached_value("Company", company, "default_currency")
	return RequestContext(
		user=frappe.session.user,
		full_name=frappe.utils.get_fullname(frappe.session.user),
		lang=frappe.local.lang or "en",
		company=company,
		currency=currency or "",
		chat=chat,
		companies=tuple(allowed),
		all_companies=every,
	)
