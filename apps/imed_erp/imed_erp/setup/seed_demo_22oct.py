# Sample records for the demo site (22 Oct 2026) of what was built that day, on top of setup/seed_cash_demo.py:
# BA Plus payments in cash and electronically, a day of printer counters read morning and evening (with a gap) and
# another read only in the morning, a teacher's prepaid studio hours partly used, and the weekly cash hand-over: one
# pending, one printed, signed and confirmed. For looking at the screens only; every record says (تجريبي).
#
# Refuses any site but "demo"; runs once (a second run finds its first record and stops):
#   docker exec frappe_docker-backend-1 bench --site demo execute imed_erp.setup.seed_demo_22oct.run

import io

import frappe
from frappe.utils import add_days, flt, today

DEMO_SITE = "demo"
MARK = "(تجريبي)"
AZARITA, MAWASAH, STUDIO, APP = "مكتبة الأزاريطة - MMG", "مكتبة المواساة - MMG", "استوديو X - MMG", "تطبيق BA Plus - MMG"
AZARITA_BOX, MAWASAH_BOX = "خزينة مكتبة الأزاريطة - MMG", "خزينة مكتبة المواساة - MMG"
SARA, RAGHAD, GILAN, MENNA, OWNER, ACCOUNTANT = (
	f"{u}@imed.local" for u in ("sara", "raghad", "gilan", "menna", "owner", "accountant")
)
TEACHER = f"أ. منى سامي {MARK}"
STUDIO_ROOM = f"استوديو التسجيل {MARK}"
STUDIO_ITEM = "STUDIO-REC-HOUR-DEMO"


def as_user(user, fn, *args, **kwargs):
	frappe.set_user(user)
	try:
		return fn(*args, **kwargs)
	finally:
		frappe.set_user("Administrator")


def run():
	if frappe.local.site != DEMO_SITE:
		print(f"REFUSED: seed_demo_22oct adds sample records; run it on the {DEMO_SITE} site only.")
		return
	if frappe.db.exists("App Payment", {"remarks": ("like", f"%{MARK}%")}):
		print("Already seeded: nothing done.")
		return
	frappe.set_user("Administrator")
	payments()
	counters()
	studio_hours()
	handovers()
	frappe.db.commit()
	print("Seeded: BA Plus payments, counters read twice, prepaid studio hours, hand-overs.")


def payments():
	# The demo's subscriptions of 18 Oct predate App Course, so a course of their own with two new students; their
	# platform fees post to the doctor's account as any subscription's do.
	agreement = frappe.get_all("Doctor Agreement", filters={"agreement_type": "App", "docstatus": 1}, pluck="name", limit=1)[0]
	course = frappe.get_doc(
		{"doctype": "App Course", "course_name": f"كورس الفسيولوجي {MARK}", "agreement": agreement, "period": f"الترم الأول 2026/2027 {MARK}"}
	).insert().name
	subs = []
	for student in (f"سلمى عادل {MARK}", f"عمر حسن {MARK}"):
		if not frappe.db.exists("Customer", student):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": student, "customer_type": "Individual",
				 "customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)[0],
				 "territory": frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)[0]}
			).insert()
		sub = frappe.get_doc(
			{"doctype": "App Subscription", "student": student, "course": course, "subscription_date": add_days(today(), -3), "cost_center": APP}
		).insert()
		sub.submit()
		subs.append(sub.name)
	for user, sub, method, treasury, branch, amount, ref in (
		(SARA, subs[0], "Cash", AZARITA_BOX, AZARITA, 600, None),
		(RAGHAD, subs[1 % len(subs)], "Cash", MAWASAH_BOX, MAWASAH, 450, None),
		(MENNA, subs[0], "InstaPay", "محفظة InstaPay - MMG", APP, 300, "IP-DEMO-1001"),
		(MENNA, subs[1 % len(subs)], "Bank Transfer", "خزينة تطبيق BA Plus - MMG", APP, 750, "TRF-DEMO-2002"),
	):
		def make():
			doc = frappe.get_doc(
				{
					"doctype": "App Payment", "subscription": sub, "posting_date": today(), "branch": branch, "payment_method": method,
					"treasury": treasury, "amount": amount, "reference_no": ref, "remarks": f"دفعة كورس {MARK}",
				}
			).insert()
			doc.submit()

		as_user(user, make)


