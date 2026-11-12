# Does the month's income cover the fixed expenses? (the owner, 12 Nov 2026, on his page under "today"): each month,
# the last six and this one, its income against its fixed expenses (rent, salaries, the utilities: electricity,
# water, gas, internet; the subscriptions and servers), coloured by the answer:
#
#   green   passed the fixed expenses: income above 110% of them
#   yellow  covers them, just: 100% to 110%
#   red     does not cover them: below 100%
#
# Read from the ledger (GL Entry, cancelled entries, openings and year-end closings left out), the group's company.
# This month's bills are not all in yet, so its fixed expenses are what was posted or, if more, the average of the
# last three months that had any: early in the month a green that is not there is never shown.
import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, nowdate

from imed_erp.imederp.owner_figures import COMPANY
from imed_erp.imederp.owner_yesterday import check_owner

# The fixed expenses' accounts (setup_expenses.py: the utility bills post to المرافق), by their names.
FIXED_ACCOUNTS = ("الإيجار", "المرافق", "الرواتب والأجور", "الاشتراكات والسيرفرات")
# Each bill under utilities shown on its own (Expense documents' categories), the rest of utilities as one.
UTILITY_BILLS = ("الكهرباء", "المياه", "الغاز", "الإنترنت")
UTILITIES = "المرافق"
MONTHS_BACK = 6
GREEN_FROM, YELLOW_FROM = 1.10, 1.00
AR_MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")


def fixed_accounts():
	return frappe.get_all(
		"Account",
		filters={"company": COMPANY, "is_group": 0, "root_type": "Expense", "account_name": ["in", FIXED_ACCOUNTS]},
		fields=["name", "account_name"],
	)


def by_month(start, end, accounts=None, root_type=None):
	"""{first day of the month: debit - credit} between start and end, on accounts or on a root type's."""
	conditions = [
		"gl.company = %(company)s",
		"gl.is_cancelled = 0",
		"gl.is_opening = 'No'",
		"gl.voucher_type != 'Period Closing Voucher'",
		"gl.posting_date between %(start)s and %(end)s",
	]
	values = {"company": COMPANY, "start": start, "end": end}
	if accounts is not None:
		if not accounts:
			return {}
		conditions.append("gl.account in %(accounts)s")
		values["accounts"] = tuple(accounts)
	if root_type:
		conditions.append("acc.root_type = %(root_type)s")
		values["root_type"] = root_type
	rows = frappe.db.sql(
		f"""select date_format(gl.posting_date, '%%Y-%%m-01'), sum(gl.debit - gl.credit)
		from `tabGL Entry` gl join `tabAccount` acc on acc.name = gl.account
		where {" and ".join(conditions)}
		group by date_format(gl.posting_date, '%%Y-%%m-01')""",
		values,
	)
	return {str(month): flt(value) for month, value in rows}


def state(income, fixed):
	if fixed <= 0:
		return "green" if income > 0 else "none"
	ratio = income / fixed
	if ratio > GREEN_FROM:
		return "green"
	if ratio >= YELLOW_FROM:
		return "yellow"
	return "red"


def breakdown(start, end, accounts):
	"""The fixed expenses of a month item by item: each account, utilities split into their bills (from the
	Expense documents' categories) and the rest of utilities."""
	totals = by_account(start, end, [a.name for a in accounts])
	items = []
	for a in accounts:
		value = flt(totals.get(a.name))
		if a.account_name == UTILITIES:
			bills = dict(
				frappe.db.sql(
					"""select expense_category, sum(amount) from `tabExpense`
					where docstatus = 1 and company = %(company)s and posting_date between %(start)s and %(end)s
						and expense_category in %(bills)s
					group by expense_category""",
					{"company": COMPANY, "start": start, "end": end, "bills": UTILITY_BILLS},
				)
			)
			for bill in UTILITY_BILLS:
				if flt(bills.get(bill)):
					items.append({"label": bill, "value": flt(bills[bill], 2)})
			rest = value - sum(flt(v) for v in bills.values())
			if flt(rest, 2) > 0:
				items.append({"label": _("مرافق تانية") if bills else UTILITIES, "value": flt(rest, 2)})
		elif value:
			items.append({"label": a.account_name, "value": flt(value, 2)})
	return items


def by_account(start, end, accounts):
	if not accounts:
		return {}
	return dict(
		frappe.db.sql(
			"""select account, sum(debit - credit) from `tabGL Entry`
			where company = %(company)s and is_cancelled = 0 and is_opening = 'No' and voucher_type != 'Period Closing Voucher'
				and posting_date between %(start)s and %(end)s and account in %(accounts)s
			group by account""",
			{"company": COMPANY, "start": start, "end": end, "accounts": tuple(accounts)},
		)
	)


def cover(today=None):
	today = getdate(today or nowdate())
	this_month = get_first_day(today)
	first = get_first_day(add_months(this_month, -MONTHS_BACK))
	accounts = fixed_accounts()
	income = by_month(first, today, root_type="Income")
	fixed = by_month(first, today, accounts=[a.name for a in accounts])
	months = []
	for i in range(MONTHS_BACK + 1):
		month = get_first_day(add_months(first, i))
		key = str(month)
		months.append(
			frappe._dict(
				month=key,
				label=AR_MONTHS[month.month - 1],
				income=flt(-income.get(key, 0), 2),
				fixed=flt(fixed.get(key, 0), 2),
				current=month == this_month,
			)
		)
	# This month's fixed expenses: what was posted, or the average of the last three months that had any.
	past = [m.fixed for m in months[:-1] if m.fixed > 0][-3:]
	expected = flt(sum(past) / len(past), 2) if past else 0.0
	now = months[-1]
	now.posted = now.fixed
	now.fixed = max(now.fixed, expected)
	now.estimated = now.fixed > now.posted
	for m in months:
		m.state = state(m.income, m.fixed)
		m.ratio = flt(m.income / m.fixed * 100, 0) if m.fixed > 0 else None
	# The fixed expenses item by item: this month's if all were posted, else the last full month's.
	detail_month = now if not now.estimated else next((m for m in reversed(months[:-1]) if m.fixed > 0), now)
	start = getdate(detail_month.month)
	end = min(get_last_day(start), today)
	return {
		"currency": frappe.get_cached_value("Company", COMPANY, "default_currency") or "EGP",
		"months": months,
		"now": now,
		"left": flt(now.income - now.fixed, 2),
		"detail": {"month": detail_month.label, "items": breakdown(start, end, accounts)},
		"limits": {"green": int(GREEN_FROM * 100), "yellow": int(YELLOW_FROM * 100)},
	}


@frappe.whitelist()
def get_cover():
	check_owner()
	return cover()
