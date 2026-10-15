# Opening stock: checking the physical count before it becomes the opening balance (INT-08, LIB-02).
#
# The opening balance is ERPNext's own: a Stock Reconciliation with Purpose "Opening Stock" (Count Type
# "Opening", imederp/stock_count.py), posted against the temporary opening account (أرصدة افتتاحية مؤقتة), one
# per branch (set_branch_cost_center). This module adds nothing to it: it reads the count sheet
# (setup/data/opening_stock_template.csv), checks every row, and only when asked makes the reconciliations as
# drafts, for the owner or the accountant to review and submit. It never submits and never changes stock.
#
# Every quantity and cost comes from the sheet: what the libraries counted and the cost approved for it. Nothing
# missing is filled in.
#
# Checks, row by row:
#   the item exists, is a stock item, is not disabled, and has no batches or serial numbers (the sheet has none)
#   the store exists, is not a group, and is the company's
#   the unit is the item's stock unit or one of its conversions; the quantity is a number, not negative, and
#     whole for a unit that must be whole (sheet, ream, box)
#   the cost per unit is given (above zero), except in the damaged store, which holds stock at zero value
#     (imederp/damaged_stock.py)
#   the same item and store are on one row only
# and against what is already there:
#   an opening reconciliation (draft or submitted) already on the store: the row is refused, never posted twice
#   stock already recorded in the store on the opening date: shown with the difference to the count

import csv

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate

from imed_erp.imederp.customers import DIGITS
from imed_erp.imederp.stock_count import OPENING, OPENING_STOCK, branch_of

COLUMNS = [
	"warehouse",
	"item_code",
	"item_name",
	"count_uom",
	"counted_qty",
	"valuation_rate",
	"cost_source",
	"counted_by",
	"count_date",
	"notes",
]
REQUIRED = ("warehouse", "item_code", "count_uom", "counted_qty")


def read_sheet(path):
	with open(path, encoding="utf-8-sig", newline="") as sheet:
		reader = csv.DictReader(sheet)
		missing = [column for column in REQUIRED + ("valuation_rate",) if column not in (reader.fieldnames or [])]
		if missing:
			frappe.throw(_("The count sheet has no column {0}.").format(", ".join(missing)))
		# Line 1 is the header, so the first row is on line 2, as a spreadsheet shows it.
		return [frappe._dict({k: cstr(v).strip() for k, v in row.items() if k}, line=i) for i, row in enumerate(reader, start=2)]


def check_rows(rows, company, posting_date):
	"""Each row with its errors, warnings, the quantity and cost in the item's stock unit, and the stock already
	recorded. A row with an error is not used."""
	posting_date = getdate(posting_date)
	abbr = frappe.get_cached_value("Company", company, "abbr")
	seen = {}
	opened = opening_reconciliations(company)
	for row in rows:
		row.errors, row.warnings = [], []
		for column in REQUIRED:
			if not row.get(column):
				row.errors.append(_("{0} is empty.").format(column))
		if row.errors:
			continue

		item = frappe.db.get_value(
			"Item", row.item_code, ["item_name", "stock_uom", "is_stock_item", "disabled", "has_batch_no", "has_serial_no"], as_dict=True
		)
		if not item:
			row.errors.append(_("Item {0} not found.").format(row.item_code))
		elif not item.is_stock_item or item.disabled:
			row.errors.append(_("Item {0} is not an active stock item.").format(row.item_code))
		elif item.has_batch_no or item.has_serial_no:
			row.errors.append(_("Item {0} has batches or serial numbers, which the sheet does not record.").format(row.item_code))
		elif row.item_name and row.item_name != item.item_name:
			row.warnings.append(_("Item name on the sheet is {0}; the item is {1}.").format(row.item_name, item.item_name))

		store = frappe.db.get_value("Warehouse", row.warehouse, ["company", "is_group", "disabled", "custom_is_damaged_store"], as_dict=True)
		if not store and not row.warehouse.endswith(f" - {abbr}"):
			# The sheet may name the store without the company's abbreviation.
			row.warehouse = f"{row.warehouse} - {abbr}"
			store = frappe.db.get_value("Warehouse", row.warehouse, ["company", "is_group", "disabled", "custom_is_damaged_store"], as_dict=True)
		if not store:
			row.errors.append(_("Store {0} not found.").format(row.warehouse))
		elif store.company != company or store.is_group or store.disabled:
			row.errors.append(_("Store {0} is not one of {1}'s stores that hold stock.").format(row.warehouse, company))

		qty = to_number(row.counted_qty)
		rate = to_number(row.valuation_rate) if row.valuation_rate else None
		if qty is None:
			row.errors.append(_("Counted quantity {0} is not a number.").format(row.counted_qty))
		elif qty < 0:
			row.errors.append(_("Counted quantity cannot be negative."))
		if row.valuation_rate and rate is None:
			row.errors.append(_("Cost per unit {0} is not a number.").format(row.valuation_rate))

		if item and store and not row.errors:
			factor = conversion_factor(row.item_code, item.stock_uom, row.count_uom)
			if not factor:
				row.errors.append(
					_("{0} is not a unit of {1}; its units are: {2}.").format(row.count_uom, row.item_code, ", ".join(units_of(row.item_code, item.stock_uom)))
				)
			elif frappe.get_cached_value("UOM", row.count_uom, "must_be_whole_number") and qty != int(qty):
				row.errors.append(_("{0} is counted in whole {1}.").format(row.item_code, row.count_uom))
			if store.custom_is_damaged_store:
				# The damaged store keeps what waits to be sold by weight at zero value (imederp/damaged_stock.py).
				if rate:
					row.errors.append(_("{0} is the damaged store, which holds stock at zero value.").format(row.warehouse))
				rate = 0
			elif qty and (not rate or rate <= 0):
				# A count of nothing has nothing to value; anything counted needs its approved cost.
				row.errors.append(_("Cost per unit is missing: enter the approved cost, it is never guessed."))
			rate = rate or 0
			if factor and not row.errors:
				row.stock_uom = item.stock_uom
				row.stock_qty = flt(qty * factor, 6)
				row.stock_rate = flt(rate / factor, 9)
				row.value = flt(row.stock_qty * row.stock_rate, 2)

		key = (row.item_code, row.warehouse)
		if key in seen:
			row.errors.append(_("Same item and store as line {0}.").format(seen[key]))
		else:
			seen[key] = row.line
		if row.warehouse in opened:
			row.errors.append(_("Store {0} already has an opening balance: {1}.").format(row.warehouse, ", ".join(opened[row.warehouse])))
		if not row.errors:
			row.recorded_qty = recorded_qty(row.item_code, row.warehouse, posting_date)
			if row.recorded_qty:
				row.warnings.append(
					_("{0} {1} already recorded in the store on {2}; the opening count replaces it (difference {3}).").format(
						flt(row.recorded_qty), row.stock_uom, posting_date, flt(row.stock_qty - row.recorded_qty)
					)
				)
	return rows


