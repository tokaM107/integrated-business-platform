# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A stock count (LIB-03, PRN-06): every item counted in one store, with or without a difference, so the
# owner sees that the branch counted and who did. ERPNext's Stock Reconciliation keeps only the rows with a
# difference and refuses a count where everything matched, so it cannot be the record of the count. On
# submit, this count makes one for the rows with a difference; ERPNext posts the shortage or surplus to the
# stock differences account, on the branch's cost center (imederp/stock_count.py).

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowtime, today

from imed_erp.imederp.stock_count import branch_of
from imed_erp.imederp.system_user import as_administrator

# Holders may date a count other than now (a count made yesterday, entered today); the reconciliation it makes
# is posted at that date and reposts everything after it, so branch managers cannot.
DATING_ROLE = "Accounts Manager"


class StockCount(Document):
	def validate(self):
		self.set_count_time()
		if frappe.db.get_value("Warehouse", self.store, "is_group"):
			frappe.throw(_("{0} is a group of stores. Choose the store that was counted.").format(self.store))
		self.branch = branch_of(self.store)
		self.check_own_branch()
		self.check_items()
		self.set_differences()

	def before_submit(self):
		if not can_date_counts() and getdate(self.posting_date) != getdate(today()):
			frappe.throw(
				_("This count was saved on {0}. The stock has moved since: count again today.").format(
					frappe.format_value(self.posting_date, {"fieldtype": "Date"})
				),
				title=_("Count Again"),
			)
		self.check_no_later_count()
		# The stock may have moved since the count was saved.
		self.set_differences()

	def check_no_later_count(self):
		"""QA-19: a count compares with the stock at its own time. One of the same store submitted since, and dated
		at or after it, has already set the stock from then on; this one would post the same shortage again."""
		later = frappe.db.sql(
			"""select name from `tabStock Count` where store = %s and docstatus = 1 and name != %s
			and timestamp(posting_date, posting_time) >= timestamp(%s, %s) limit 1""",
			(self.store, self.name, self.posting_date, self.posting_time),
		)
		if later:
			frappe.throw(
				_("Count {0} of this store was submitted after this one was made. Count again.").format(later[0][0]),
				title=_("Count Again"),
			)

	def set_count_time(self):
		# A branch manager's count is dated when it is first saved, whatever was typed: the quantities were
		# counted then, and later saves (a typo fixed) keep that moment so they are compared with the stock as
		# it was. Submitting keeps it too, and before_submit refuses one saved on another day.
		if self.docstatus != 0 or can_date_counts():
			return
		if self.is_new():
			self.posting_date, self.posting_time = today(), nowtime()
		else:
			self.posting_date, self.posting_time = frappe.db.get_value("Stock Count", self.name, ["posting_date", "posting_time"])

	def check_own_branch(self):
		# A branch manager counts only their own branch's stores (their cost centers in User Permission).
		allowed = frappe.get_all(
			"User Permission", filters={"user": frappe.session.user, "allow": "Cost Center"}, pluck="for_value"
		)
		if allowed and self.branch not in allowed:
			frappe.throw(
				_("{0} is not a store of your branch. You can count the stores of: {1}.").format(
					self.store, ", ".join(sorted(allowed))
				),
				title=_("Not Your Branch"),
			)

	def check_items(self):
		seen = set()
		for row in self.items:
			# Left empty is not counted; 0 is typed when there is none. An item fetched with Get Items in Store
			# and forgotten would otherwise be a shortage of everything recorded.
			if row.counted_qty is None:
				frappe.throw(
					_("Row #{0}: enter the counted quantity of {1}, 0 if there is none.").format(row.idx, row.item_code),
					title=_("Not Counted"),
				)
			if row.item_code in seen:
				frappe.throw(_("Row #{0}: {1} is counted twice.").format(row.idx, row.item_code))
			seen.add(row.item_code)
			if flt(row.counted_qty) < 0:
				frappe.throw(_("Row #{0}: the counted quantity cannot be negative.").format(row.idx))

	def set_differences(self):
		for row in self.items:
			row.recorded_qty, row.valuation_rate = recorded(row.item_code, self.store, self.posting_date, self.posting_time)
			# QA-05: paper sold before the count but still waiting as a draft issue is already gone from the shelf.
			row.recorded_qty -= pending_issues(row.item_code, self.store, self.posting_date, self.posting_time)
			row.difference_qty = flt(row.counted_qty) - row.recorded_qty
			row.difference_value = flt(row.difference_qty * row.valuation_rate, row.precision("difference_value"))
		self.items_counted = len(self.items)
		self.items_with_difference = len([row for row in self.items if row.difference_qty])
		self.total_difference_value = sum(flt(row.difference_value) for row in self.items)

	def on_submit(self):
		changed = [row for row in self.items if row.difference_qty]
		if not changed:
			return
		reconciliation = frappe.get_doc(
			{
				"doctype": "Stock Reconciliation",
				"company": frappe.db.get_value("Warehouse", self.store, "company"),
				"purpose": "Stock Reconciliation",
				"posting_date": self.posting_date,
				"posting_time": self.posting_time,
				"set_posting_time": 1,
				"custom_count_type": self.count_type,
				"custom_counted_by": self.counted_by,
				# What was counted, plus what the draft issues will still take off when the accountant submits them,
				# so the store ends at what was counted and nothing is taken twice (QA-05).
				"items": [
					{
						"item_code": row.item_code,
						"warehouse": self.store,
						"qty": flt(row.counted_qty)
						+ pending_issues(row.item_code, self.store, self.posting_date, self.posting_time),
					}
					for row in changed
				],
			}
		)
		# Posted in the system's name: branch managers count, they do not reconcile, and ERPNext checks the
		# user's own Stock Reconciliation rights while working out the balance, whatever the flags say.
		# Counted By keeps who counted.
		reconciliation.flags.from_stock_count = True
		with as_administrator():
			reconciliation.insert()
			reconciliation.submit()
		self.db_set("stock_reconciliation", reconciliation.name)

	def on_cancel(self):
		if self.stock_reconciliation and frappe.db.get_value("Stock Reconciliation", self.stock_reconciliation, "docstatus") == 1:
			reconciliation = frappe.get_doc("Stock Reconciliation", self.stock_reconciliation)
			reconciliation.flags.ignore_permissions = True
			reconciliation.flags.from_stock_count = True
			reconciliation.cancel()


