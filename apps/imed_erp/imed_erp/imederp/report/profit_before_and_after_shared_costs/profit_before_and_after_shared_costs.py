# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Profit Before and After Shared Costs (RPT-02): each business's profit for a period, before and after its share of
# the shared premises' expenses (مصروفات المقر المشتركة, EXP-03/04), from the ledger (business_figures.py).
#
#   Revenue                    income accounts, credit - debit
#   Direct Expenses            the business's own expenses: the ledger's, less the part split onto it from the
#                              shared premises
#   Shared Costs Allocated     that part: what ERPNext split onto the business from a shared line, as posted
#                              (Allocation Rule -> Cost Center Allocation), read back from the documents
#   Profit Before Allocation   Revenue - Direct Expenses
#   Profit After Allocation    Revenue - Direct Expenses - Shared Costs Allocated: the ledger's profit
#
# The shared premises have their own row: the shared expenses of the period (split or not) before the allocation,
# what is still on the shared cost center after it. Each expense is in one column of one row only, so both profit
# columns add up to the same total, the ledger's profit for the businesses shown (checked on every run).
#
# Nothing is simulated: a shared expense no rule covered (its date before the first rule) stays on the shared cost
# center in the ledger, and the report says that the profit after allocation is incomplete for the period.

import frappe
from frappe import _
from frappe.utils import flt, fmt_money

from imed_erp.imederp.business_figures import (
	NO_COST_CENTER,
	allocated,
	check_dates,
	company,
	ledger,
	shared_cost_centers,
	subtree,
)
from imed_erp.imederp.owner_figures import check_reader


def execute(filters=None):
	check_reader()
	filters = frappe._dict(filters or {})
	from_date, to_date = check_dates(filters.from_date, filters.to_date)
	tree = subtree(filters.cost_center)
	result = get_result(tree, from_date, to_date, include_unassigned=not filters.cost_center)
	return get_columns(), result.data, get_message(result), None, get_summary(result)


def get_columns():
	return [
		{"label": _("Business"), "fieldname": "business", "fieldtype": "Data", "width": 230},
		{
			"label": _("Cost Center"),
			"fieldname": "cost_center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"hidden": 1,
		},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 130},
		{
			"label": _("Direct Expenses"),
			"fieldname": "direct_expenses",
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"label": _("Shared Costs Before Allocation"),
			"fieldname": "shared_before",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": _("Profit Before Allocation"),
			"fieldname": "profit_before",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": _("Shared Costs Allocated"),
			"fieldname": "shared_allocated",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": _("Shared Costs Not Allocated"),
			"fieldname": "shared_unallocated",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": _("Profit After Allocation"),
			"fieldname": "profit_after",
			"fieldtype": "Currency",
			"width": 150,
		},
	]


FIELDS = ["revenue", "direct_expenses", "shared_before", "shared_allocated", "shared_unallocated"]


