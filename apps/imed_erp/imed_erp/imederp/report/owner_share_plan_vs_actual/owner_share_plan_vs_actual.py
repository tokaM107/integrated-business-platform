# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The owner's share planned in an edition's price against what its sales brought in (DOC-27), for each approved
# edition with sales. Planned: the profit per sheet x sheets, on every copy sold. Actual: what the copies sold for
# (net of discounts and returns, at whatever price they were sold, DOC-16) less the rest of the planned price of a
# copy (its costs, binding, marketing and the doctor's amount, which do not change once approved, DOC-25). A price
# set by hand, a discount or a carried copy sold at today's price shows up as the difference.

import frappe
from frappe import _
from frappe.utils import cint, flt

from imed_erp.imederp.edition_sales import FIELD


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Edition"), "fieldname": "edition", "fieldtype": "Link", "options": "Book Edition", "width": 200},
		{"label": _("Library"), "fieldname": "library", "fieldtype": "Link", "options": "Cost Center", "width": 150},
		{"label": _("Copies Sold"), "fieldname": "sold_qty", "fieldtype": "Float", "precision": 0, "width": 100},
		{"label": _("Planned per Copy"), "fieldname": "planned_per_copy", "fieldtype": "Currency", "width": 120},
		{"label": _("Planned Owner Share"), "fieldname": "planned", "fieldtype": "Currency", "width": 140},
		{"label": _("Sales"), "fieldname": "sales", "fieldtype": "Currency", "width": 120},
		{"label": _("Actual Owner Share"), "fieldname": "actual", "fieldtype": "Currency", "width": 140},
		{"label": _("Difference"), "fieldname": "difference", "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	conditions = {"docstatus": 1}
	if filters.library:
		conditions["cost_center"] = ["in", [filters.library, *frappe.db.get_descendants("Cost Center", filters.library)]]
	if filters.period:
		conditions["period"] = filters.period
	rows = []
	for edition in frappe.get_list(
		"Book Edition",
		filters=conditions,
		fields=["name", "cost_center", "owner_share", "pages", "calculated_price"],
		order_by="edition_date",
	):
		sold, sales = frappe.db.sql(
			f"""select sum(sii.stock_qty), sum(sii.base_net_amount) from `tabSales Invoice Item` sii
			join `tabSales Invoice` si on si.name = sii.parent
			where sii.{FIELD} = %s and si.docstatus = 1""",
			edition.name,
		)[0]
		sold, sales = flt(sold), flt(sales)
		if not sold and not sales:
			continue
		planned_per_copy = flt(edition.owner_share) * cint(edition.pages)
		rest_of_price = flt(edition.calculated_price) - planned_per_copy
		planned = flt(planned_per_copy * sold, 2)
		actual = flt(sales - rest_of_price * sold, 2)
		rows.append(
			{
				"edition": edition.name,
				"library": edition.cost_center,
				"sold_qty": sold,
				"planned_per_copy": planned_per_copy,
				"planned": planned,
				"sales": sales,
				"actual": actual,
				"difference": flt(actual - planned, 2),
			}
		)
	return rows