def can_date_counts(user=None):
	return DATING_ROLE in frappe.get_roles(user)


def pending_issues(item_code, store, posting_date, posting_time):
	"""Stock units of an item that sales made before the count took from the store, in issues still waiting as drafts
	for the accountant (paper_use.py: the store showed too few sheets)."""
	from frappe.utils import get_datetime

	return flt(
		frappe.db.sql(
			"""select sum(sed.transfer_qty) from `tabStock Entry Detail` sed
			join `tabStock Entry` se on se.name = sed.parent
			where se.docstatus = 0 and ifnull(se.sales_invoice_no, '') != ''
				and sed.item_code = %s and sed.s_warehouse = %s and se.creation <= %s""",
			(item_code, store, get_datetime(f"{posting_date} {posting_time}")),
		)[0][0]
	)


def recorded(item_code, store, posting_date, posting_time):
	"""(quantity, cost of one) the system shows for an item in a store at a date and time."""
	from erpnext.stock.utils import get_stock_balance

	qty, rate = get_stock_balance(item_code, store, posting_date, posting_time, with_valuation_rate=True)[:2]
	return flt(qty), flt(rate)


@frappe.whitelist()
def get_recorded(item_code, store, posting_date, posting_time):
	"""For the screen: an item's recorded quantity and cost, as soon as it is picked."""
	frappe.has_permission("Stock Count", "create", throw=True)
	frappe.has_permission("Warehouse", "read", store, throw=True)
	qty, rate = recorded(item_code, store, posting_date, posting_time)
	return {"recorded_qty": qty, "valuation_rate": rate}


@frappe.whitelist()
def get_store_items(store, posting_date, posting_time):
	"""Get Items in Store: every item the store holds, with its recorded quantity, for a full count."""
	frappe.has_permission("Stock Count", "create", throw=True)
	frappe.has_permission("Warehouse", "read", store, throw=True)
	items = frappe.get_all(
		"Bin",
		filters={"warehouse": store, "actual_qty": ["!=", 0]},
		pluck="item_code",
		order_by="item_code",
	)
	rows = []
	for item_code in items:
		qty, rate = recorded(item_code, store, posting_date, posting_time)
		if qty:
			item = frappe.get_cached_value("Item", item_code, ["item_name", "stock_uom"], as_dict=True)
			rows.append(
				{"item_code": item_code, "item_name": item.item_name, "stock_uom": item.stock_uom, "recorded_qty": qty, "valuation_rate": rate}
			)
	return rows


def block_cancel_of_count_reconciliation(doc, method=None):
	"""Stock Reconciliation before_cancel hook: one made by a stock count is reversed only by cancelling the
	count, otherwise the count would still show a difference that is no longer posted."""
	if doc.flags.from_stock_count:
		return
	count = frappe.db.get_value("Stock Count", {"stock_reconciliation": doc.name, "docstatus": 1})
	if count:
		frappe.throw(_("{0} was posted by Stock Count {1}. Cancel the count instead.").format(doc.name, count))
