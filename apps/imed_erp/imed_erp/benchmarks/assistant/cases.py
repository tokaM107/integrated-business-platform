# The assistant's benchmark: the owner's own questions (handwritten on the requirements sheet, section 12 "AI Agent
# - Real Questions", 4 Nov 2026), plus the sheet's printed examples. Each case carries what a right answer must hold,
# worked out from the ERP itself at run time (`oracle`, read-only), so the benchmark holds on any site and any day.
#
# Kinds of case:
#   facts        the answer must give the oracle's figures (counts exactly, money within 1%)
#   list         the answer must name the oracle's items (names, times)
#   unavailable  the ERP holds no such data: a right answer says so and gives no figure
#   readonly     the question asks for an action: a right answer says it only reads, and where it is done
#
# `reading` is how the handwriting was read; `uncertain` marks the readings to confirm with the owner.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import frappe
from frappe.utils import add_days, flt, get_first_day, today

from imed_erp.imederp.booking_rules import NOT_HELD, STUDIO_SERVICE

PAPER = "A4-PAPER"
SHEETS_PER_BOX = 2500  # setup_core.py: 1 Box = 5 Reams = 2,500 sheets


@dataclass
class Case:
	id: str
	question: str
	kind: str  # facts | list | unavailable | readonly
	category: str
	intent: str
	oracle: Callable[[str], dict] | None = None
	expected_tools: tuple[str, ...] = ()
	reading: str = ""
	uncertain: bool = False
	source: str = "handwritten"
	notes: str = ""
	tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- oracles (read-only; never raise)


def _company(company):
	return company or frappe.defaults.get_global_default("company")


def _gl(company, root_type, start, end, cost_centers=None):
	"""Income (credit - debit) or expense (debit - credit), opening and closing entries left out, as the reports do."""
	sign = "gl.credit - gl.debit" if root_type == "Income" else "gl.debit - gl.credit"
	cc = "and gl.cost_center in %(cc)s" if cost_centers else ""
	return flt(frappe.db.sql(
		f"""select coalesce(sum({sign}), 0) from `tabGL Entry` gl join `tabAccount` a on a.name = gl.account
		where gl.company = %(company)s and gl.is_cancelled = 0 and gl.is_opening = 'No' and gl.voucher_type != 'Period Closing Voucher'
		and a.root_type = %(root)s and gl.posting_date between %(start)s and %(end)s {cc}""",
		{"company": company, "root": root_type, "start": start, "end": end, "cc": tuple(cost_centers or ()) or ("",)},
	)[0][0], 2)


def _cost_centers_like(company, words):
	rows = frappe.get_all("Cost Center", filters={"company": company, "is_group": 0}, fields=["name", "cost_center_name"])
	return [r.name for r in rows if any(w in (r.cost_center_name or "") for w in words)]


def _held_bookings(day, resource_type=None):
	filters = {"booking_date": day, "status": ("not in", NOT_HELD)}
	if resource_type:
		filters["resource_type"] = resource_type
	return frappe.get_all("Booking", filters=filters, fields=["name", "customer", "resource", "from_time", "to_time", "hours", "resource_type"], order_by="from_time")


def _no_records(**facts):
	return {"available": True, "has_records": False, "facts": facts}


def oracle_editions_sold(company, doctor_words=("ايمن", "أيمن"), book_words=("bio", "Bio", "بيو", "بايو")):
	agreements = [a.name for a in frappe.get_all("Doctor Agreement", fields=["name", "doctor"]) if any(w in (a.doctor or "") for w in doctor_words)]
	if not agreements:
		return {"available": True, "has_records": False, "facts": {}, "why": "no doctor named Ayman"}
	editions = frappe.get_all("Book Edition", filters={"agreement": ("in", agreements), "docstatus": 1}, fields=["name", "edition_name", "sold_qty", "remaining_qty"])
	bio = [e for e in editions if any(w in (e.edition_name or "") for w in book_words)] or editions
	return {"available": True, "has_records": bool(bio), "facts": {"sold": sum(int(e.sold_qty or 0) for e in bio)}, "items": [e.edition_name for e in bio]}


def oracle_booking_times_today(company):
	rows = _held_bookings(today())
	if not rows:
		return _no_records(count=0)
	return {"available": True, "has_records": True, "facts": {"count": len(rows)}, "items": [str(r.from_time)[:5] for r in rows]}


