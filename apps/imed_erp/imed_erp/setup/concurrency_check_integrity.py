# Two sessions at once, for the races of the review of 2 Nov 2026 (docs/audits/architecture-audit-2026-11-02.md):
# the same student subscribed twice, the same week reviewed twice, two sales of one edition, the daily doctor
# accrual run twice on a missed sale, two printing sales on the last of the paper.
#
# Like concurrency_check.py (whose two-session runner it uses), it COMMITS its records ("_Conc ..."), so it refuses
# the main site. Run it on a throwaway copy:
#   docker exec frappe_docker-backend-1 bench --site restore-test execute imed_erp.setup.concurrency_check_integrity.run

import random
from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, today

from imed_erp.setup import concurrency_check
from imed_erp.setup.concurrency_check import APP, MAIN_SITE, agreement, customer, report, results, suffix


def at_once(first, second):
	"""concurrency_check.at_once; with frappe.flags.snapshot_off each session runs without MariaDB's snapshot
	isolation (as on MariaDB before 11.6, or a server configured without it), so the code's own locking is what is
	tested, not the database's refusal of a stale write."""
	if not frappe.flags.get("snapshot_off"):
		return concurrency_check.at_once(first, second)

	def plain(fn):
		def run():
			frappe.db.sql("set session innodb_snapshot_isolation = OFF")
			return fn()

		return run

	return concurrency_check.at_once(plain(first), plain(second))

COMPANY = "Mohamed Mamdouh group"
MAWASAH = "مكتبة المواساة - MMG"
MAWASAH_STORE = "خامات المواساة - MMG"
EDITIONS = "إصدارات الأطباء — المواساة - MMG"
AZARITA = "مكتبة الأزاريطة - MMG"
PAPER = "A4-PAPER"


def done(outcome):
	return sum(1 for state, _ in outcome if state == "done")


def check_same_student_twice():
	"""One student subscribed to one course from two sessions at once: one subscription, counted once."""
	tag = suffix()
	term = frappe.get_all("Academic Period", filters={"period_type": "Term", "is_closed": 0, "start_date": ("<=", today())}, pluck="name", limit=1)[0]
	course = frappe.get_doc({"doctype": "App Course", "course_name": f"_Conc Course {tag}", "agreement": agreement("App", tag), "period": term}).insert().name
	student = customer(f"_Conc Student {tag}")
	frappe.db.commit()

	def subscribe():
		doc = frappe.get_doc({"doctype": "App Subscription", "student": student, "course": course, "subscription_date": today(), "cost_center": APP}).insert()
		doc.submit()
		return doc.name

	outcome = at_once(subscribe, subscribe)
	submitted = frappe.db.count("App Subscription", {"course": course, "student": student, "docstatus": 1})
	counted = frappe.db.get_value("App Course", course, "subscriptions")
	report("same student subscribed twice at once", submitted == 1 == counted, f"{outcome}; submitted {submitted}, course counts {counted}")


def check_two_weekly_reviews():
	"""One week of one business reviewed from two sessions at once: one review."""
	settings = frappe.db.get_value("Cash Close Settings", None, ["week_starts_on", "week_ends_on"], as_dict=True) or {}
	frappe.db.set_single_value("Cash Close Settings", {"week_starts_on": None, "week_ends_on": None})
	week = add_days("2020-01-06", random.randint(0, 1500))
	frappe.db.commit()

	def review():
		return frappe.get_doc({"doctype": "Weekly Cash Reconciliation", "week_start": week, "business": AZARITA, "review_note": "concurrency"}).insert().name

	try:
		outcome = at_once(review, review)
		kept = frappe.db.count("Weekly Cash Reconciliation", {"week_start": week, "business": AZARITA, "docstatus": ("<", 2)})
		report("one week reviewed twice at once", kept == 1 == done(outcome), f"{outcome}; reviews kept {kept}")
	finally:
		frappe.db.set_single_value("Cash Close Settings", {"week_starts_on": settings.get("week_starts_on"), "week_ends_on": settings.get("week_ends_on")})
		frappe.db.commit()


def edition_fixture(tag, doctor_share=80, doctor_qty=50):
	from imed_erp.imederp.tests.test_edition_sales import IntegrationTestEditionSales as Sales

	item = Sales.make_item(f"_Conc Book {tag}")
	receipt = frappe.get_doc(
		{"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": COMPANY,
		 "items": [{"item_code": item, "qty": doctor_qty, "basic_rate": 60, "t_warehouse": EDITIONS}]}
	).insert()
	receipt.submit()
	term = Sales.make_period(f"_Conc Term {tag}", "2026-09-01", "2026-12-31")
	with patch("imed_erp.imederp.doctype.book_edition.book_edition.get_paper_cost", return_value=0.30):
		from imed_erp.imederp.doctype.book_edition.test_book_edition import make_agreement

		edition = frappe.get_doc(
			{"doctype": "Book Edition", "edition_name": f"_Conc Edition {tag}", "agreement": make_agreement("Books", doctor_share),
			 "item_code": item, "cost_center": MAWASAH, "edition_date": "2026-09-15", "period": term, "pages": 100,
			 "doctor_qty": doctor_qty, "extra_qty": 0}
		).insert()
		edition.submit()
	buyer = customer(f"_Conc Buyer {tag}")
	return item, edition.name, buyer


