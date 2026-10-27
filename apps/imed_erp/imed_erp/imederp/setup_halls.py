# Copyright (c) 2026, toka mohamed and contributors
# License information in license.txt

"""IMED's lecture halls as the requirements name them (v1.2 §4.9, table "بيانات القاعات (للاستيفاء)"), as Booking
Resources of the halls' business.

The table names seven halls and leaves every other column blank: capacity, equipment and the hourly price are
"……………………" (question 15, for Nour, unanswered on 27 Oct 2026). A hall needs its capacity (HAL-01, booking_resource.py
refuses one without it), so nothing can be written until the capacities are given: `plan` shows the seven records
with what is still missing, and `run` inserts only the halls whose capacity was passed in, by the owner's or Nour's
answer, never a guessed one. Equipment and the hourly price stay empty until given too: the service item HALL-HOUR has
no Item Price, so a fixed-rent booking is refused until the price is set (booking_pricing.py); internal uses
(courses, meetings, maintenance) book without one.

Idempotent: a hall that exists (by its name) is left as it is, never overwritten.

    bench --site frontend execute imed_erp.imederp.setup_halls.plan
    bench --site frontend execute imed_erp.imederp.setup_halls.run --kwargs "{'capacities': {'قاعة 1': 40, ...}}"
"""

import frappe
from frappe.utils import cint

COST_CENTER = "قاعات Imed - MMG"
ITEM = "HALL-HOUR"
# Exactly the rows of the requirements table, in its order (there is no قاعة 2 in it).
HALL_NAMES = ["قاعة 1", "قاعة 3", "قاعة 4", "قاعة 5", "قاعة 6", "قاعة 7", "قاعة 8"]
NOTE = "من جدول بيانات القاعات في وثيقة المتطلبات v1.2 (التجهيزات وسعر الساعة لم تُستوفَ بعد)."


def record(name, capacity=None, equipment=None, location=None):
	return {
		"doctype": "Booking Resource",
		"resource_name": name,
		"resource_type": "Hall",
		"cost_center": COST_CENTER,
		"item": ITEM if frappe.db.exists("Item", ITEM) else None,
		"capacity": cint(capacity),
		"equipment": equipment or None,
		"location": location or None,
		"buffer_minutes": 0,
		"notes": NOTE,
	}


def plan(capacities=None, equipment=None):
	"""What `run` would do with these answers: insert, skip (exists) or wait (capacity unknown). Writes nothing."""
	capacities, equipment = capacities or {}, equipment or {}
	out = []
	for name in HALL_NAMES:
		rec = record(name, capacities.get(name), equipment.get(name))
		if frappe.db.exists("Booking Resource", name):
			action = "skip (exists)"
		elif rec["capacity"] <= 0:
			action = "wait (capacity unknown)"
		else:
			action = "insert"
		out.append({"resource_name": name, "action": action, "record": rec})
	return out


def run(capacities=None, equipment=None, dry_run=False):
	"""Insert the halls that are missing and whose capacity is known. Returns the names inserted."""
	inserted = []
	for row in plan(capacities, equipment):
		if row["action"] != "insert":
			continue
		if not dry_run:
			frappe.get_doc(row["record"]).insert()
		inserted.append(row["resource_name"])
	if inserted and not dry_run:
		frappe.db.commit()
	return inserted