def oracle_paper_stock(company):
	rows = frappe.get_all("Bin", filters={"item_code": PAPER, "actual_qty": ("!=", 0)}, fields=["warehouse", "actual_qty"])
	sheets = sum(flt(r.actual_qty) for r in rows)
	ink_items = frappe.get_all("Item", filters={"disabled": 0, "is_stock_item": 1, "item_name": ("like", "%حبر%")}, pluck="name") + frappe.get_all(
		"Item", filters={"disabled": 0, "is_stock_item": 1, "item_name": ("like", "%ink%")}, pluck="name"
	)
	ink = sum(flt(b.actual_qty) for b in frappe.get_all("Bin", filters={"item_code": ("in", ink_items)}, fields=["actual_qty"])) if ink_items else 0
	return {
		"available": True,
		"has_records": bool(rows),
		"facts": {"sheets": flt(sheets, 0), "boxes": flt(sheets / SHEETS_PER_BOX, 1)},
		"items": [r.warehouse for r in rows],
		"ink_tracked": bool(ink_items),
		"ink_qty": ink,
	}


def oracle_paper_boxes(company):
	o = oracle_paper_stock(company)
	return {**o, "facts": {"boxes": o["facts"]["boxes"]}}


def oracle_ink(company):
	ink_items = frappe.get_all("Item", filters={"disabled": 0, "is_stock_item": 1}, fields=["name", "item_name"])
	ink_items = [i.name for i in ink_items if "حبر" in (i.item_name or "") or "ink" in (i.item_name or "").lower()]
	if not ink_items:
		return {"available": False, "why": "ink is not a stock item in this ERP (only an ink cost per sheet on Printing Cost Settings)"}
	rows = frappe.get_all("Bin", filters={"item_code": ("in", ink_items), "actual_qty": ("!=", 0)}, fields=["item_code", "warehouse", "actual_qty"])
	last_in = frappe.db.sql(
		"""select max(posting_date) from `tabStock Ledger Entry` where item_code in %s and actual_qty > 0 and is_cancelled = 0""", (tuple(ink_items),)
	)[0][0]
	return {"available": True, "has_records": bool(rows), "facts": {}, "items": sorted({r.warehouse for r in rows}), "last_received": str(last_in or "")}


def oracle_profit_per_place(company):
	start, end = get_first_day(today()), today()
	centers = frappe.get_all("Cost Center", filters={"company": company, "is_group": 0, "disabled": 0}, fields=["name", "cost_center_name"])
	facts, items = {}, []
	for c in centers:
		income, expense = _gl(company, "Income", start, end, [c.name]), _gl(company, "Expense", start, end, [c.name])
		if income or expense:
			facts[f"net:{c.cost_center_name}"] = flt(income - expense, 2)
			items.append(c.cost_center_name)
	return {"available": True, "has_records": bool(items), "facts": facts, "items": items, "period": f"{start}..{end}"}


def oracle_studio_bookers_today(company):
	rows = _held_bookings(today(), STUDIO_SERVICE)
	return {"available": True, "has_records": bool(rows), "facts": {"people": len({r.customer for r in rows if r.customer}), "bookings": len(rows)}}


def oracle_hours_per_person_today(company):
	rows = _held_bookings(today())
	per = {}
	for r in rows:
		per[r.customer or "-"] = flt(per.get(r.customer or "-", 0) + flt(r.hours), 2)
	return {"available": True, "has_records": bool(rows), "facts": {f"hours:{k}": v for k, v in per.items()}, "items": list(per)}


def oracle_studio_money(company):
	start, end = get_first_day(today()), today()
	studio = _cost_centers_like(company, ("استوديو", "Studio"))
	income, expense = _gl(company, "Income", start, end, studio), _gl(company, "Expense", start, end, studio)
	due = frappe.db.sql(
		"""select coalesce(sum(xstudio_amount_due - xstudio_amount_paid), 0), coalesce(sum(xstudio_amount_paid), 0) from `tabBooking`
		where source_system = 'xstudio' and booking_date between %s and %s and status not in %s""",
		(start, end, NOT_HELD),
	)[0] if frappe.get_meta("Booking").has_field("xstudio_amount_due") else (0, 0)
	return {
		"available": True,
		"has_records": bool(income or expense or due[0] or due[1]),
		"facts": {"revenue": income, "expenses": expense, "net": flt(income - expense, 2)},
		"xstudio": {"due": flt(due[0], 2), "paid": flt(due[1], 2)},
		"period": f"{start}..{end}",
	}


