# Each item a library sold in the period, under its item group, each group closed by its total and the period by
# the grand total (Tanmya's "تقرير المبيعات اليومية"): see imederp/library_sync/reports.py. Groups in the order of
# their net sales, the largest first; items the same within a group.
from frappe import _

from imed_erp.imederp.library_sync.reports import add_up, lines, money_columns, summary


def execute(filters=None):
	items = lines(filters, ["product_code", "product_name"], extra_fields=["category_name"])
	groups = {}
	for item in items:
		item.category_name = item.category_name or _("Without a group")
		groups.setdefault(item.category_name, []).append(item)
	data = []
	for name, rows in sorted(groups.items(), key=lambda g: -sum(r.net_value for r in g[1])):
		data.append({"product_name": name, "is_group": 1, "indent": 0})
		data += [dict(r, indent=1) for r in rows]
		data.append(dict(add_up(rows, product_name=_("Total of {0}").format(name), is_total=1), indent=1))
	if items:
		data.append(dict(add_up(items, product_name=_("Total Sales"), is_total=1, is_grand_total=1), indent=0))
	columns = [
		{"label": _("Product Code"), "fieldname": "product_code", "fieldtype": "Data", "width": 100},
		{"label": _("Product"), "fieldname": "product_name", "fieldtype": "Data", "width": 280},
	] + money_columns(discount=True)
	# The groups' totals and the grand total are rows of their own: no total row of Frappe's over them.
	return columns, data, None, None, summary(items), True
