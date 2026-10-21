# Two sessions at once, for real (audit QA-10, QA-11, QA-12, QA-26, bookings of one resource, and on 21 Oct 2026
# two payments out of one cash box and two closes of one cash box).
#
# Each scenario opens two database connections in two threads, holds them at a barrier, then runs the same
# operation in both at the same moment and commits each. Then it reads what the database holds: one receipt, one
# payout, both students counted once, one day's screen, one booking, a cash box not below zero, one close.
#
# It COMMITS its records (a second connection sees only committed data), so it refuses to run on the main site:
# run it on a throwaway copy, e.g. the site a backup was restored into (docs/production-hardening.md):
#   docker exec frappe_docker-backend-1 bench --site restore-test execute imed_erp.setup.concurrency_check.run
#
# Its records are named "_Conc ..." and made fresh on every run.

import threading
from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, today

MAIN_SITE = "frontend"
COMPANY = "Mohamed Mamdouh group"
AZARITA = "مكتبة الأزاريطة - MMG"
HALLS = "قاعات Imed - MMG"
AZARITA_BOX = "خزينة مكتبة الأزاريطة - MMG"
HALLS_BOX = "خزينة سنتر Imed - MMG"
APP = "تطبيق BA Plus - MMG"
STUDIO = "استوديو X - MMG"

results = []


def report(scenario, ok, detail):
	results.append(ok)
	print(f"{'PASS' if ok else 'FAIL'}  {scenario}: {detail}")


def at_once(first, second):
	"""Run first() and second() in two sessions at the same moment; each commits, or rolls back on an error.
	Returns two (outcome, detail) pairs."""
	site, sites_path = frappe.local.site, frappe.local.sites_path
	barrier = threading.Barrier(2, timeout=60)
	outcome = [None, None]

	def worker(i, fn):
		frappe.init(site=site, sites_path=sites_path)
		frappe.connect()
		frappe.set_user("Administrator")
		try:
			barrier.wait()
			value = fn()
			frappe.db.commit()
			outcome[i] = ("done", value)
		except Exception as e:
			frappe.db.rollback()
			outcome[i] = ("refused", f"{type(e).__name__}: {frappe.utils.strip_html(str(e))[:140]}")
		finally:
			frappe.destroy()

	threads = [threading.Thread(target=worker, args=(i, fn)) for i, fn in enumerate((first, second))]
	for t in threads:
		t.start()
	for t in threads:
		t.join()
	# This session's reads come from a snapshot taken at its first read since its last commit: start a new one, so
	# the checks see what the two sessions committed.
	frappe.db.rollback()
	return outcome


def suffix():
	return frappe.generate_hash(length=5)


def customer(name, group=None):
	return frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_group": group or frappe.get_all("Customer Group", filters={"is_group": 0, "name": ("!=", "طبيب")}, pluck="name", limit=1)[0],
			"territory": frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)[0],
		}
	).insert().name


def agreement(kind, tag):
	return (
		frappe.get_doc(
			{
				"doctype": "Doctor Agreement",
				"agreement_name": f"_Conc {kind} {tag}",
				"doctor": customer(f"_Conc Doctor {tag}", "طبيب"),
				"agreement_type": kind,
				"start_date": "2026-09-01",
				"settlement_cycle": "Term",
				"terms": [{"valid_from": "2026-09-01", "amount_per_copy": 80}],
			}
		)
		.insert()
		.submit()
		.name
	)


def check_transfer_receipt():
	"""QA-10: two people confirm the receipt of one transfer at once."""
	fund(AZARITA_BOX, AZARITA, 1000)
	transfer = frappe.get_doc(
		{
			"doctype": "Inter Business Transfer",
			"posting_date": today(),
			"from_business": AZARITA,
			"from_treasury": AZARITA_BOX,
			"to_business": HALLS,
			"to_treasury": HALLS_BOX,
			"amount": 123,
			"reason": "_Conc transfer",
			"period": frappe.get_all("Academic Period", filters={"period_type": "Term", "is_closed": 0}, pluck="name", limit=1)[0],
		}
	).insert()
	transfer.submit()
	frappe.db.commit()
	confirm = lambda: frappe.get_doc("Inter Business Transfer", transfer.name).confirm_receipt()
	outcome = at_once(confirm, confirm)
	receipts = frappe.db.count("Journal Entry", {"user_remark": ("like", f"%{transfer.name}: received%"), "docstatus": 1})
	status = frappe.db.get_value("Inter Business Transfer", transfer.name, "status")
	report("QA-10 transfer confirmed twice at once", receipts == 1 and status == "Received", f"{outcome}; receipt journal entries: {receipts}; status {status}")


def payout(agreement_name, amount):
	def make():
		doc = frappe.get_doc(
			{
				"doctype": "Doctor Ledger Entry",
				"agreement": agreement_name,
				"entry_type": "Payout",
				"amount": amount,
				"entry_date": today(),
				"treasury": AZARITA_BOX,
			}
		).insert()
		doc.submit()
		return doc.name

	return make