def to_number(value):
	"""A number as typed on the sheet: thousands separators allowed, Arabic digits read as such."""
	text = cstr(value).translate(DIGITS).replace(",", "").replace("٬", "").replace("٫", ".")
	try:
		return float(text)
	except ValueError:
		return None


def conversion_factor(item_code, stock_uom, uom):
	if uom == stock_uom:
		return 1
	return flt(frappe.db.get_value("UOM Conversion Detail", {"parent": item_code, "uom": uom}, "conversion_factor"))


def units_of(item_code, stock_uom):
	return [stock_uom, *frappe.get_all("UOM Conversion Detail", filters={"parent": item_code, "uom": ["!=", stock_uom]}, pluck="uom")]


def recorded_qty(item_code, warehouse, posting_date):
	from erpnext.stock.utils import get_stock_balance

	return flt(get_stock_balance(item_code, warehouse, posting_date))


def opening_reconciliations(company):
	"""{store: [reconciliations]}: opening counts already made, draft or submitted."""
	opened = {}
	for name, warehouse in frappe.db.sql(
		"""select distinct sr.name, sri.warehouse from `tabStock Reconciliation` sr
		join `tabStock Reconciliation Item` sri on sri.parent = sr.name
		where sr.company = %s and sr.purpose = %s and sr.docstatus < 2""",
		(company, OPENING_STOCK),
	):
		opened.setdefault(warehouse, []).append(name)
	return opened


def make_drafts(rows, company, posting_date):
	"""One draft opening reconciliation per branch (a branch's stores are counted together, stock_count.py), from
	the rows without errors. Draft only: the owner or the accountant reviews and submits it."""
	if any(row.errors for row in rows):
		frappe.throw(_("Fix every row with an error before making the opening balance."))
	account = frappe.db.get_value("Account", {"company": company, "account_type": "Temporary", "is_group": 0}, "name")
	if not account:
		frappe.throw(_("{0} has no temporary opening account.").format(company))
	by_branch = {}
	for row in rows:
		by_branch.setdefault(branch_of(row.warehouse), []).append(row)
	made = []
	for branch, branch_rows in by_branch.items():
		doc = frappe.get_doc(
			{
				"doctype": "Stock Reconciliation",
				"company": company,
				"purpose": OPENING_STOCK,
				"custom_count_type": OPENING,
				"posting_date": posting_date,
				"set_posting_time": 1,
				"expense_account": account,
				"items": [
					{
						"item_code": row.item_code,
						"warehouse": row.warehouse,
						"qty": row.stock_qty,
						"valuation_rate": row.stock_rate,
						"allow_zero_valuation_rate": cint(not row.stock_rate),
					}
					for row in branch_rows
				],
			}
		)
		doc.insert()
		made.append(doc.name)
	return made