def oracle_who_paid(company):
	"""BA Plus students who paid this month (submitted App Payments): who, how many, how much."""
	start, end = get_first_day(today()), today()
	rows = frappe.get_all("App Payment", filters={"docstatus": 1, "posting_date": ("between", [start, end])}, fields=["student", "amount"])
	per = {}
	for r in rows:
		per[r.student] = flt(per.get(r.student, 0) + flt(r.amount), 2)
	names = {c.name: c.customer_name for c in frappe.get_all("Customer", filters={"name": ("in", list(per) or ["-"])}, fields=["name", "customer_name"])}
	return {
		"available": True,
		"has_records": bool(rows),
		"facts": {"payers": len(per), "total": flt(sum(per.values()), 2)},
		"items": [names.get(k, k) for k in per],
		"period": f"{start}..{end}",
	}


def oracle_teachers_students(company):
	courses = frappe.get_all("App Course", filters={"status": "Active"}, fields=["name", "doctor", "subscriptions"])
	per = {}
	for c in courses:
		per[c.doctor or "-"] = per.get(c.doctor or "-", 0) + int(c.subscriptions or 0)
	return {"available": True, "has_records": bool(courses), "facts": {"teachers": len(per), **{f"students:{k}": v for k, v in per.items()}}, "items": list(per)}


def oracle_revenue_today(company):
	day = today()
	return {"available": True, "has_records": bool(frappe.db.count("GL Entry", {"company": company, "posting_date": day, "is_cancelled": 0})), "facts": {"revenue": _gl(company, "Income", day, day)}}


def oracle_top_place_month(company):
	o = oracle_profit_per_place(company)
	start, end = get_first_day(today()), today()
	revenue = {}
	for c in frappe.get_all("Cost Center", filters={"company": company, "is_group": 0, "disabled": 0}, fields=["name", "cost_center_name"]):
		value = _gl(company, "Income", start, end, [c.name])
		if value:
			revenue[c.cost_center_name] = value
	top = max(revenue, key=revenue.get) if revenue else None
	return {"available": True, "has_records": bool(revenue), "facts": {"top_revenue": revenue.get(top, 0)} if top else {}, "items": [top] if top else [], "all": revenue, "net": o.get("facts")}


def oracle_studio_expenses_month(company):
	start, end = get_first_day(today()), today()
	studio = _cost_centers_like(company, ("استوديو", "Studio"))
	value = _gl(company, "Expense", start, end, studio)
	return {"available": True, "has_records": bool(value), "facts": {"expenses": value}}


def oracle_bookings_tomorrow(company):
	rows = _held_bookings(add_days(today(), 1))
	return {"available": True, "has_records": bool(rows), "facts": {"count": len(rows)}, "items": [f"{str(r.from_time)[:5]} {r.resource}" for r in rows]}


def oracle_running_out(company):
	rows = frappe.db.sql(
		"""select b.item_code, b.warehouse, b.actual_qty, r.warehouse_reorder_level from `tabBin` b
		join `tabItem Reorder` r on r.parent = b.item_code and r.warehouse = b.warehouse
		where b.actual_qty <= r.warehouse_reorder_level""",
		as_dict=True,
	)
	return {"available": True, "has_records": bool(rows), "facts": {"count": len(rows)}, "items": sorted({r.item_code for r in rows})}


# ---------------------------------------------------------------- the cases

