# The studio's services and prices from the requirements (v1.2, section 4.8, "قائمة الخدمات والأسعار"): the
# resources, their service items and Item Prices (Standard Selling), the packages (STU-05) and the extras (STU-04).
# The halls' prices are blank in the requirements (HAL-01, HAL-03, question 15): nothing is made for them.
#
# Run from bench console:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_booking_prices.py").read(), {"frappe": frappe})
#
# Idempotent: what exists is left as it is, and a price already set is never changed here (the owner changes
# prices, SEC-02). Safe to run again.
#
# The items carry no income account: a booking's invoice puts each line into its business's income account
# (imederp/booking_accounts.py), whatever item it sells.
#
# Read from the price list, and to confirm with Gilan (docs/known-issues.md, bookings):
#   - Smart board 86": 1,150 for 5 hours includes filming, editing and removing mistakes; 750 without editing.
#   - The 10- and 30-hour packages are sold as one booking of up to those hours; hours used over several
#     bookings (a balance) are not built.
#   - Podcast: one room, priced per hour by its cameras (three packages), so its bookings never overlap.
#   - Extras: "مايك أو إضاءة — ساعة — 50 للقطعة الواحدة": 50 a piece an hour, for the studio.
#   - Location: no price in the list; the resource is made, and takes no booking until it is priced.

import frappe

STUDIO = "استوديو X - MMG"
PRICE_LIST = "Standard Selling"
ITEM_GROUP = "الخدمات"
HOUR, UNIT = "ساعة", "Nos"

# (item code, item name, unit, price)
ITEMS = [
	("STU-SB86-5H", "سمارت بورد 86 بوصة — 5 ساعات", UNIT, 1150),
	("STU-SB86-5H-NOEDIT", "سمارت بورد 86 بوصة — 5 ساعات بدون مونتاج", UNIT, 750),
	("STU-SB86-10H", "سمارت بورد 86 بوصة — 10 ساعات", UNIT, 1750),
	("STU-SB86-30H", "سمارت بورد 86 بوصة — 30 ساعة", UNIT, 4650),
	("STU-SB75-HOUR", "2 سمارت بورد 75 بوصة — ساعة", HOUR, 200),
	("STU-SB75-5H", "2 سمارت بورد 75 بوصة — 5 ساعات", UNIT, 900),
	("STU-SB75-10H", "2 سمارت بورد 75 بوصة — 10 ساعات", UNIT, 1350),
	("STU-SB75-30H", "2 سمارت بورد 75 بوصة — 30 ساعة", UNIT, 3750),
	("STU-REEL-1", "ريل (دقيقة ونصف)", UNIT, 500),
	("STU-REEL-5", "5 ريلز", UNIT, 2250),
	("STU-REEL-10", "10 ريلز", UNIT, 4250),
	("STU-REEL-15", "15 ريلز", UNIT, 6000),
	("STU-PODCAST-1CAM", "بودكاست — كاميرا واحدة — ساعة", HOUR, 1250),
	("STU-PODCAST-2CAM", "بودكاست — كاميرتان — ساعة", HOUR, 1750),
	("STU-PODCAST-3CAM", "بودكاست — 3 كاميرات — ساعة", HOUR, 2250),
	("STU-EXTRA-MIC", "ميكروفون إضافي — للقطعة في الساعة", HOUR, 50),
	("STU-EXTRA-LIGHT", "إضاءة إضافية — للقطعة في الساعة", HOUR, 50),
]

# (resource, its item by the hour or None, equipment)
RESOURCES = [
	("سمارت بورد 86 بوصة", None, "سمارت بورد 86 بوصة"),
	("2 سمارت بورد 75 بوصة", "STU-SB75-HOUR", "2 سمارت بورد 75 بوصة"),
	("ريلز", None, "مدة التواجد في اللوكيشن لا تتجاوز 15 دقيقة للريل"),
	("بودكاست", None, "تصوير، مونتاج، إضاءة، ميكروفونات ومعدات احترافية"),
	("لوكيشن", None, ""),
]

