# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Sale of damaged stock by weight (LIB-09, PRN-07): the weight the scale showed, the price per kilogram,
# the buyer, and which damaged items left the damaged store with it (each in its own stock unit: sheets
# are never converted to kilograms). On submit, in the system's name (imederp/damaged_stock.py):
#   1. a Material Issue takes those items out of the damaged store. They are there at zero value
#      (Damaged Stock Entry posted their cost as a loss), so it posts no cost of sale;
#   2. a Sales Invoice of the weight, SCRAP_ITEM at the price per kilogram: revenue to
#      إيراد بيع التالف بالوزن on the damaged store's branch;
#   3. if paid in cash, a Payment Entry into that branch's cash box (imederp/treasuries.py).
# A row may name the damage record it came from, which then shows how much of it was sold (DOC-19).
# Cancelling reverses all three.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from imed_erp.imederp.damaged_stock import (
	LOSS_ACCOUNT,
	SCRAP_ITEM,
	SCRAP_REVENUE_ACCOUNT,
	WEIGHT_UOM,
	acc,
	as_system,
	cancel_posted,
	check_own_branch,
	is_damaged_store,
	submit_new,
)
from imed_erp.imederp.doctype.stock_count.stock_count import recorded
from imed_erp.imederp.stock_count import branch_of
from imed_erp.imederp.treasuries import BUSINESS_TREASURY, plain


