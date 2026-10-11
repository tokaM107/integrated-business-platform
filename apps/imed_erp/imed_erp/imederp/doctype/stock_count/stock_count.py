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
from frappe.utils import flt

from imed_erp.imederp.stock_count import branch_of


class StockCount(Document):
	def validate(self):
		if frappe.db.get_value("Warehouse", self.store, "is_group"):
			frappe.throw(_("{0} is a group of stores. Choose the store that was counted.").format(self.store))
		self.branch = branch_of(self.store)
		self.check_own_branch()
		self.check_items()
		self.set_differences()

	def before_submit(self):
		# The stock may have moved since the count was saved.
		self.set_differences()

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
				"items": [
					{"item_code": row.item_code, "warehouse": self.store, "qty": flt(row.counted_qty)} for row in changed
				],
			}
		)
		# Posted in the system's name: branch managers count, they do not reconcile, and ERPNext checks the
		# user's own Stock Reconciliation rights while working out the balance, whatever the flags say.
		# Counted By keeps who counted.
		reconciliation.flags.from_stock_count = True
		user = frappe.session.user
		frappe.set_user("Administrator")
		try:
			reconciliation.insert()
			reconciliation.submit()
		finally:
			frappe.set_user(user)
		self.db_set("stock_reconciliation", reconciliation.name)

	def on_cancel(self):
		if self.stock_reconciliation and frappe.db.get_value("Stock Reconciliation", self.stock_reconciliation, "docstatus") == 1:
			reconciliation = frappe.get_doc("Stock Reconciliation", self.stock_reconciliation)
			reconciliation.flags.ignore_permissions = True
			reconciliation.flags.from_stock_count = True
			reconciliation.cancel()


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