# (package, resource, item, charged, hours included, what it includes)
PACKAGES = [
	("سمارت بورد 86 — 5 ساعات", "سمارت بورد 86 بوصة", "STU-SB86-5H", "Once", 5, "شامل التصوير والمونتاج وإزالة الأخطاء"),
	("سمارت بورد 86 — 5 ساعات بدون مونتاج", "سمارت بورد 86 بوصة", "STU-SB86-5H-NOEDIT", "Once", 5, "بدون مونتاج"),
	("سمارت بورد 86 — 10 ساعات", "سمارت بورد 86 بوصة", "STU-SB86-10H", "Once", 10, ""),
	("سمارت بورد 86 — 30 ساعة", "سمارت بورد 86 بوصة", "STU-SB86-30H", "Once", 30, ""),
	("2 سمارت بورد 75 — 5 ساعات", "2 سمارت بورد 75 بوصة", "STU-SB75-5H", "Once", 5, ""),
	("2 سمارت بورد 75 — 10 ساعات", "2 سمارت بورد 75 بوصة", "STU-SB75-10H", "Once", 10, ""),
	("2 سمارت بورد 75 — 30 ساعة", "2 سمارت بورد 75 بوصة", "STU-SB75-30H", "Once", 30, ""),
	("ريل واحد", "ريلز", "STU-REEL-1", "Once", 0, "دقيقة ونصف"),
	("5 ريلز", "ريلز", "STU-REEL-5", "Once", 0, ""),
	("10 ريلز", "ريلز", "STU-REEL-10", "Once", 0, ""),
	("15 ريلز", "ريلز", "STU-REEL-15", "Once", 0, ""),
	("بودكاست — كاميرا واحدة", "بودكاست", "STU-PODCAST-1CAM", "Per Hour", 0, "تصوير، مونتاج، إضاءة، ميكروفونات"),
	("بودكاست — كاميرتان", "بودكاست", "STU-PODCAST-2CAM", "Per Hour", 0, "تصوير، مونتاج، إضاءة، ميكروفونات"),
	("بودكاست — 3 كاميرات", "بودكاست", "STU-PODCAST-3CAM", "Per Hour", 0, "تصوير، مونتاج، إضاءة، ميكروفونات"),
]

# (extra, item, charged, applies to)
EXTRAS = [
	("ميكروفون", "STU-EXTRA-MIC", "Per Piece per Hour", "Studio Service"),
	("إضاءة", "STU-EXTRA-LIGHT", "Per Piece per Hour", "Studio Service"),
]


def make(doctype, name, values):
	if frappe.db.exists(doctype, name):
		print(f"exists {doctype} {name}")
		return
	frappe.get_doc({"doctype": doctype, **values}).insert()
	print(f"create {doctype} {name}")


def run():
	for code, name, uom, price in ITEMS:
		make(
			"Item",
			code,
			{
				"item_code": code,
				"item_name": name,
				"item_group": ITEM_GROUP,
				"stock_uom": uom,
				"is_stock_item": 0,
				"include_item_in_manufacturing": 0,
			},
		)
		if frappe.db.exists("Item Price", {"item_code": code, "price_list": PRICE_LIST}):
			print(f"exists Item Price {code} ({PRICE_LIST})")
		else:
			frappe.get_doc({"doctype": "Item Price", "item_code": code, "price_list": PRICE_LIST, "price_list_rate": price, "valid_from": "2026-01-01"}).insert()
			print(f"create Item Price {code} {price}")
	for name, item, equipment in RESOURCES:
		make(
			"Booking Resource",
			name,
			{"resource_name": name, "resource_type": "Studio Service", "cost_center": STUDIO, "item": item, "equipment": equipment},
		)
	for name, resource, item, charged, hours, inclusions in PACKAGES:
		make(
			"Booking Package",
			name,
			{"package_name": name, "resource": resource, "item": item, "charged": charged, "hours": hours, "inclusions": inclusions},
		)
	for name, item, charged, applies_to in EXTRAS:
		make("Booking Extra", name, {"extra_name": name, "item": item, "charged": charged, "applies_to": applies_to})
	frappe.db.commit()


run()