def box_balance(box):
	return flt(
		frappe.db.sql("select sum(debit - credit) from `tabGL Entry` where account = %s and is_cancelled = 0", box)[0][0], 2
	)


def capital():
	return frappe.get_all("Account", filters={"company": COMPANY, "root_type": "Equity", "is_group": 0}, pluck="name", limit=1)[0]


def cash_entry(box, business, amount, submit=True):
	"""Cash into (or, below zero, out of) a box against capital, dated today."""
	doc = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"company": COMPANY,
			"posting_date": today(),
			"user_remark": "_Conc cash",
			"accounts": [
				{"account": box, "debit_in_account_currency": max(amount, 0), "credit_in_account_currency": max(-amount, 0), "cost_center": business},
				{"account": capital(), "debit_in_account_currency": max(-amount, 0), "credit_in_account_currency": max(amount, 0), "cost_center": business},
			],
		}
	).insert()
	if submit:
		doc.submit()
	return doc.name


def fund(box, business, at_least):
	"""Cash into the box today so that it holds at least `at_least` from today on (committed; copy site only)."""
	held = box_balance(box)
	if held < at_least:
		cash_entry(box, business, at_least - held)
		frappe.db.commit()


def books_agreement_owed(amount, tag):
	name = agreement("Books", tag)
	frappe.get_doc(
		{"doctype": "Doctor Ledger Entry", "agreement": name, "entry_type": "Accrual", "amount": amount, "entry_date": today()}
	).insert().submit()
	frappe.db.commit()
	return name


def check_two_payouts(lock=True):
	"""QA-11: two payouts of 300 from an agreement owing 500, at once. With the lock one is refused; without it
	(lock=False, the code before the fix) both may pass and overdraw it."""
	from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import get_balance

	name = books_agreement_owed(500, suffix())
	# The box holds enough for both: only the agreement's balance is under test here.
	fund(AZARITA_BOX, AZARITA, 1000)
	if lock:
		outcome = at_once(payout(name, 300), payout(name, 300))
	else:
		with patch("imed_erp.imederp.doctype.doctor_ledger_entry.doctor_ledger_entry.lock_agreement"):
			outcome = at_once(payout(name, 300), payout(name, 300))
	paid = frappe.db.count("Doctor Ledger Entry", {"agreement": name, "entry_type": "Payout", "docstatus": 1})
	balance = flt(get_balance(name))
	label = "QA-11 two payouts at once" + ("" if lock else " WITHOUT the lock (the code before the fix)")
	if lock:
		report(label, paid == 1 and balance == 200, f"{outcome}; payouts posted: {paid}; balance {balance}")
	else:
		# Not a pass or fail of the system: it shows whether the race is real on this database.
		print(f"INFO  {label}: {outcome}; payouts posted: {paid}; balance {balance}")


def check_two_subscriptions():
	"""QA-12: two students subscribe to one course at once; both are counted and charged once."""
	from imed_erp.imederp.platform_fee_posting import posted

	tag = suffix()
	app = agreement("App", tag)
	term = frappe.get_all("Academic Period", filters={"period_type": "Term", "is_closed": 0, "start_date": ("<=", today())}, pluck="name", limit=1)[0]
	course = frappe.get_doc({"doctype": "App Course", "course_name": f"_Conc Course {tag}", "agreement": app, "period": term}).insert().name
	students = [customer(f"_Conc Student {tag} {i}") for i in (1, 2)]
	frappe.db.commit()

	def subscribe(student):
		def make():
			doc = frappe.get_doc(
				{"doctype": "App Subscription", "student": student, "course": course, "subscription_date": today(), "cost_center": APP}
			).insert()
			doc.submit()
			return doc.name

		return make

	outcome = at_once(subscribe(students[0]), subscribe(students[1]))
	done = sum(1 for o in outcome if o[0] == "done")
	counted, fee, total = frappe.db.get_value("App Course", course, ["subscriptions", "fee_per_student", "platform_fee_total"])
	submitted = frappe.db.count("App Subscription", {"course": course, "docstatus": 1})
	ok = counted == submitted == done and flt(total) == flt(fee) * submitted and flt(posted(course)) == flt(total)
	report(
		"QA-12 two subscriptions at once",
		ok,
		f"{outcome}; submitted {submitted}, course counts {counted}, fee {fee} x {counted} = {total}, posted to the doctor {posted(course)}",
	)


