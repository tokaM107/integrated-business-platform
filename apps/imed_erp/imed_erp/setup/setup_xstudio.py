# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# What the XStudio sync needs on the site, made once and safe to run again: the customer group عملاء الاستوديو,
# one studio-service resource per XStudio hall (1, 3, 4, 5, 6, 8) and one for the prepaid packages, and the hall
# map on XStudio Settings. Prices are not set: imported bookings keep XStudio's amounts and are never priced here.
#
#   bench --site frontend execute imed_erp.setup.setup_xstudio.run
#
# It does not enable the sync, nor touch the URL, login or password: the owner enters those on XStudio Settings.

import os

import frappe

STUDIO = "استوديو X - MMG"
GROUP = "عملاء الاستوديو"
HALLS = (1, 3, 4, 5, 6, 8)
PACKAGES = "X Studio — Prepaid Packages"


def hall_resource(hall_id):
	return f"X Studio — Hall {hall_id}"


def run():
	ensure_group()
	for hall_id in HALLS:
		ensure_resource(hall_resource(hall_id), f"XStudio hall {hall_id}; booked in XStudio, read here.")
	ensure_resource(PACKAGES, "XStudio's prepaid hour and reel packages (not tied to one hall).")
	settings = frappe.get_single("XStudio Settings")
	mapped = {row.hall_id for row in settings.hall_map}
	for hall_id in HALLS:
		if hall_id not in mapped:
			settings.append("hall_map", {"hall_id": hall_id, "hall_name": f"Hall {hall_id}", "resource": hall_resource(hall_id)})
	if not settings.packages_resource:
		settings.packages_resource = PACKAGES
	if not settings.customer_group:
		settings.customer_group = GROUP
	settings.flags.ignore_permissions = True
	settings.save()
	frappe.db.commit()
	print("XStudio: group, 7 resources and the hall map are in place. Enter the URL, login and password on XStudio Settings, then enable it.")


def ensure_group():
	if not frappe.db.exists("Customer Group", GROUP):
		frappe.get_doc({"doctype": "Customer Group", "customer_group_name": GROUP, "parent_customer_group": "All Customer Groups"}).insert()


def ensure_resource(name, notes):
	if frappe.db.exists("Booking Resource", name):
		return
	item = "STUDIO-HOUR" if frappe.db.exists("Item", "STUDIO-HOUR") else None
	frappe.get_doc(
		{"doctype": "Booking Resource", "resource_name": name, "resource_type": "Studio Service", "cost_center": STUDIO, "item": item, "notes": notes}
	).insert()


def configure(base_url, login, enabled=0):
	"""The connection on XStudio Settings. The password is read from the environment variable XSTUDIO_SYNC_PASSWORD,
	never from a command line:
	  XSTUDIO_SYNC_PASSWORD=... bench --site frontend execute imed_erp.setup.setup_xstudio.configure \
	    --kwargs '{"base_url": "http://host.docker.internal:4000", "login": "+2010...", "enabled": 1}'"""
	password = os.environ.get("XSTUDIO_SYNC_PASSWORD")
	if not password:
		frappe.throw("Set XSTUDIO_SYNC_PASSWORD in the environment first.")
	settings = frappe.get_single("XStudio Settings")
	settings.base_url, settings.login, settings.password = base_url, login, password
	settings.token, settings.token_obtained_at = None, None
	settings.enabled = int(enabled)
	settings.flags.ignore_permissions = True
	settings.save()
	frappe.db.commit()
	print(f"XStudio Settings: {base_url}, login {login}, enabled={int(enabled)}")
