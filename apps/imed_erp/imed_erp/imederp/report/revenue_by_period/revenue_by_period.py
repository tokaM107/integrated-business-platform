# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Revenue by Period (RPT-01): each business's revenue by day, week or month, from the ledger (business_figures.py):
# the income accounts, credit - debit, on submitted documents only, cancelled ones and their reversals left out.
# Revenue is what was invoiced (accrual basis, ACC-05), net of returns; money collected is not revenue and is not
# shown here (Cash Movements, Cash Box Balances). An invoice and the payment of it are therefore one revenue, never two.
#
# Rows are the business tree: an activity (a library, the halls, the studio, the app) and the group above it with
# the sum of its branches, the top row being the total of everything shown. Business filters one branch of the tree
# (a group stands for every business under it). A week starts on the day set in System Settings (Saturday here);
# the first and last periods are cut to the dates chosen.
#
# The owner and the accountant only (the company's figures): the report's roles, and owner_figures.check_reader.

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, format_date, get_first_day, get_first_day_of_week, getdate

from imed_erp.imederp.business_figures import NO_COST_CENTER, check_dates, ledger, subtree
from imed_erp.imederp.owner_figures import check_reader

PERIODICITIES = ("Daily", "Weekly", "Monthly")
# Columns at most: a year by day, five years by week or month.
MAX_PERIODS = 370


def execute(filters=None):
	check_reader()
	filters = frappe._dict(filters or {})
	from_date, to_date = check_dates(filters.from_date, filters.to_date)
	periodicity = filters.periodicity or "Monthly"
	if periodicity not in PERIODICITIES:
		frappe.throw(_("Choose Daily, Weekly or Monthly."))
	periods = get_periods(from_date, to_date, periodicity)
	if len(periods) > MAX_PERIODS:
		frappe.throw(_("Too many periods: choose fewer dates or a longer period."))

	tree = subtree(filters.cost_center)
	data = get_data(tree, periods, from_date, to_date, include_unassigned=not filters.cost_center)
	return get_columns(periods), data, message(), get_chart(periods, data), get_summary(data, periods)


def get_periods(from_date, to_date, periodicity):
	"""[(key, label, start, end)], the first and the last cut to the dates chosen."""
	periods, start = [], from_date
	while start <= to_date:
		if periodicity == "Daily":
			end = start
			label = format_date(start)
		elif periodicity == "Weekly":
			end = add_days(get_first_day_of_week(start), 6)
			label = _("Week of {0}").format(format_date(get_first_day_of_week(start)))
		else:
			end = add_days(add_months(get_first_day(start), 1), -1)
			label = format_date(start, "MMMM yyyy")
		end = min(getdate(end), to_date)
		periods.append((f"p_{start.strftime('%Y%m%d')}", label, start, end))
		start = add_days(end, 1)
	return periods


def get_columns(periods):
	columns = [
		{"label": _("Business"), "fieldname": "business", "fieldtype": "Data", "width": 240},
		{
			"label": _("Cost Center"),
			"fieldname": "cost_center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"hidden": 1,
		},
	]
	columns += [
		{"label": label, "fieldname": key, "fieldtype": "Currency", "width": 130}
		for key, label, _start, _end in periods
	]
	columns.append({"label": _("Total"), "fieldname": "total", "fieldtype": "Currency", "width": 140})
	return columns


def get_data(tree, periods, from_date, to_date, include_unassigned=False):
	names = [row.name for row in tree]
	totals = ledger(from_date, to_date, None if include_unassigned else names, by_date=True)

	# Each activity's revenue per period, then each group as the sum of the activities under it.
	period_of = {}
	for key, _label, start, end in periods:
		day = start
		while day <= end:
			period_of[day] = key
			day = add_days(day, 1)
	own = {}
	for (cost_center, root_type, posting_date), amount in totals.items():
		if root_type != "Income":
			continue
		key = period_of.get(getdate(posting_date))
		row = own.setdefault(cost_center, {})
		# Income is a credit: revenue is credit - debit (a return or a credit note takes it back).
		row[key] = row.get(key, 0) - amount

	data = []
	for business in tree:
		under = [b.name for b in tree if business.lft <= b.lft and b.rgt <= business.rgt]
		values = {
			key: flt(sum(own.get(name, {}).get(key, 0) for name in under), 2) for key, *_rest in periods
		}
		data.append(
			{
				"business": business.label,
				"cost_center": business.name,
				"parent_cost_center": business.parent if business is not tree[0] else None,
				"indent": business.depth - tree[0].depth,
				"is_group": business.is_group,
				**values,
				"total": flt(sum(values.values()), 2),
			}
		)
	# Revenue posted without a business, so the top row still adds up to the ledger.
	if include_unassigned and own.get(NO_COST_CENTER):
		values = {key: flt(own[NO_COST_CENTER].get(key, 0), 2) for key, *_rest in periods}
		data.append(
			{
				"business": _("No business on the entry"),
				"cost_center": None,
				"parent_cost_center": tree[0].name,
				"indent": 1,
				**values,
				"total": flt(sum(values.values()), 2),
			}
		)
		for key, value in {**values, "total": sum(values.values())}.items():
			data[0][key] = flt(data[0][key] + value, 2)
	return data


def message():
	return _(
		"Revenue invoiced (accrual basis), net of returns, from submitted documents only. Money collected is not "
		"revenue: see Cash Movements and Cash Box Balances."
	)


def get_chart(periods, data):
	if not data:
		return None
	return {
		"data": {
			"labels": [label for _key, label, *_rest in periods],
			"datasets": [{"name": data[0]["business"], "values": [data[0][key] for key, *_rest in periods]}],
		},
		"type": "bar",
		"colors": ["#0f766e"],
		"fieldtype": "Currency",
	}


def get_summary(data, periods):
	if not data:
		return []
	top = data[0]
	best = max(periods, key=lambda period: top[period[0]], default=None)
	activities = [row for row in data if not row.get("is_group") and row.get("cost_center")]
	leader = max(activities, key=lambda row: row["total"], default=None)
	summary = [
		{"label": _("Total Revenue"), "value": top["total"], "datatype": "Currency", "indicator": "Green"}
	]
	if best and top[best[0]]:
		summary.append({"label": _("Best Period"), "value": best[1], "datatype": "Data"})
	if leader and leader["total"]:
		summary.append({"label": _("Top Business"), "value": leader["business"], "datatype": "Data"})
	return summary