CASES: list[Case] = [
	Case("H01", "مين بيشتغل ومين مش بيشتغل النهارده؟", "unavailable", "staff", "who is at work today",
		reading="مين بيشتغل ومين مش بيشتغل", notes="No HR or attendance app is installed: no check-ins to read."),
	Case("H02", "كام كتاب اتباع للدكتور أيمن، كتاب البيو؟", "facts", "library", "copies sold of Dr. Ayman's bio book",
		oracle=oracle_editions_sold, expected_tools=("list_records", "run_report"), reading="كام كتاب اتباع للدكتور ايمن كتاب bio"),
	Case("H03", "الناس النهارده حجزت الساعة كام؟", "list", "bookings", "the times of today's bookings",
		oracle=oracle_booking_times_today, expected_tools=("list_records",), reading="الناس النهاردة حجم اساعة كام",
		notes="Reading confirmed by the owner (4 Nov 2026): what time did people book today."),
	Case("H04", "مين اتأخر بعد ٩ ونص؟", "unavailable", "staff", "who came after 9:30",
		reading="مين اتأخر بعد ٩ ونص", notes="No attendance data in the ERP."),
	Case("H05", "الأحبار والورق فيها مخزون كام؟", "facts", "library-stock", "ink and paper on hand",
		oracle=oracle_paper_stock, expected_tools=("run_report", "list_records"), reading="الأحبار والورق فيها مخزون كام",
		notes="Paper is a stock item (sheets; 2,500 a box). Ink is not stocked (only an ink cost per sheet): the answer must say so for the ink."),
	Case("H06", "الأحبار اتحطت فين؟", "unavailable", "library-stock", "which store holds the ink",
		oracle=oracle_ink, reading="الأحبار اتحطت فين", notes="Becomes a 'list' case once ink is a stock item."),
	Case("H07", "كام كرتونة ورق متبقية؟", "facts", "library-stock", "paper boxes left",
		oracle=oracle_paper_boxes, expected_tools=("run_report", "list_records"), reading="كام كارتونة ورق متبقية"),
	Case("H08", "عايز حساب كامل لكل مكان لوحده.", "facts", "accounts", "revenue, expenses and net for each business this month",
		oracle=oracle_profit_per_place, expected_tools=("run_report", "dashboard_cards"), reading="حساب كامل لكل مكان لوحده",
		notes="No period said: this month is assumed; the answer must say which period it used."),
	Case("H09", "كام واحد حجز الاستوديو النهارده؟", "facts", "studio", "people who booked the studio today",
		oracle=oracle_studio_bookers_today, expected_tools=("count_records", "list_records"), reading="كام واحد حجز الاستوديو النهاردة"),
	Case("H10", "الحجوزات اللي اتعملت النهارده، وكل واحد خد كام ساعة؟", "facts", "bookings", "today's bookings and hours per person",
		oracle=oracle_hours_per_person_today, expected_tools=("list_records",), reading="الحجوزات اللي اتعملت وواحد لنفس... اخد كام ساعة",
		notes="Reading confirmed by the owner (4 Nov 2026): hours per person."),
	Case("H11", "فلوس الاستوديو وحساباته الشهر ده عاملة إيه؟", "facts", "studio", "the studio's money this month",
		oracle=oracle_studio_money, expected_tools=("run_report", "dashboard_cards", "owner_band_today"), reading="اعد فلوسك والحسابات بالنسبة للاستوديو",
		notes="Reading confirmed by the owner (4 Nov 2026). XStudio's amounts due and paid are mirrored, never posted: a right answer keeps them apart from the ledger."),
	Case("H12", "مين دفع؟", "list", "ba-plus", "which BA Plus students paid (this month)",
		oracle=oracle_who_paid, expected_tools=("list_records",), reading="مين دفع",
		notes="Confirmed by the owner (4 Nov 2026): 'who paid', next to teachers and students, so BA Plus. No period said: this month is assumed; the answer must say which period it used."),
	Case("H13", "كام مدرس، وكل مدرس معاه كام طالب؟", "facts", "ba-plus", "active teachers and their students",
		oracle=oracle_teachers_students, expected_tools=("list_records", "run_report"), reading="كام مدرس معاه كام طالب",
		notes="Confirmed by the owner (4 Nov 2026)."),
	Case("H14", "رصيد الحبر في المكتبة اتحط على السيستم امتى؟", "unavailable", "library-stock", "when the ink stock was entered",
		oracle=oracle_ink, reading="المكتبة بيدخل رصيد الحبر على السيستم حطيناه امتى"),
	Case("H15", "معدل استهلاك الأحبار الطبيعي قد إيه، والأحبار هتخلص امتى؟", "unavailable", "library-stock", "ink usage rate and run-out date",
		oracle=oracle_ink, reading="معدل طبيعي الأحبار هتخلص امتى"),
	Case("H16", "لما المخزون يخلص ابعتلي إنذار.", "readonly", "library-stock", "an alert when stock runs out",
		reading="لما المخزون يخلص يدي انذار", notes="A feature request: the ERP already alerts on reorder levels (stock_reorder.py, Reorder Alerts); the assistant cannot set anything."),
	Case("T01", "إيرادات النهارده كام؟", "facts", "accounts", "today's revenue", oracle=oracle_revenue_today,
		expected_tools=("dashboard_cards", "owner_band_today", "run_report"), source="sheet example"),
	Case("T02", "مين أكتر مكان كسب الشهر ده؟", "list", "accounts", "the business with the most revenue this month", oracle=oracle_top_place_month,
		expected_tools=("run_report", "dashboard_cards"), source="sheet example"),
	Case("T03", "مصروفات الاستوديو الشهر ده كام؟", "facts", "studio", "the studio's expenses this month", oracle=oracle_studio_expenses_month,
		expected_tools=("run_report",), source="sheet example"),
	Case("T04", "إيه الحجوزات بتاعة بكرة؟", "list", "bookings", "tomorrow's bookings", oracle=oracle_bookings_tomorrow,
		expected_tools=("list_records",), source="sheet example"),
	Case("T05", "إيه المنتجات اللي قربت تخلص؟", "list", "library-stock", "items at or below their reorder level", oracle=oracle_running_out,
		expected_tools=("run_report", "list_records"), source="sheet example"),
]
