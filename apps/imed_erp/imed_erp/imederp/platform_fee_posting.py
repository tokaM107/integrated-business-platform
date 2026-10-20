# Platform fees in the doctor's account (APP-05, decided 19 Oct 2026): automatic, with every student.
#
# The doctor's account under his app agreement always holds what his courses are charged now. Whenever a course
# is counted again (app_course.recalculate_course: a subscription submitted, cancelled or ticked Withdrew, or new
# tiers), the difference between the course's Platform Fee and what is already in the ledger for it is posted as
# one Doctor Ledger Entry naming the course (app_course):
#   more   an Accrual: one more student, at the course's fee per student
#   less   an Adjustment of minus the difference: a cancelled student, or the 101st student moving the whole
#          course to the next tier (100 x 250 = 25,000 becomes 101 x 200 = 20,200: 4,800 less)
# so the entries of a course always add up to its fee. They are the system's: nobody approves them (they are not
# a deduction, DOC-22), and they are cancelled only by changing the course's subscriptions.
#
# In the accounts, each entry has its Journal Entry (the entry names it in journal_entry):
#   Dr مستحقات على الأطباء — رسوم المنصة   receivable, party: the doctor (a Customer)
#   Cr إيراد رسوم المنصة                    the group's revenue (APP-05)
# on the app's cost center; a smaller fee posts the other way round. The money collected from the doctor is a
# Collection (APP-06): Dr the treasury / Cr the same receivable (doctor_ledger_entry.post_collection).

import frappe
from frappe import _
from frappe.utils import flt, today

from imed_erp.imederp.doctor_accrual import account
from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import BALANCE_SIGN

LEDGER = "Doctor Ledger Entry"
RECEIVABLE_ACCOUNT = "مستحقات على الأطباء — رسوم المنصة"
REVENUE_ACCOUNT = "إيراد رسوم المنصة"
# QA-16: the fee is the app's revenue, whoever subscribed the student.
APP_BUSINESS = "تطبيق BA Plus"


def app_cost_center(company=None):
	company = company or frappe.defaults.get_global_default("company")
	return f"{APP_BUSINESS} - {frappe.get_cached_value('Company', company, 'abbr')}"


def posted(course):
	"""What the ledger holds for the course."""
	entries = frappe.get_all(LEDGER, filters={"app_course": course, "docstatus": 1}, fields=["entry_type", "amount"])
	return flt(sum(BALANCE_SIGN.get(entry.entry_type, 0) * flt(entry.amount) for entry in entries), 2)


def post_fee_change(course, date=None):
	"""Bring the doctor's account to the course's fee. Returns the entry posted, or None when nothing changed."""
	course = frappe.db.get_value(
		"App Course",
		course,
		["name", "course_name", "agreement", "doctor", "period", "subscriptions", "fee_per_student", "platform_fee_total"],
		as_dict=True,
	)
	difference = flt(flt(course.platform_fee_total) - posted(course.name), 2)
	if not difference:
		return None
	cost_center = app_cost_center()
	entry = frappe.get_doc(
		{
			"doctype": LEDGER,
			"agreement": course.agreement,
			"period": course.period,
			"entry_date": date or today(),
			"entry_type": "Accrual" if difference > 0 else "Adjustment",
			"amount": difference,
			"app_course": course.name,
			"remarks": _("Platform fee of {0}: {1} students x {2} = {3}").format(
				course.course_name, course.subscriptions, flt(course.fee_per_student), flt(course.platform_fee_total)
			),
		}
	)
	entry.journal_entry = post(entry, course.doctor, cost_center)
	# Whoever subscribes the student (a branch manager) cannot open the doctors' accounts; the course posts for them.
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	return entry


def post(entry, doctor, cost_center):
	company = frappe.db.get_value("Cost Center", cost_center, "company")
	amount = abs(flt(entry.amount))
	more = flt(entry.amount) > 0
	journal_entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": company,
			"posting_date": entry.entry_date,
			"accounts": [
				{
					"account": account(company, RECEIVABLE_ACCOUNT),
					"party_type": "Customer",
					"party": doctor,
					"cost_center": cost_center,
					"debit_in_account_currency": amount if more else 0,
					"credit_in_account_currency": 0 if more else amount,
				},
				{
					"account": account(company, REVENUE_ACCOUNT),
					"cost_center": cost_center,
					"debit_in_account_currency": 0 if more else amount,
					"credit_in_account_currency": amount if more else 0,
				},
			],
			"user_remark": entry.remarks,
		}
	)
	journal_entry.flags.ignore_permissions = True
	journal_entry.flags.from_doctor_accrual = True
	journal_entry.insert()
	journal_entry.submit()
	return journal_entry.name
