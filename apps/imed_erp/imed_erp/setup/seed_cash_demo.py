# Sample cash closes for the demo site (21 Oct 2026): the daily close, discrepancies in each state and a weekly
# review in progress, on top of the demo transactions restored from the backup of 21 Oct. For looking at the
# screens only; every record says (تجريبي).
#
# Refuses any site but "demo": run it on the demo site only, never on the development or production site:
#   docker exec frappe_docker-backend-1 bench --site demo execute imed_erp.setup.seed_cash_demo.run
#
# Runs once: a second run finds its opening entry and stops.
#
# What it makes:
# - an opening cash entry dated 1 Sep 2026 (the fiscal year's first day) for every cash box, as the go-live count
#   would be, so the boxes start from realistic balances (without it Mawasah's demo day leaves it at -936.50);
# - closes from Saturday 17 to Tuesday 20 Oct, each by its branch manager: Mawasah (Raghad) 50 short on the
#   18th, 20 over on the 20th; Azarita (Sara) 30 short on the 19th, 15 short on the 20th; the halls (Nour) on the 18th;
# - the accountant's work on them: Mawasah's shortage under investigation, Azarita's 30 recommended for recovery
#   (waiting for the owner, who cannot approve it: the recovery policy is not approved), Azarita's 15 written off,
#   Mawasah's surplus waiting for an explanation;
# - the week of Saturday 17 Oct, all businesses, as a draft the accountant is reviewing.
# Today (the 21st) is left open: no box is closed yet.

import frappe
from frappe.utils import flt

DEMO_SITE = "demo"
COMPANY = "Mohamed Mamdouh group"
MARK = "(تجريبي)"
OPENING_REMARK = f"رصيد افتتاحي للخزائن {MARK} — بيانات عرض"
ACCOUNTANT = "accountant@imed.local"

OPENING = {
	"الخزينة الرئيسية - MMG": 2000,
	"خزينة مكتبة الأزاريطة - MMG": 1000,
	"خزينة مكتبة المواساة - MMG": 3000,
	"خزينة سنتر Imed - MMG": 500,
	"خزينة X Studio - MMG": 500,
}
AZARITA = ("خزينة مكتبة الأزاريطة - MMG", "مكتبة الأزاريطة - MMG", "sara@imed.local")
MAWASAH = ("خزينة مكتبة المواساة - MMG", "مكتبة المواساة - MMG", "raghad@imed.local")
HALLS = ("خزينة سنتر Imed - MMG", "قاعات Imed - MMG", "nour@imed.local")

# (box, date, counted minus expected, shift, note)
CLOSES = [
	(MAWASAH, "2026-10-17", 0, "مسائي", f"اليوم مطابق {MARK}"),
	(AZARITA, "2026-10-17", 0, "مسائي", f"اليوم مطابق {MARK}"),
	(MAWASAH, "2026-10-18", -50, "مسائي", f"العد أقل من المتوقع بـ 50 {MARK}"),
	(AZARITA, "2026-10-18", 0, "مسائي", f"اليوم مطابق {MARK}"),
	(HALLS, "2026-10-18", 0, "صباحي", f"اليوم مطابق {MARK}"),
	(MAWASAH, "2026-10-19", 0, "مسائي", f"اليوم مطابق {MARK}"),
	(AZARITA, "2026-10-19", -30, "صباحي", f"ناقص 30 بعد العد مرتين {MARK}"),
	(MAWASAH, "2026-10-20", 20, "مسائي", f"زيادة 20 مش معروف مصدرها {MARK}"),
	(AZARITA, "2026-10-20", -15, "مسائي", f"ناقص 15 {MARK}"),
]


def run():
	if frappe.local.site != DEMO_SITE:
		print(f"REFUSED: seed_cash_demo adds sample records; run it on the {DEMO_SITE} site only.")
		return
	if frappe.db.exists("Journal Entry", {"user_remark": OPENING_REMARK, "docstatus": 1}):
		print("Already seeded: nothing done.")
		return
	frappe.set_user("Administrator")
	opening_cash()
	discrepancies = {}
	for (box, business, user), date, off_by, shift, note in CLOSES:
		discrepancies[(box, date)] = close(box, business, user, date, off_by, shift, note)
	frappe.set_user(ACCOUNTANT)
	investigate(discrepancies[(MAWASAH[0], "2026-10-18")])
	recommend(discrepancies[(AZARITA[0], "2026-10-19")])
	write_off(discrepancies[(AZARITA[0], "2026-10-20")])
	week = frappe.get_doc(
		{
			"doctype": "Weekly Cash Reconciliation",
			"week_start": "2026-10-17",
			"review_note": f"الأسبوع لسه شغال: عجز المواساة تحت التحقيق، وزيادتها مستنية تفسير {MARK}",
		}
	).insert()
	frappe.set_user("Administrator")
	frappe.db.commit()
	print(f"Seeded: opening cash, {len(CLOSES)} closes, the week {week.name}.")


def opening_cash():
	equity = f"حقوق ملكية الأرصدة الافتتاحية - {frappe.get_cached_value('Company', COMPANY, 'abbr')}"
	cost_center = frappe.get_cached_value("Company", COMPANY, "cost_center")
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Opening Entry",
			"is_opening": "Yes",
			"company": COMPANY,
			"posting_date": "2026-09-01",
			"user_remark": OPENING_REMARK,
			"accounts": [
				{"account": box, "debit_in_account_currency": amount, "cost_center": cost_center}
				for box, amount in OPENING.items()
			]
			+ [{"account": equity, "credit_in_account_currency": sum(OPENING.values()), "cost_center": cost_center}],
		}
	).insert()
	entry.submit()


def close(box, business, user, date, off_by, shift, note):
	frappe.set_user(user)
	try:
		doc = frappe.get_doc(
			{"doctype": "Treasury Close", "treasury": box, "business": business, "close_date": date, "counted": 0, "shift": shift, "note": note}
		).insert()
		doc.counted = flt(doc.expected + off_by, 2)
		doc.submit()
		return doc.cash_discrepancy
	finally:
		frappe.set_user("Administrator")


def investigate(name):
	doc = frappe.get_doc("Cash Discrepancy", name)
	doc.investigation_notes = f"راجعنا فواتير اليوم مع رغد؛ لسه بنراجع إيصالات التحويلات {MARK}"
	doc.save()


def recommend(name):
	from imed_erp.imederp.doctype.cash_discrepancy import cash_discrepancy as cd

	doc = frappe.get_doc("Cash Discrepancy", name)
	doc.investigation_notes = f"العد اتعاد مع سارة؛ الفرق من باقي اتدفع زيادة لعميل {MARK}"
	doc.legal_check = 1
	doc.employees = []
	doc.append(
		"employees",
		{"user": AZARITA[2], "responsible": 1, "notified_on": "2026-10-20", "employee_response": f"تقر بالخطأ {MARK}", "recovery_amount": 30},
	)
	doc.save()
	cd.determine_responsibility(name)
	cd.recommend_recovery(name)


def write_off(name):
	from imed_erp.imederp.doctype.cash_discrepancy import cash_discrepancy as cd

	cd.write_off(name, f"فرق صغير مالوش سبب واضح؛ الشركة تتحمله {MARK}")
