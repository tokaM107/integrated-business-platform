# The library system's own daily reports, rebuilt here from the mirrored invoices (Library Sales Document): Tanmya's
# "تقرير المبيعات اليومية" (each item sold, how many and for how much, under its item group) and "ملخص حركة
# الدكاترة" (what was sold on each doctor's name, and the doctor's share). The owner, 5 and 9 Nov 2026: "what the
# library system shows, shown here". Only issued documents not cancelled count; a sale adds, a return takes away;
# a line's value is its total as the library system has it (after its own discount; an invoice-wide discount is not
# shared out on the lines). Read through get_list, so a user sees only what their permissions show of the invoices.
# Lines read before 9 Nov 2026 carry no item group nor doctor's share until the connector reads them again.
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from imed_erp.imederp.library_sync.contract import RETURN_KINDS, SALES_KINDS

LINE = "`tabLibrary Sales Document Line`"
AMOUNTS = ("qty", "line_total", "discount_value", "doctor_share")


def lines(filters, key_fields, extra_fields=()):
	"""The period's lines grouped on key_fields (of the line), each group's sold and returned quantity, value,
	discount and doctor's share, and the number of sales invoices in it. extra_fields are carried, from the first
	line of the group."""
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
	wanted = list(dict.fromkeys(list(key_fields) + list(extra_fields) + list(AMOUNTS)))
	rows = frappe.get_list(
		"Library Sales Document",
		filters=conditions,
		fields=["name", "document_kind"] + [f"{LINE}.{f} as {f}" for f in wanted],
		order_by="reg_date",
	)
	groups = {}
	for row in rows:
		if row.get("qty") is None and row.get("line_total") is None:
			continue  # a document without lines
		key = tuple((row.get(f) or "").strip() for f in key_fields)
		g = groups.get(key)
		if g is None:
			g = groups[key] = frappe._dict(dict(zip(key_fields, key)), invoices=set())
			for f in extra_fields:
				g[f] = (row.get(f) or "").strip()
			for side in ("sold", "returned"):
				for f in ("qty", "value", "discount", "doctor_share"):
					g[f"{side}_{f}"] = 0.0
		side = "sold" if row.document_kind in SALES_KINDS else "returned"
		g[f"{side}_qty"] += flt(row.qty)
		g[f"{side}_value"] += flt(row.line_total)
		g[f"{side}_discount"] += flt(row.discount_value)
		g[f"{side}_doctor_share"] += flt(row.doctor_share)
		if side == "sold":
			g.invoices.add(row.name)
	out = []
	for g in groups.values():
		g.invoices = len(g.invoices)
		finish(g)
		out.append(g)
	out.sort(key=lambda g: -g.net_value)
	return out


def finish(g):
	"""A group's derived figures: before discount, net, rounded to the penny."""
	g.sold_before_discount = g.sold_value + g.sold_discount
	g.returned_before_discount = g.returned_value + g.returned_discount
	g.net_qty = g.sold_qty - g.returned_qty
	g.net_value = g.sold_value - g.returned_value
	g.net_discount = g.sold_discount - g.returned_discount
	g.net_before_discount = g.sold_before_discount - g.returned_before_discount
	g.doctor_share = g.sold_doctor_share - g.returned_doctor_share
	for f in ("sold_value", "sold_discount", "sold_before_discount", "returned_value", "returned_discount", "returned_before_discount", "net_value", "net_discount", "net_before_discount", "doctor_share"):
		g[f] = flt(g[f], 2)
	return g


def add_up(rows, **fields):
	"""One row holding the sums of rows (a group's total, or the day's)."""
	total = frappe._dict(fields, invoices=0)
	for f in ("sold_qty", "sold_value", "sold_discount", "sold_doctor_share", "returned_qty", "returned_value", "returned_discount", "returned_doctor_share"):
		total[f] = sum(flt(r.get(f)) for r in rows)
	return finish(total)


def money_columns(discount=False):
	columns = [{"label": _("Sold Qty"), "fieldname": "sold_qty", "fieldtype": "Int", "width": 90}]
	if discount:
		columns += [
			{"label": _("Value Before Discount"), "fieldname": "sold_before_discount", "fieldtype": "Currency", "width": 120},
			{"label": _("Discount"), "fieldname": "sold_discount", "fieldtype": "Currency", "width": 90},
		]
	return columns + [
		{"label": _("Sales"), "fieldname": "sold_value", "fieldtype": "Currency", "width": 120},
		{"label": _("Returned Qty"), "fieldname": "returned_qty", "fieldtype": "Int", "width": 90},
		{"label": _("Returns"), "fieldname": "returned_value", "fieldtype": "Currency", "width": 110},
		{"label": _("Net Qty"), "fieldname": "net_qty", "fieldtype": "Int", "width": 90},
		{"label": _("Net Sales"), "fieldname": "net_value", "fieldtype": "Currency", "width": 130},
	]


def summary(rows):
	sales = sum(flt(r.sold_value) for r in rows)
	returns = sum(flt(r.returned_value) for r in rows)
	return [
		{"label": _("Sales"), "value": flt(sales, 2), "datatype": "Currency", "indicator": "Green"},
		{"label": _("Returns"), "value": flt(returns, 2), "datatype": "Currency", "indicator": "Red"},
		{"label": _("Net Sales"), "value": flt(sales - returns, 2), "datatype": "Currency", "indicator": "Blue"},
	]


@frappe.whitelist()
def daily_sales(from_date=None, to_date=None, cost_center=None):
	"""Tanmya's daily sales report as it prints it (the owner, 9 Nov 2026, with its photos): each item group, its
	items (code, name; sold, returned and net, each as quantity, value before discount, discount and value) and the
	group's total, then the period's total. For the page library-daily-sales."""
	filters = {"from_date": from_date, "to_date": to_date, "cost_center": cost_center}
	items = lines(filters, ["product_code", "product_name"], extra_fields=["category_name"])
	groups = {}
	for item in items:
		groups.setdefault(item.category_name or _("Without a group"), []).append(item)
	ordered = sorted(groups.items(), key=lambda g: (g[0] == _("Without a group"), -sum(r.net_value for r in g[1])))
	return {
		"from_date": str(getdate(from_date or nowdate())),
		"to_date": str(getdate(to_date or nowdate())),
		"cost_center": cost_center,
		"currency": frappe.db.get_default("currency") or "EGP",
		"groups": [{"name": name, "items": sorted(rows, key=lambda r: (len(r.product_code or ""), r.product_code or "")), "total": add_up(rows)} for name, rows in ordered],
		"total": add_up(items),
	}
