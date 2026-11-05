# Each item a library sold in the period (Tanmya's "تقرير المبيعات اليومية"): see imederp/library_sync/reports.py.
from frappe import _

from imed_erp.imederp.library_sync.reports import lines, money_columns, summary


def execute(filters=None):
	rows = lines(filters, ["product_code", "product_name"])
	columns = [
		{"label": _("Product Code"), "fieldname": "product_code", "fieldtype": "Data", "width": 110},
		{"label": _("Product"), "fieldname": "product_name", "fieldtype": "Data", "width": 260},
	] + money_columns()
	return columns, rows, None, None, summary(rows)
