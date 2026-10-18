# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The libraries' printing day by day (PRN-01, PRN-02, PRN-09): each machine's counter against what was sold, and
# the shortfall in sheets and in money, from the submitted Daily Counter Readings. A sale does not say which
# machine printed it, so the day's sold sheets are shared out by each machine's share of the day's printing (its
# Utilization); a machine's variance is its consumption less its share, valued at its own cost per sheet, so the
# machines add up to the library's day, shown under them. get_list applies User Permissions: a branch manager sees
# her own library.

import frappe
from frappe import _
from frappe.utils import cint, flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "reading_date", "fieldtype": "Date", "width": 100},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Cost Center", "width": 160},
		{"label": _("Machine"), "fieldname": "machine", "fieldtype": "Link", "options": "Printing Machine", "width": 160},
		{"label": _("Type"), "fieldname": "machine_type", "fieldtype": "Data", "width": 70},
		{"label": _("Consumed Sheets"), "fieldname": "consumed", "fieldtype": "Int", "width": 110},
		{"label": _("Utilization (%)"), "fieldname": "utilization", "fieldtype": "Percent", "width": 100},
		{"label": _("Sold Sheets"), "fieldname": "sold", "fieldtype": "Float", "precision": 1, "width": 100},
		{"label": _("Variance (Sheets)"), "fieldname": "variance", "fieldtype": "Float", "precision": 1, "width": 110},
		{"label": _("Cost per Sheet"), "fieldname": "cost_per_sheet", "fieldtype": "Currency", "precision": 4, "width": 100},
		{"label": _("Variance Value"), "fieldname": "variance_value", "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	conditions = {"docstatus": 1, "reading_date": ["between", [filters.from_date, filters.to_date]]}
	if filters.branch:
		conditions["branch"] = filters.branch
	rows = []
	for day in frappe.get_list(
		"Daily Counter Reading",
		filters=conditions,
		fields=["name", "branch", "reading_date", "total_consumed", "sold_sheets", "variance", "cost_per_sheet", "variance_value"],
		order_by="reading_date, branch",
	):
		machines = frappe.get_all(
			"Daily Counter Reading Item",
			filters={"parent": day.name, "parenttype": "Daily Counter Reading"},
			fields=["machine", "machine_type", "consumed", "cost_per_sheet"],
			order_by="idx",
		)
		printed = sum(max(cint(m.consumed), 0) for m in machines)
		for m in machines:
			# Its share of the day's printing; on a day nothing was printed, the sales are shared equally.
			share = max(cint(m.consumed), 0) / printed if printed else 1 / len(machines)
			sold = flt(day.sold_sheets) * share
			variance = cint(m.consumed) - sold
			rows.append(
				{
					"reading_date": day.reading_date,
					"branch": day.branch,
					"machine": m.machine,
					"machine_type": m.machine_type,
					"consumed": m.consumed,
					"utilization": flt(share * 100, 1),
					"sold": flt(sold, 1),
					"variance": flt(variance, 1),
					"cost_per_sheet": m.cost_per_sheet,
					"variance_value": flt(variance * flt(m.cost_per_sheet), 2),
				}
			)
		rows.append(
			{
				"reading_date": day.reading_date,
				"branch": day.branch,
				"machine": None,
				"machine_type": _("Total"),
				"consumed": day.total_consumed,
				"utilization": 100 if machines else 0,
				"sold": day.sold_sheets,
				"variance": day.variance,
				"cost_per_sheet": day.cost_per_sheet,
				"variance_value": day.variance_value,
				"is_total": 1,
			}
		)
	return rows
