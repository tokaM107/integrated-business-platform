# Opening stock: check the libraries' physical count before it becomes the opening balance (INT-08).
#
# Run from bench console:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/check_opening_stock.py").read(), {"frappe": frappe})
#
# 1. Copy setup/data/opening_stock_template.csv to setup/data/opening_stock.csv and fill one row per item and store
#    counted (columns in docs/OPENING_STOCK.md). Quantities are what was counted; costs are the approved ones.
# 2. Run with MAKE_DRAFTS = False (the default): every row is checked and printed with its errors and warnings,
#    and the total per store. Nothing is written.
# 3. Once no row has an error, set MAKE_DRAFTS = True and run again: one draft Stock Reconciliation (Opening
#    Stock) per branch is made. The owner or the accountant reviews and submits it; this script never submits.
# A store that already has an opening reconciliation is refused, so running it twice makes nothing twice.

import os
from collections import defaultdict

import frappe

from imed_erp.imederp.opening_stock import check_rows, make_drafts, read_sheet

COMPANY = "Mohamed Mamdouh group"
FILE = "/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/data/opening_stock.csv"
POSTING_DATE = ""  # "YYYY-MM-DD": the day of the count. Required.
MAKE_DRAFTS = False


def run():
	if not POSTING_DATE:
		print("STOP   Set POSTING_DATE at the top to the day of the count.")
		return
	if not os.path.exists(FILE):
		print(f"STOP   {FILE} not found. Copy opening_stock_template.csv to it and fill in the count.")
		return
	rows = check_rows(read_sheet(FILE), COMPANY, POSTING_DATE)
	if not rows:
		print("STOP   The count sheet has no rows.")
		return

	errors = [row for row in rows if row.errors]
	for row in rows:
		state = "ERROR" if row.errors else ("WARN " if row.warnings else "OK   ")
		print(f"{state} line {row.line}: {row.item_code} in {row.warehouse}: {row.counted_qty} {row.count_uom}")
		for message in row.errors + row.warnings:
			print(f"         - {message}")

	totals = defaultdict(lambda: [0, 0.0, 0.0])
	for row in rows:
		if not row.errors:
			total = totals[row.warehouse]
			total[0] += 1
			total[1] += row.stock_qty
			total[2] += row.value
	print()
	for warehouse, (count, qty, value) in sorted(totals.items()):
		print(f"{warehouse}: {count} items, {qty:,.2f} in stock units, value {value:,.2f}")
	print(f"\n{len(rows)} rows, {len(errors)} with errors, {sum(1 for r in rows if r.warnings and not r.errors)} with warnings.")

	if not MAKE_DRAFTS:
		print("DONE   Checked only; nothing was written. Set MAKE_DRAFTS = True once there are no errors.")
		return
	if errors:
		print("STOP   Fix the rows with errors first; no draft was made.")
		return
	made = make_drafts(rows, COMPANY, POSTING_DATE)
	frappe.db.commit()
	print(f"DONE   Draft opening reconciliations made, to review and submit: {', '.join(made)}")


run()
