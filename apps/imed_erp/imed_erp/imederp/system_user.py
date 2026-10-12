# Work done in the system's name (Administrator) inside someone's request, e.g. the Stock Reconciliation a
# branch manager's count makes, or the paper a cashier's printing sale issues.
#
# frappe.set_user() replaces the session's sid and data with the new user's. Inside a web request those
# belong to the person's browser session, and Frappe saves them back when the request ends: switching back
# with set_user alone would leave the session without its user, csrf token and expiry, and log them out.
# as_administrator() puts the person's session (and the request's form data) back exactly as it was.

from contextlib import contextmanager

import frappe


@contextmanager
def as_administrator():
	session = frappe.local.session
	user, sid, data = session.user, session.get("sid"), session.get("data")
	form_dict = frappe.local.form_dict
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)
		session.sid = sid
		session.data = data
		frappe.local.form_dict = form_dict
