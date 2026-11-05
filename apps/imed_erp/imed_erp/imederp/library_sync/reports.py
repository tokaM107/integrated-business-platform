# The library system's own daily reports, rebuilt here from the mirrored invoices (Library Sales Document): Tanmya's
# "تقرير المبيعات اليومية" (each item sold, how many and for how much) and "ملخص حركة الدكاترة" (what was sold on
# each doctor's name). The owner, 5 Nov 2026: "we have Azarita's data, show it on the website". Only issued
# documents not cancelled count; a sale adds, a return takes away; amounts are the lines' totals as the library
# system has them (before an invoice-wide discount). Read through get_list, so a user sees only what their
# permissions show of the invoices.
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from imed_erp.imederp.library_sync.contract import RETURN_KINDS, SALES_KINDS

LINE = "`tabLibrary Sales Document Line`"


def lines(filters, key_fields):
	"""The period's lines grouped on key_fields (of the line), each group's sold and returned quantity and value."""
	filters = frappe._dict(filters or {})
	start, end = getdate(filters.from_date or nowdate()), getdate(filters.to_date or nowdate())
	if start > end:
		frappe.throw(_("From Date must be before To Date."))
	conditions = {
		"reg_date": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]],
		"is_final": 1,
		"is_cancelled": 0,
		"document_kind": ["in", SALES_KINDS + RETURN_KINDS],
	}
	if filters.cost_center:
		conditions["cost_center"] = filters.cost_center
	rows = frappe.get_list(
		"Library Sales Document",
		filters=conditions,
		fields=["name", "document_kind"] + [f"{LINE}.{f} as {f}" for f in key_fields + ["qty", "line_total"]],
		order_by="reg_date",
	)
	groups = {}
	for row in rows:
		if row.get(key_fields[0]) is None and row.get("qty") is None:
			continue  # a document without lines
		key = tuple((row.get(f) or "").strip() for f in key_fields)
		g = groups.setdefault(key, frappe._dict(dict(zip(key_fields, key)), invoices=set(), sold_qty=0.0, sold_value=0.0, returned_qty=0.0, returned_value=0.0))
		if row.document_kind in SALES_KINDS:
			g.sold_qty += flt(row.qty)
			g.sold_value += flt(row.line_total)
			g.invoices.add(row.name)
		else:
			g.returned_qty += flt(row.qty)
			g.returned_value += flt(row.line_total)
	out = []
	for g in groups.values():
		g.invoices = len(g.invoices)
		g.net_qty = g.sold_qty - g.returned_qty
		g.net_value = flt(g.sold_value - g.returned_value, 2)
		g.sold_value, g.returned_value = flt(g.sold_value, 2), flt(g.returned_value, 2)
		out.append(g)
	out.sort(key=lambda g: -g.net_value)
	return out


def money_columns():
	return [
		{"label": _("Sold Qty"), "fieldname": "sold_qty", "fieldtype": "Int", "width": 100},
		{"label": _("Sales"), "fieldname": "sold_value", "fieldtype": "Currency", "width": 120},
		{"label": _("Returned Qty"), "fieldname": "returned_qty", "fieldtype": "Int", "width": 100},
		{"label": _("Returns"), "fieldname": "returned_value", "fieldtype": "Currency", "width": 110},
		{"label": _("Net Qty"), "fieldname": "net_qty", "fieldtype": "Int", "width": 90},
		{"label": _("Net Sales"), "fieldname": "net_value", "fieldtype": "Currency", "width": 130},
	]


def summary(rows):
	sales = sum(r.sold_value for r in rows)
	returns = sum(r.returned_value for r in rows)
	return [
		{"label": _("Sales"), "value": flt(sales, 2), "datatype": "Currency", "indicator": "Green"},
		{"label": _("Returns"), "value": flt(returns, 2), "datatype": "Currency", "indicator": "Red"},
		{"label": _("Net Sales"), "value": flt(sales - returns, 2), "datatype": "Currency", "indicator": "Blue"},
	]