def check_two_day_screens():
	"""QA-26: two people save a library's counters for the same day at once: one screen a day."""
	from imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading import get_machines

	libraries = [
		branch
		for branch in (AZARITA, "مكتبة المواساة - MMG")
		if get_machines(branch)
		and not frappe.db.exists("Daily Counter Reading", {"branch": branch, "reading_date": today(), "docstatus": ("<", 2)})
	]
	if not libraries:
		report("QA-26 two day screens at once", False, "every library already has today's screen on this site; run on another day")
		return
	library = libraries[0]

	def screen():
		doc = frappe.new_doc("Daily Counter Reading")
		doc.update({"branch": library, "reading_date": today()})
		for row in get_machines(library):
			opening = row["opening_reading"] if row["opening_reading"] is not None else 1000
			row.update({"opening_reading": opening, "closing_reading": opening + 10})
			doc.append("machines", row)
		doc.insert()
		return doc.name

	outcome = at_once(screen, screen)
	saved = frappe.db.count("Daily Counter Reading", {"branch": library, "reading_date": today(), "docstatus": ("<", 2)})
	report(f"QA-26 two day screens at once ({library})", saved == 1, f"{outcome}; screens saved: {saved}")


def check_two_bookings():
	"""Two bookings of one studio resource for the same hour, at once: one is refused (STU-14)."""
	tag = suffix()
	item = f"_CONC-HOUR-{tag}"
	frappe.get_doc(
		{"doctype": "Item", "item_code": item, "item_name": item, "item_group": "الخدمات", "stock_uom": "ساعة", "is_stock_item": 0}
	).insert()
	frappe.get_doc({"doctype": "Item Price", "item_code": item, "price_list": "Standard Selling", "price_list_rate": 100}).insert()
	resource = frappe.get_doc(
		{"doctype": "Booking Resource", "resource_name": f"_Conc Room {tag}", "resource_type": "Studio Service", "cost_center": STUDIO, "item": item}
	).insert().name
	who = customer(f"_Conc Booker {tag}")
	frappe.db.commit()

	def book():
		return frappe.get_doc(
			{"doctype": "Booking", "resource": resource, "customer": who, "booking_date": add_days(today(), 3), "from_time": "10:00", "to_time": "11:00"}
		).insert().name

	outcome = at_once(book, book)
	saved = frappe.db.count("Booking", {"resource": resource, "status": ("not in", ("Cancelled", "No Show"))})
	report("Bookings of one resource and hour at once", saved == 1, f"{outcome}; bookings saved: {saved}")


def check_two_cash_payments():
	"""Two payments of 300 at once out of a box holding exactly 500 (cash_balance.py): one is paid, the other refused;
	the box ends at 200, not -100."""
	held = box_balance(HALLS_BOX)
	if held != 500:
		cash_entry(HALLS_BOX, HALLS, 500 - held) if held < 500 else cash_entry(HALLS_BOX, HALLS, -(held - 500))
		frappe.db.commit()
	# Saved first, so the two sessions meet at the box's lock when they submit, not at the naming series.
	first, second = cash_entry(HALLS_BOX, HALLS, -300, submit=False), cash_entry(HALLS_BOX, HALLS, -300, submit=False)
	frappe.db.commit()
	outcome = at_once(
		lambda: frappe.get_doc("Journal Entry", first).submit(), lambda: frappe.get_doc("Journal Entry", second).submit()
	)
	after = box_balance(HALLS_BOX)
	done = [o for o in outcome if o[0] == "done"]
	report("Two cash payments at once from a box holding 500", len(done) == 1 and after == 200, f"{outcome}; box now {after}")


def check_two_closes():
	"""Two closes of one cash box for one day at once: one is saved, the other refused (treasury_close.py)."""
	box, business = None, None
	from imed_erp.imederp.doctype.weekly_cash_reconciliation.weekly_cash_reconciliation import boxes

	for business_name, box_name in boxes():
		if not frappe.db.exists("Treasury Close", {"treasury": box_name, "close_date": (">=", today()), "docstatus": ("<", 2)}):
			box, business = box_name, business_name
			break
	if not box:
		report("Two closes of one box at once", False, "every box is already closed today on this site")
		return

	def close():
		# Named apart, so the two sessions meet at the box's lock, not at the naming series.
		doc = frappe.get_doc(
			{"doctype": "Treasury Close", "treasury": box, "business": business, "close_date": today(), "counted": 0, "note": "_Conc"}
		).insert(set_name=f"_Conc TCL {suffix()}")
		return doc.name

	outcome = at_once(close, close)
	saved = frappe.db.count("Treasury Close", {"treasury": box, "close_date": today(), "docstatus": ("<", 2)})
	report("Two closes of one box at once", saved == 1 and sum(o[0] == "done" for o in outcome) == 1, f"{outcome}; closes saved: {saved}")


def run():
	if frappe.local.site == MAIN_SITE:
		print(f"REFUSED: concurrency_check commits records; run it on a throwaway copy of the site, not {MAIN_SITE}.")
		return
	for check in (
		check_transfer_receipt, check_two_payouts, check_two_subscriptions, check_two_day_screens, check_two_bookings,
		check_two_cash_payments, check_two_closes,
	):
		try:
			check()
		except Exception as e:
			frappe.db.rollback()
			report(check.__name__, False, f"could not run: {type(e).__name__}: {str(e)[:200]}")
	check_two_payouts(lock=False)
	print(f"\n{sum(results)} of {len(results)} passed.")