class DamagedStockSale(Document):
	def validate(self):
		if not is_damaged_store(self.damaged_store):
			frappe.throw(_("{0} is not a damaged store (Warehouse > Damaged Store).").format(self.damaged_store))
		self.company = frappe.db.get_value("Warehouse", self.damaged_store, "company")
		self.branch = branch_of(self.damaged_store)
		if not self.branch:
			frappe.throw(_("{0} is not a store of a library branch.").format(self.damaged_store))
		check_own_branch(self.branch, self.damaged_store)

		self.weight_uom = WEIGHT_UOM
		if flt(self.weight) <= 0:
			frappe.throw(_("Enter the weight sold, more than zero."), title=_("Missing Weight"))
		if flt(self.rate) <= 0:
			frappe.throw(_("Enter the price per kilogram, more than zero."), title=_("Missing Price"))
		# The price and the weight as the invoice keeps them (the currency's precision, piastres; the invoice's
		# quantity precision, System Settings > Float Precision), so the two totals agree: a weight of 2.345 Kg on a
		# site that keeps 2 decimals is invoiced as 2.34, and the sale says so too.
		self.rate = flt(self.rate, self.precision("rate"))
		self.weight = flt(self.weight, frappe.get_precision("Sales Invoice Item", "qty"))
		self.amount = flt(flt(self.weight) * self.rate, self.precision("amount"))
		self.set_cash_account()
		self.check_items()

	def set_cash_account(self):
		self.cash_account = None
		if not self.paid_in_cash:
			return
		abbr = frappe.get_cached_value("Company", self.company, "abbr")
		box = BUSINESS_TREASURY.get(plain(self.branch, abbr))
		if not box or not frappe.db.exists("Account", f"{box} - {abbr}"):
			frappe.throw(_("{0} has no cash box. Untick Paid in Cash and record the payment separately.").format(self.branch))
		self.cash_account = f"{box} - {abbr}"

	def check_items(self):
		taken = {}
		seen = set()
		for row in self.items:
			key = (row.item_code, row.damage_entry)
			if key in seen:
				frappe.throw(_("Row #{0}: {1} is listed twice.").format(row.idx, row.item_code))
			seen.add(key)
			if flt(row.qty) <= 0:
				frappe.throw(_("Row #{0}: the quantity taken out must be more than zero.").format(row.idx))
			item = frappe.db.get_value("Item", row.item_code, ["is_stock_item", "stock_uom"], as_dict=True)
			if not item or not item.is_stock_item:
				frappe.throw(_("Row #{0}: {1} is not a stock item.").format(row.idx, row.item_code))
			row.stock_uom = item.stock_uom
			row.available_qty = recorded(row.item_code, self.damaged_store, self.posting_date, frappe.utils.nowtime())[0]
			taken[row.item_code] = taken.get(row.item_code, 0) + flt(row.qty)
			if taken[row.item_code] > row.available_qty:
				frappe.throw(
					_("Row #{0}: the damaged store holds only {1} {2} of {3}.").format(row.idx, row.available_qty, row.stock_uom, row.item_code),
					title=_("Not Enough Damaged Stock"),
				)
			if row.damage_entry:
				self.check_damage_entry(row)

	def check_damage_entry(self, row):
		entry = frappe.db.get_value("Damaged Stock Entry", row.damage_entry, ["docstatus", "damaged_store"], as_dict=True)
		if not entry or entry.docstatus != 1:
			frappe.throw(_("Row #{0}: damage record {1} is not submitted.").format(row.idx, row.damage_entry))
		if entry.damaged_store != self.damaged_store:
			frappe.throw(_("Row #{0}: damage record {1} went to {2}.").format(row.idx, row.damage_entry, entry.damaged_store))
		damaged = frappe.db.get_value(
			"Damaged Stock Item", {"parent": row.damage_entry, "item_code": row.item_code}, ["qty", "sold_qty"], as_dict=True
		)
		if not damaged:
			frappe.throw(_("Row #{0}: damage record {1} has no {2}.").format(row.idx, row.damage_entry, row.item_code))
		left = flt(damaged.qty) - flt(damaged.sold_qty)
		if flt(row.qty) > left:
			frappe.throw(
				_("Row #{0}: only {1} {2} of {3} from damage record {4} are left to sell.").format(
					row.idx, left, row.stock_uom, row.item_code, row.damage_entry
				)
			)

	def before_submit(self):
		# Two sales of the same damage record submitted at once: the second waits here until the first is
		# done, then sees what is left. The damaged store may also have changed since the sale was saved.
		for entry in sorted({row.damage_entry for row in self.items if row.damage_entry}):
			frappe.db.get_value("Damaged Stock Entry", entry, "name", for_update=True)
		self.check_items()

	def on_submit(self):
		stock_out = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"company": self.company,
				"stock_entry_type": "Material Issue",
				"purpose": "Material Issue",
				"posting_date": self.posting_date,
				"set_posting_time": 1,
				"remarks": _("Damaged stock sold by weight: {0}").format(self.name),
				"items": [
					{
						"item_code": row.item_code,
						"qty": flt(row.qty),
						"uom": row.stock_uom,
						"conversion_factor": 1,
						"s_warehouse": self.damaged_store,
						"expense_account": acc(LOSS_ACCOUNT, self.company),
						"cost_center": self.branch,
						"allow_zero_valuation_rate": 1,
					}
					for row in self.items
				],
			}
		)
		self.db_set("stock_entry", submit_new(stock_out))

		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": self.company,
				"customer": self.customer,
				"posting_date": self.posting_date,
				"set_posting_time": 1,
				"due_date": self.posting_date,
				"cost_center": self.branch,
				"update_stock": 0,
				"remarks": _("Damaged stock sold by weight: {0}").format(self.name),
				"items": [
					{
						"item_code": SCRAP_ITEM,
						"qty": flt(self.weight),
						"uom": WEIGHT_UOM,
						"conversion_factor": 1,
						"rate": flt(self.rate),
						"income_account": acc(SCRAP_REVENUE_ACCOUNT, self.company),
						"cost_center": self.branch,
					}
				],
			}
		)
		self.db_set("sales_invoice", submit_new(invoice))
		invoice.reload()
		if flt(invoice.grand_total, 2) != flt(self.amount, 2):
			frappe.throw(_("The invoice total {0} differs from the sale's {1}.").format(invoice.grand_total, self.amount))

		if self.paid_in_cash:
			from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

			payment = as_system(get_payment_entry, "Sales Invoice", invoice.name)
			payment.posting_date = self.posting_date
			payment.mode_of_payment = "Cash" if frappe.db.exists("Mode of Payment", "Cash") else None
			payment.paid_to = self.cash_account
			payment.paid_to_account_currency = frappe.db.get_value("Account", self.cash_account, "account_currency")
			payment.cost_center = self.branch
			payment.remarks = _("Damaged stock sold by weight: {0}").format(self.name)
			self.db_set("payment_entry", submit_new(payment))

		update_sold_qty(self)

	def on_cancel(self):
		cancel_posted("Payment Entry", self.payment_entry)
		cancel_posted("Sales Invoice", self.sales_invoice)
		cancel_posted("Stock Entry", self.stock_entry)
		update_sold_qty(self)


def update_sold_qty(sale):
	"""On each damage record a sale names: how much of each item has been sold by weight."""
	for entry, item_code in {(row.damage_entry, row.item_code) for row in sale.items if row.damage_entry}:
		sold = frappe.db.sql(
			"""select coalesce(sum(i.qty), 0) from `tabDamaged Stock Sale Item` i
			join `tabDamaged Stock Sale` s on s.name = i.parent
			where s.docstatus = 1 and i.damage_entry = %s and i.item_code = %s""",
			(entry, item_code),
		)[0][0]
		frappe.db.set_value("Damaged Stock Item", {"parent": entry, "item_code": item_code}, "sold_qty", flt(sold))


@frappe.whitelist()
def get_damaged_qty(item_code, store):
	"""For the screen: how much of an item the damaged store holds now."""
	frappe.has_permission("Damaged Stock Sale", "create", throw=True)
	frappe.has_permission("Warehouse", "read", store, throw=True)
	return recorded(item_code, store, frappe.utils.nowdate(), frappe.utils.nowtime())[0]
