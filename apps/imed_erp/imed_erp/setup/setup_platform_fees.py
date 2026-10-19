# The BA+ platform fee tiers (APP-02) approved by the owner: the first Platform Fee Schedule.
#
# Run from bench console, after setup_core.py:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_platform_fees.py").read(), {"frappe": frappe})
#
# This only enters the first tiers. From then on the owner keeps them himself from the Platform Fee
# Schedule list: new prices are a new schedule from a later date, and the old one stays as it was.
#
# Idempotent: a schedule already in force from the same date is left as is, even if its tiers were changed
# since. Safe to run again.

import frappe

# Requirements v1.2 §4.10, approved by the owner: the fee for ONE student of a course in a term, by the
# course's number of students. 300 students -> second tier -> 300 x 200 = 60,000.
# A course of exactly 100 students is in the first tier: assumed until the owner confirms (known-issues).
VALID_FROM = "2026-09-01"  # the start of the first term, 2026/2027
TIERS = [
	(1, 100, 250),
	(101, 500, 200),
	(501, None, 170),  # None: no upper limit
]


def make_schedule():
	if name := frappe.db.exists("Platform Fee Schedule", {"valid_from": VALID_FROM, "docstatus": ("<", 2)}):
		print(f"exists Platform Fee Schedule {name}")
		return
	schedule = frappe.get_doc(
		{
			"doctype": "Platform Fee Schedule",
			"valid_from": VALID_FROM,
			"tiers": [
				{"from_students": low, "to_students": high, "fee_per_student": fee} for low, high, fee in TIERS
			],
		}
	)
	schedule.insert()
	schedule.submit()
	print(f"created Platform Fee Schedule {schedule.name}: " + ", ".join(f"{low}-{high or '…'}: {fee}" for low, high, fee in TIERS))


make_schedule()
frappe.db.commit()
