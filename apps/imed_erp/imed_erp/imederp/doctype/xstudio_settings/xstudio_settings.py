# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Where XStudio is and how the sync reads it (imederp/xstudio/). The "Last Runs" fields are written by the sync
# itself (xstudio/sync.py), never typed.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr


class XStudioSettings(Document):
	def validate(self):
		url = cstr(self.base_url).strip().rstrip("/")
		local = ("http://localhost", "http://127.", "http://host.docker.internal")
		if url and not url.startswith("https://") and not url.startswith(local):
			frappe.throw(_("The XStudio URL must start with https:// (http is allowed only for a local test server)."))
		self.base_url = url or None
		if self.enabled:
			for field in ("base_url", "login", "packages_resource", "customer_group"):
				if not self.get(field):
					frappe.throw(_("Enter {0} before enabling the sync.").format(_(self.meta.get_label(field))), title=_("Missing Value"))
			if not self.get_password("password", raise_exception=False):
				frappe.throw(_("Enter the XStudio password before enabling the sync."), title=_("Missing Value"))
			if not self.hall_map:
				frappe.throw(_("Map XStudio's halls to booking resources before enabling the sync."), title=_("Missing Value"))
		seen = set()
		for row in self.hall_map:
			if row.hall_id in seen:
				frappe.throw(_("Hall {0} is mapped twice.").format(row.hall_id))
			seen.add(row.hall_id)
			kind = frappe.db.get_value("Booking Resource", row.resource, "resource_type")
			if kind != "Studio Service":
				frappe.throw(_("{0} is a {1}. XStudio's halls are studio services, kept apart from the lecture halls.").format(row.resource, _(kind or "?")))
		if self.packages_resource and frappe.db.get_value("Booking Resource", self.packages_resource, "resource_type") != "Studio Service":
			frappe.throw(_("{0} is not a studio service.").format(self.packages_resource))
		for field in ("lookback_days", "lookahead_days", "poll_minutes"):
			if cint(self.get(field)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(field))))