def counters():
	from imed_erp.imederp.doctype.daily_counter_reading.daily_counter_reading import get_machines

	# Azarita: read in the morning and in the evening; the first machine printed 35 sheets after last closing.
	def full_day():
		doc = frappe.new_doc("Daily Counter Reading")
		doc.update({"branch": AZARITA, "reading_date": add_days(today(), -1)})
		for i, row in enumerate(get_machines(AZARITA)):
			start = row["previous_closing"] or 1000
			gap = 35 if i == 0 else 0
			row.update({"opening_reading": start + gap, "closing_reading": start + gap + 180 - 40 * i})
			if gap:
				row["gap_note"] = f"طباعة شغل متأخر بعد قفلة امبارح {MARK}"
			doc.append("machines", row)
		doc.insert()
		doc.submit()

	# Mawasah today: the morning readings only; the evening readings come at closing time.
	def morning():
		doc = frappe.new_doc("Daily Counter Reading")
		doc.update({"branch": MAWASAH, "reading_date": today()})
		for row in get_machines(MAWASAH):
			row.update({"opening_reading": row["previous_closing"] or 1000})
			doc.append("machines", row)
		doc.insert()

	as_user(SARA, full_day)
	as_user(RAGHAD, morning)


def studio_hours():
	if not frappe.db.exists("Item", STUDIO_ITEM):
		frappe.get_doc(
			{"doctype": "Item", "item_code": STUDIO_ITEM, "item_name": f"ساعة تسجيل استوديو {MARK}", "item_group": "الخدمات", "stock_uom": "Nos", "is_stock_item": 0}
		).insert()
		frappe.get_doc({"doctype": "Item Price", "item_code": STUDIO_ITEM, "price_list": "Standard Selling", "price_list_rate": 400}).insert()
	if not frappe.db.exists("Booking Resource", STUDIO_ROOM):
		frappe.get_doc(
			{"doctype": "Booking Resource", "resource_name": STUDIO_ROOM, "resource_type": "Studio Service", "cost_center": STUDIO, "item": STUDIO_ITEM}
		).insert()
	if not frappe.db.exists("Customer", TEACHER):
		frappe.get_doc(
			{
				"doctype": "Customer", "customer_name": TEACHER, "customer_type": "Individual",
				"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)[0],
			}
		).insert()

	def package():
		doc = frappe.get_doc(
			{"doctype": "Studio Hour Package", "customer": TEACHER, "resource": STUDIO_ROOM, "purchase_date": add_days(today(), -2),
			 "hours_purchased": 30, "price": 9000, "notes": f"باقة 30 ساعة تسجيل {MARK}"}
		).insert()
		doc.submit()
		from imed_erp.imederp.doctype.studio_hour_package.studio_hour_package import make_invoice

		make_invoice(doc.name)
		# Sessions of 2, 3 and 1.5 hours over two weeks: 23.5 hours left.
		for day, start, end in ((1, "10:00", "12:00"), (3, "14:00", "17:00"), (8, "09:00", "10:30")):
			frappe.get_doc(
				{"doctype": "Booking", "resource": STUDIO_ROOM, "customer": TEACHER, "booking_date": add_days(today(), day),
				 "from_time": start, "to_time": end, "hour_package": doc.name, "notes": f"تسجيل محاضرات {MARK}"}
			).insert()

	as_user(GILAN, package)


def signed_scan(name):
	"""The printed receipt as a PDF, standing in for the signed paper scanned back."""
	from frappe.utils.pdf import get_pdf

	try:
		html = frappe.get_print("Cash Handover", name, print_format="Cash Handover Receipt")
		return get_pdf(html)
	except Exception:
		from pypdf import PdfWriter

		writer, out = PdfWriter(), io.BytesIO()
		writer.add_blank_page(width=420, height=595)
		writer.add_metadata({"/Title": f"{name} {MARK}"})
		writer.write(out)
		return out.getvalue()


def handovers():
	from imed_erp.imederp.doctype.cash_handover.cash_handover import confirm_receipt

	def make(branch, box, amount, receiver, kind, note):
		doc = frappe.get_doc(
			{"doctype": "Cash Handover", "branch": branch, "treasury": box, "amount": amount, "handover_date": today(),
			 "handover_time": "21:30:00", "receiver_kind": kind, "receiver": receiver, "notes": note}
		).insert()
		doc.submit()
		return doc

	# Azarita's week, handed to the owner, printed, signed and confirmed.
	done = as_user(SARA, make, AZARITA, AZARITA_BOX, 2500, OWNER, "Owner", f"إيراد الأسبوع {MARK}")

	def sign_and_confirm():
		scan = frappe.get_doc(
			{"doctype": "File", "file_name": f"إيصال موقع {done.name}.pdf", "is_private": 1, "content": signed_scan(done.name),
			 "attached_to_doctype": "Cash Handover", "attached_to_name": done.name, "attached_to_field": "signed_receipt"}
		).insert()
		doc = frappe.get_doc("Cash Handover", done.name)
		doc.signed_receipt = scan.file_url
		doc.save()
		confirm_receipt(done.name, 2500)

	as_user(OWNER, sign_and_confirm)
	# Mawasah's, handed to the accountant: printed, waiting for the signed receipt and the confirmation.
	as_user(RAGHAD, make, MAWASAH, MAWASAH_BOX, flt(1200), ACCOUNTANT, "Accountant", f"جزء من إيراد الأسبوع {MARK}")