def get_result(tree, from_date, to_date, include_unassigned=False):
	"""frappe._dict(data, totals, ledger_profit, unallocated, shared_total, reconciles)."""
	names = [row.name for row in tree]
	totals = ledger(from_date, to_date, None if include_unassigned else names)
	split = allocated(from_date, to_date)
	shared = shared_cost_centers()

	def figures(cost_center):
		revenue = -flt(totals.get((cost_center, "Income")))
		expenses = flt(totals.get((cost_center, "Expense")))
		if cost_center in shared:
			# Everything the shared premises spent in the period, split or not, and what is still on them.
			still_there = flt(expenses - revenue, 2)
			return {
				"revenue": 0.0,
				"direct_expenses": 0.0,
				"shared_before": flt(still_there + flt(split.by_shared.get(cost_center)), 2),
				"shared_allocated": 0.0,
				"shared_unallocated": still_there,
			}
		# The part of the ledger's figures that came from a shared line is not the business's own.
		split_income = flt(split.by_business.get((cost_center, "Income")))
		split_expense = flt(split.by_business.get((cost_center, "Expense")))
		return {
			"revenue": flt(revenue + split_income, 2),
			"direct_expenses": flt(expenses - split_expense, 2),
			"shared_before": 0.0,
			"shared_allocated": flt(split_expense + split_income, 2),
			"shared_unallocated": 0.0,
		}

	own = {row.name: figures(row.name) for row in tree if not row.is_group}
	if include_unassigned and (
		totals.get((NO_COST_CENTER, "Income")) or totals.get((NO_COST_CENTER, "Expense"))
	):
		own[NO_COST_CENTER] = figures(NO_COST_CENTER)

	data = []
	for business in tree:
		under = [b.name for b in tree if business.lft <= b.lft and b.rgt <= business.rgt]
		if business is tree[0] and NO_COST_CENTER in own:
			under.append(NO_COST_CENTER)
		row = {field: flt(sum(own.get(name, {}).get(field, 0) for name in under), 2) for field in FIELDS}
		data.append(
			{
				"business": business.label,
				"cost_center": business.name,
				"parent_cost_center": business.parent if business is not tree[0] else None,
				"indent": business.depth - tree[0].depth,
				"is_group": business.is_group,
				"is_shared": business.name in shared,
				**with_profit(row),
			}
		)
	if NO_COST_CENTER in own:
		data.append(
			{
				"business": _("No business on the entry"),
				"cost_center": None,
				"parent_cost_center": tree[0].name,
				"indent": 1,
				**with_profit(own[NO_COST_CENTER]),
			}
		)

	top = data[0]
	shown_shared = [name for name in own if name in shared]
	# The ledger's profit for the businesses shown, read on its own.
	ledger_profit = flt(-sum(totals.values()), 2)
	# Profit before allocation differs from it only by the shared costs split across the edge of what is shown: onto
	# a business shown from shared premises not shown, or the other way round. With every business shown, by nothing.
	split_onto_shown = sum(amount for (name, _root_type), amount in split.by_business.items() if name in own)
	split_from_shown = sum(flt(split.by_shared.get(name)) for name in shown_shared)
	expected_before = flt(ledger_profit + split_onto_shown - split_from_shown, 2)
	return frappe._dict(
		data=data,
		totals=top,
		ledger_profit=ledger_profit,
		unallocated=flt(sum(own[name]["shared_unallocated"] for name in shown_shared), 2),
		shared_total=flt(sum(own[name]["shared_before"] for name in shown_shared), 2),
		reconciles=abs(top["profit_after"] - ledger_profit) < 0.01
		and abs(top["profit_before"] - expected_before) < 0.01,
	)


def with_profit(row):
	row = dict(row)
	row["profit_before"] = flt(row["revenue"] - row["direct_expenses"] - row["shared_before"], 2)
	row["profit_after"] = flt(
		row["revenue"] - row["direct_expenses"] - row["shared_allocated"] - row["shared_unallocated"], 2
	)
	return row


def get_message(result):
	currency = frappe.get_cached_value("Company", company(), "default_currency")
	notes = [
		_(
			"Profit before allocation keeps the shared premises' expenses on their own row; profit after allocation "
			"is the ledger's, with each business's share as ERPNext posted it."
		)
	]
	if result.unallocated:
		notes.append(
			"<b>"
			+ _(
				"{0} of the shared premises' expenses in this period were not split (no Allocation Rule covered their "
				"dates): the profit after allocation is incomplete for the businesses."
			).format(fmt_money(result.unallocated, currency=currency))
			+ "</b>"
		)
	elif not result.shared_total:
		notes.append(_("No shared premises' expenses in this period."))
	if not result.reconciles:
		notes.append("<b>" + _("The totals do not agree with the ledger. Tell the developer.") + "</b>")
	return "<br>".join(notes)


def get_summary(result):
	top = result.totals
	summary = [
		{
			"label": _("Profit Before Allocation"),
			"value": top["profit_before"],
			"datatype": "Currency",
			"indicator": indicator(top["profit_before"]),
		},
		{
			"label": _("Profit After Allocation"),
			"value": top["profit_after"],
			"datatype": "Currency",
			"indicator": indicator(top["profit_after"]),
		},
		{
			"label": _("Shared Costs Allocated"),
			"value": top["shared_allocated"],
			"datatype": "Currency",
			"indicator": "Blue",
		},
	]
	if result.unallocated:
		summary.append(
			{
				"label": _("Shared Costs Not Allocated"),
				"value": result.unallocated,
				"datatype": "Currency",
				"indicator": "Orange",
			}
		)
	summary.append(
		{
			"label": _("Agrees with the Ledger"),
			"value": _("Yes") if result.reconciles else _("No"),
			"datatype": "Data",
			"indicator": "Green" if result.reconciles else "Red",
		}
	)
	return summary


def indicator(value):
	return "Green" if value > 0 else "Red" if value < 0 else "Gray"
