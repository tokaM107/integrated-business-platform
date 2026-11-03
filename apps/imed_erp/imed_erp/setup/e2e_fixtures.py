# The records the browser suites (tests/e2e) need, on a throwaway copy only. Each is made through the documents
# and rules the users go through, never by writing tables, and only when missing, so it can run again:
#   - a sale of Sara's at Azarita (binding: no paper) to try a return and a cancel on   (roles.js)
#   - the obsolete edition's copies in Azarita's editions store, to dispose as scrap        (workflows.js)
#   - a price for the studio's hour in Standard Selling                                    (workflows.js)
#   - today's submitted close of Azarita's cash box, to reopen                              (close.js)
#   - IMED's halls and a price tier for one of them                                         (hall_tiers.js)
# The cash boxes must hold money first (tests/testing.fund_cash_boxes), as on a real opening day.
#
#   docker exec frappe_docker-backend-1 bench --site restore-test execute imed_erp.setup.e2e_fixtures.run

import frappe
from frappe.utils import flt, today

THROWAWAY = ("restore-test",)
COMPANY = "Mohamed Mamdouh group"
AZARITA = "مكتبة الأزاريطة - MMG"
AZARITA_BOX = "خزينة مكتبة الأزاريطة - MMG"
AZARITA_EDITIONS = "إصدارات الأطباء — الأزاريطة - MMG"
SARA = "sara@imed.local"
HALL_CAPACITIES = {"قاعة 1": 150, "قاعة 3": 40, "قاعة 4": 40, "قاعة 6": 40}


def sale_of_sara():
	if frappe.db.exists("Sales Invoice", {"owner": SARA, "docstatus": 1, "is_return": 0, "cost_center": AZARITA}):
		return "kept"
	customer = frappe.get_all("Customer", {"customer_group": ["!=", "طبيب"], "disabled": 0}, pluck="name", limit=1)[0]
	frappe.set_user(SARA)
	try:
		doc = frappe.get_doc(
			{"doctype": "Sales Invoice", "company": COMPANY, "customer": customer, "cost_center": AZARITA,
			 "items": [{"item_code": "BINDING-SVC", "qty": 1, "rate": 20, "cost_center": AZARITA}]}
		).insert()
		doc.submit()
		return doc.name
	finally:
		frappe.set_user("Administrator")


def obsolete_edition_copies():
	made = []
	for ed in frappe.get_all("Book Edition", {"status": "Cancelled", "docstatus": 1, "remaining_qty": [">", 0], "cost_center": AZARITA}, ["name", "item_code", "remaining_qty"]):
		held = flt(frappe.db.get_value("Bin", {"item_code": ed.item_code, "warehouse": AZARITA_EDITIONS}, "actual_qty"))
		if held >= ed.remaining_qty:
			continue
		entry = frappe.get_doc(
			{"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": COMPANY,
			 "items": [{"item_code": ed.item_code, "qty": ed.remaining_qty - held, "basic_rate": 30, "t_warehouse": AZARITA_EDITIONS}]}
		).insert()
		entry.submit()
		made.append(entry.name)
	return made or "kept"


def studio_hour_price(rate=400):
	if frappe.db.exists("Item Price", {"item_code": "STUDIO-HOUR", "price_list": "Standard Selling"}):
		return "kept"
	return frappe.get_doc({"doctype": "Item Price", "item_code": "STUDIO-HOUR", "price_list": "Standard Selling", "price_list_rate": rate}).insert().name


def azarita_close_today():
	if frappe.db.exists("Treasury Close", {"treasury": AZARITA_BOX, "close_date": today(), "docstatus": 1}):
		return "kept"
	doc = frappe.get_doc({"doctype": "Treasury Close", "treasury": AZARITA_BOX, "business": AZARITA, "close_date": today(), "counted": 0}).insert()
	doc.counted = doc.expected  # counted what the books expect: no difference
	doc.submit()
	return doc.name


def halls_and_a_tier():
	from imed_erp.imederp import setup_halls

	inserted = setup_halls.run(capacities=HALL_CAPACITIES)
	hall = frappe.get_all("Booking Resource", {"resource_type": "Hall", "disabled": 0}, pluck="name", order_by="name", limit=1)
	if not hall:
		return {"halls": inserted, "tier": "no hall"}
	if frappe.db.exists("Hall Price Tier", {"resource": hall[0]}):
		return {"halls": inserted, "tier": "kept"}
	tier = frappe.get_doc(
		{"doctype": "Hall Price Tier", "resource": hall[0], "price_list": "Standard Selling",
		 "first_hour_rate": 800, "two_hour_rate": 1600, "extra_hour_rate": 600, "notes": "e2e fixture (throwaway site)"}
	).insert()
	return {"halls": inserted, "tier": tier.name, "hall": hall[0]}


def run():
	if frappe.local.site not in THROWAWAY:
		print(f"REFUSED: e2e fixtures are made on a throwaway copy only ({', '.join(THROWAWAY)}), not {frappe.local.site}.")
		return
	out = {}
	for step in (sale_of_sara, obsolete_edition_copies, studio_hour_price, azarita_close_today, halls_and_a_tier):
		try:
			out[step.__name__] = step()
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback()
			out[step.__name__] = f"FAILED: {type(e).__name__}: {frappe.utils.strip_html(str(e))[:200]}"
	for k, v in out.items():
		print(f"{k}: {v}")
	return out
