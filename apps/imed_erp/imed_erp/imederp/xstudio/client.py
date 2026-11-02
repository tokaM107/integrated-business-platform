# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The one place that talks to XStudio's existing REST API (xstudio-platform/backend/src/routes.js). Nothing here
# writes to XStudio: every call is a GET, except the login that gets the session token.
#
# What the API offers today, and what it does not (the sync works around these, see sync.py):
#   POST /api/auth/login                 {phone|email, password} -> {token}; the token lasts 7 days (db.js jwtExpiry)
#   GET  /api/health                      {ok: true}
#   GET  /api/halls                       the active halls (public)
#   GET  /api/config                      rates and the editable services (public)
#   GET  /api/bookings?from&to&status&customerId   needs bookings.read; AT MOST 500 ROWS, ordered by starts_at,
#                                         no paging, no filter on updated_at (routes.js:569-584)
#   GET  /api/customers/:id/packages      needs packages.read; the customer's packages with their usage ledger and
#                                         payments (the payments carry no id: routes.js:909-919)
#   GET  /api/photographers               needs bookings.read
# The staff roles that hold both bookings.read and packages.read are manager and accountant (middleware/auth.js);
# the sync's account should be an accountant made for it, with its own password.

import json
from urllib.parse import urlencode

import frappe
import requests
from frappe import _
from frappe.utils import cstr, now_datetime

TIMEOUT = 20
# The bookings endpoint's fixed limit: a window that returns this many rows may hold more (routes.js:582).
BOOKINGS_LIMIT = 500


class XStudioError(Exception):
	"""XStudio could not be read: the sync stops and says why; nothing already imported changes."""


class XStudioAuthError(XStudioError):
	pass


class XStudioClient:
	def __init__(self, settings):
		self.settings = settings
		self.base_url = cstr(settings.base_url).rstrip("/")
		if not self.base_url:
			raise XStudioError(_("XStudio Settings has no URL."))
		self.token = settings.get_password("token", raise_exception=False)
		self.requests_made = 0
		self.session = requests.Session()

	# ---------- transport ----------

	def request(self, method, path, params=None, body=None, auth=True, _retry=True):
		# Read-only, whatever the account may do in XStudio: a GET, or the one POST that logs in. Nothing else leaves.
		if not (method == "GET" or (method == "POST" and path == "/api/auth/login")):
			raise XStudioError(f"The ERP only reads from XStudio; {method} {path} is refused.")
		"""One call. 401 with a token: log in again once and repeat. Anything else that is not 2xx raises."""
		url = self.base_url + path
		if params:
			url += "?" + urlencode({k: v for k, v in params.items() if v is not None})
		headers = {"Accept": "application/json"}
		if auth:
			if not self.token:
				self.login()
			headers["Authorization"] = f"Bearer {self.token}"
		try:
			self.requests_made += 1
			response = self.session.request(method, url, headers=headers, json=body, timeout=TIMEOUT)
		except requests.RequestException as e:
			raise XStudioError(_("XStudio did not answer ({0}): {1}").format(path, type(e).__name__))
		if response.status_code == 401 and auth and _retry:
			self.login()
			return self.request(method, path, params=params, body=body, auth=auth, _retry=False)
		if response.status_code >= 400:
			raise XStudioError(_("XStudio answered {0} on {1}: {2}").format(response.status_code, path, error_text(response)))
		try:
			return response.json()
		except ValueError:
			raise XStudioError(_("XStudio's answer on {0} is not JSON.").format(path))

	def get(self, path, **params):
		return self.request("GET", path, params=params or None)

	def login(self):
		"""POST /api/auth/login with the settings' phone or email and password; keeps the token on the settings."""
		login = cstr(self.settings.login).strip()
		password = self.settings.get_password("password", raise_exception=False)
		if not login or not password:
			raise XStudioAuthError(_("XStudio Settings has no login or password."))
		body = {"email" if "@" in login else "phone": login, "password": password}
		url = self.base_url + "/api/auth/login"
		try:
			self.requests_made += 1
			response = self.session.post(url, json=body, timeout=TIMEOUT)
		except requests.RequestException as e:
			raise XStudioError(_("XStudio did not answer the login: {0}").format(type(e).__name__))
		if response.status_code != 200:
			raise XStudioAuthError(_("XStudio refused the login ({0}): {1}").format(response.status_code, error_text(response)))
		token = (response.json() or {}).get("token")
		if not token:
			raise XStudioAuthError(_("XStudio's login answer has no token."))
		self.token = token
		# The token is a secret: kept in the Password field, decrypted only to send it.
		frappe.db.set_single_value("XStudio Settings", "token_obtained_at", now_datetime(), update_modified=False)
		doc = frappe.get_single("XStudio Settings")
		doc.token = token
		doc.flags.ignore_permissions = True
		doc.flags.ignore_validate = True
		doc.save(ignore_version=True)
		return token

	# ---------- the endpoints the sync reads ----------

	def health(self):
		return self.request("GET", "/api/health", auth=False)

	def halls(self):
		return self.request("GET", "/api/halls", auth=False)

	def config(self):
		return self.request("GET", "/api/config", auth=False)

	def bookings(self, starts_from=None, starts_before=None, customer_id=None, status=None):
		"""GET /api/bookings. `starts_from`/`starts_before` are ISO instants compared with starts_at (>= and <).
		Returns at most BOOKINGS_LIMIT rows: the caller checks the count."""
		params = {"from": starts_from, "to": starts_before, "customerId": customer_id, "status": status}
		rows = self.get("/api/bookings", **params)
		return rows if isinstance(rows, list) else []

	def customer_packages(self, customer_id):
		rows = self.get(f"/api/customers/{customer_id}/packages")
		return rows if isinstance(rows, list) else []

	def photographers(self):
		rows = self.get("/api/photographers")
		return rows if isinstance(rows, list) else []


def error_text(response):
	try:
		return cstr((response.json() or {}).get("error") or "")[:200]
	except ValueError:
		return cstr(response.text)[:200]


def stable_json(value):
	"""The same JSON for the same data, whatever the key order: what the payload hash is made of."""
	return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
