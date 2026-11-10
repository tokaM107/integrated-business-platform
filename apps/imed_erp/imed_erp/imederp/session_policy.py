# Session expiry enforced by the server on every request (security audit, 10 Nov 2026).
#
# Frappe alone ends a session only after System Settings > Session Expiry of inactivity (170 hours on this
# site, 240 by default) and has no limit on a session's total age. This hook adds, for browser sessions:
#
#   inactivity   30 minutes for everyone, 15 for privileged roles
#   total age    12 hours for everyone, 8 for privileged roles
#
# Every value is changed in the site's configuration without a release (minutes / hours; 0 switches one off):
#
#   imed_session_idle_minutes               imed_session_privileged_idle_minutes
#   imed_session_absolute_hours             imed_session_privileged_absolute_hours
#   imed_session_privileged_roles           (a list of role names)
#
# It runs as an `auth_hooks` hook (hooks.py): after Frappe has resumed the session from the cookie and before
# any page or method. An expired session is deleted on the server exactly as "Log out" does, so the cookie is
# worth nothing afterwards, and the request goes on as Guest: methods answer 403 and the desk shows the sign-in
# page. Requests signed with an API key or token carry no browser session and are not touched (the library
# connector, scripts).
#
# Inactivity is measured from the last request this hook saw (kept in the cache with the session's id). Frappe's
# own `last_updated` is written at most every ten minutes, so it is used only when the cache holds nothing
# (first request after sign-in or after the cache was emptied); it is never later than the real last request, so
# the fallback can only end a session early, never late.

import frappe
from frappe.utils import cint, get_datetime, now_datetime

DEFAULT_IDLE_MINUTES = 30
DEFAULT_PRIVILEGED_IDLE_MINUTES = 15
DEFAULT_ABSOLUTE_HOURS = 12
DEFAULT_PRIVILEGED_ABSOLUTE_HOURS = 8
DEFAULT_PRIVILEGED_ROLES = ("System Manager", "Super Admin", "Accounts Manager")

SEEN_KEY = "imed_session_seen:"


def _setting(key, default):
	value = frappe.conf.get(key)
	return default if value is None else cint(value)


def limits(user):
	"""(seconds of inactivity allowed, seconds of total age allowed) for this user; 0 means no limit."""
	roles = frappe.conf.get("imed_session_privileged_roles") or DEFAULT_PRIVILEGED_ROLES
	privileged = user == "Administrator" or bool(set(roles) & set(frappe.get_roles(user)))
	if privileged:
		idle = _setting("imed_session_privileged_idle_minutes", DEFAULT_PRIVILEGED_IDLE_MINUTES)
		age = _setting("imed_session_privileged_absolute_hours", DEFAULT_PRIVILEGED_ABSOLUTE_HOURS)
	else:
		idle = _setting("imed_session_idle_minutes", DEFAULT_IDLE_MINUTES)
		age = _setting("imed_session_absolute_hours", DEFAULT_ABSOLUTE_HOURS)
	return max(idle, 0) * 60, max(age, 0) * 3600


def expired(data, seen, idle_limit, age_limit, now):
	"""Why this session is over ("age", "idle"), or None. Pure: the hook's rule, tested on its own."""
	created = data.get("creation")
	if age_limit and created and (now - get_datetime(created)).total_seconds() > age_limit:
		return "age"
	last = seen or data.get("last_updated")
	if idle_limit and last and (now - get_datetime(last)).total_seconds() > idle_limit:
		return "idle"
	return None


def enforce():
	"""auth_hooks: end a browser session that is too old or was idle too long."""
	session = getattr(frappe.local, "session", None)
	if not session or session.get("user") in (None, "", "Guest"):
		return
	data = session.get("data") or {}
	sid = session.get("sid")
	# A browser session has its creation time; API-key and token requests (frappe.set_user) have none.
	if not sid or not data.get("creation"):
		return

	user = session.user
	idle_limit, age_limit = limits(user)
	now = now_datetime()
	key = SEEN_KEY + sid
	reason = expired(data, last_seen(key), idle_limit, age_limit, now)
	if reason:
		end_session(sid, user, key, reason)
		return
	if idle_limit:
		remember(key, now, idle_limit)


def last_seen(key):
	return frappe.cache.get_value(key)


def remember(key, now, idle_limit):
	frappe.cache.set_value(key, str(now), expires_in_sec=idle_limit + 60)


def end_session(sid, user, key, reason):
	"""Delete the session on the server and carry on as Guest, as Frappe's own log-out does."""
	from frappe.sessions import delete_session

	message = "Session Expired (total age)" if reason == "age" else "Session Expired (inactivity)"
	delete_session(sid, user=user, reason=message)
	frappe.cache.delete_value(key)
	login_manager = getattr(frappe.local, "login_manager", None)
	if login_manager:
		login_manager.clear_cookies()
		login_manager.login_as_guest()
	else:
		frappe.set_user("Guest")
	frappe.response["session_expired"] = 1


def forget(login_manager=None):
	"""on_logout: the cache entry of a session that was logged out is dropped."""
	sid = getattr(frappe.local, "session", {}).get("sid")
	if sid:
		frappe.cache.delete_value(SEEN_KEY + sid)
