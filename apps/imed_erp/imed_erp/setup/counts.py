# Copyright (c) 2026, toka mohamed and contributors
# License information in license.txt

"""Record counts of the doctypes that matter for a restore check (read-only), printed as JSON so a shell script can
compare two sites without quoting SQL:  bench --site <site> execute imed_erp.setup.counts.run"""

import frappe

DOCTYPES = (
	"Booking", "Customer", "Studio Hour Package", "Integration Import Log", "Booking Resource", "Doctor Agreement",
	"Book Edition", "Material Request", "Library Sales Document", "Sales Invoice", "Payment Entry", "Journal Entry",
	"GL Entry", "Stock Ledger Entry", "Expense", "Treasury Close", "Cash Handover", "User",
)


def run():
	return {doctype: frappe.db.count(doctype) for doctype in DOCTYPES if frappe.db.exists("DocType", doctype)}
