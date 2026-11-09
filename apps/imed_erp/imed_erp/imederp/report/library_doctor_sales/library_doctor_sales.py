# What a library sold on each doctor's name in the period, and the doctor's share of it (Tanmya's "ملخص حركة
# الدكاترة"): see imederp/library_sync/reports.py. Lines sold on no doctor's name are one row, "Without a doctor".
from frappe import _

from imed_erp.imederp.library_sync.reports import lines, money_columns, summary


def execute(filters=None):
	rows = lines(filters, ["doctor_name"])
	for row in rows:
		row.doctor_name = row.doctor_name or _("Without a doctor")
	columns = [
		{"label": _("Doctor"), "fieldname": "doctor_name", "fieldtype": "Data", "width": 220},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 90},
	] + money_columns() + [
		{"label": _("Doctor Share"), "fieldname": "doctor_share", "fieldtype": "Currency", "width": 120},
	]
	return columns, rows, None, None, summary(rows)