def sale(item, buyer, qty=1):
	invoice = frappe.get_doc(
		{"doctype": "Sales Invoice", "company": COMPANY, "customer": buyer, "cost_center": MAWASAH, "update_stock": 1,
		 "set_warehouse": EDITIONS, "items": [{"item_code": item, "qty": qty, "rate": 150, "warehouse": EDITIONS, "cost_center": MAWASAH}]}
	).insert()
	invoice.submit()
	return invoice.name


def check_two_sales_of_one_edition():
	"""Two sales of one edition submitted at once: the edition's Sold Qty and Remaining count both."""
	tag = suffix()
	item, edition, buyer = edition_fixture(tag)
	frappe.db.commit()
	outcome = at_once(lambda: sale(item, buyer), lambda: sale(item, buyer))
	sold, remaining, total = frappe.db.get_value("Book Edition", edition, ["sold_qty", "remaining_qty", "total_qty"])
	ok = sold == done(outcome) and remaining == total - sold
	report("two sales of one edition at once", ok, f"{outcome}; sold_qty {sold}, remaining {remaining} of {total}")


def check_two_daily_accruals():
	"""The daily safety net run twice at once on a sale the hooks missed: the doctor's amount counted once."""
	from imed_erp.imederp import doctor_accrual

	tag = suffix()
	item, edition, buyer = edition_fixture(tag)
	with patch.object(doctor_accrual, "accrue"):  # the hook missed it, as for an imported sale
		invoice = sale(item, buyer)
	frappe.db.commit()

	def daily():
		return doctor_accrual.catch_up([invoice], doctor_accrual.accrue, "concurrency {0}")

	outcome = at_once(daily, daily)
	entries = frappe.db.count("Doctor Ledger Entry", {"sales_invoice": invoice, "docstatus": 1})
	journals = frappe.db.count("Journal Entry", {"user_remark": ("like", f"%{invoice}%"), "docstatus": 1})
	report("daily accrual run twice at once", entries == 1 and journals == 1, f"{outcome}; ledger entries {entries}, journal entries {journals}")


def check_two_printing_sales_on_the_last_paper():
	"""Two printing sales at once, each within the paper in store but not both: both sales stand (the rule: a sale
	is never refused for paper), one issue is submitted, the other waits as a draft; the store never goes negative."""
	tag = suffix()
	buyer = customer(f"_Conc Printing {tag}")
	sheets = 300
	# The store is brought to 500 sheets: each sale fits, both do not.
	on_hand = flt(frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": MAWASAH_STORE}, "actual_qty"))
	if on_hand != 500:
		receipt = on_hand < 500
		frappe.get_doc(
			{"doctype": "Stock Entry", "stock_entry_type": "Material Receipt" if receipt else "Material Issue", "company": COMPANY,
			 "items": [{"item_code": PAPER, "qty": abs(500 - on_hand), "basic_rate": 0.26, ("t_warehouse" if receipt else "s_warehouse"): MAWASAH_STORE}]}
		).insert().submit()
	frappe.db.commit()

	def printing():
		invoice = frappe.get_doc(
			{"doctype": "Sales Invoice", "company": COMPANY, "customer": buyer, "posting_date": today(), "cost_center": MAWASAH,
			 "items": [{"item_code": "PRINT-SVC", "qty": sheets, "rate": 1, "cost_center": MAWASAH}]}
		).insert()
		invoice.submit()
		return invoice.name

	outcome = at_once(printing, printing)
	invoices = [value for state, value in outcome if state == "done"]
	issues = frappe.get_all("Stock Entry", filters={"sales_invoice_no": ("in", invoices or ["-"])}, fields=["docstatus"], pluck="docstatus")
	left = flt(frappe.db.get_value("Bin", {"item_code": PAPER, "warehouse": MAWASAH_STORE}, "actual_qty"))
	# A sale refused for paper breaks the rule; one refused by the database's stale-write check (error 1020, shown
	# to the user as "try again") is the platform's, and its retry then waits behind the first.
	for_paper = [value for state, value in outcome if state == "refused" and "NegativeStock" in value]
	retryable = [value for state, value in outcome if state == "refused" and "QueryDeadlockError" in value]
	ok = not for_paper and left >= 0 and (
		(len(invoices) == 2 and sorted(issues) == [0, 1] and left == 200) or (len(invoices) == 1 and retryable and issues == [1] and left == 200)
	)
	report("two printing sales on the last paper", ok, f"{outcome}; issues {sorted(issues)} (1 submitted, 0 draft), sheets left {left}")


def run(snapshot_off=0, only=None):
	frappe.flags.snapshot_off = bool(int(snapshot_off))
	if only:
		frappe.flags.concurrency_only = only.split(",")
	print("snapshot isolation", "OFF" if frappe.flags.snapshot_off else "as the server has it")
	if frappe.local.site == MAIN_SITE:
		print(f"REFUSED: concurrency_check_integrity commits records; run it on a throwaway copy, not {MAIN_SITE}.")
		return
	only = frappe.flags.get("concurrency_only")
	for check in (check_same_student_twice, check_two_weekly_reviews, check_two_sales_of_one_edition, check_two_daily_accruals, check_two_printing_sales_on_the_last_paper):
		if only and check.__name__ not in only:
			continue
		try:
			check()
		except Exception as e:
			frappe.db.rollback()
			report(check.__name__, False, f"could not run: {type(e).__name__}: {str(e)[:300]}")
	print(f"\n{sum(results)} of {len(results)} passed.")
