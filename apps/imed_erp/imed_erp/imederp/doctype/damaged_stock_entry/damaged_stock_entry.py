# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Damaged stock (LIB-09, PRN-07, DOC-19): items damaged in a store, with the reason and who is responsible.
# On submit, in the system's name (imederp/damaged_stock.py):
#   1. a Material Issue takes them out of their store at their cost (moving average), posted to
#      الهالك والتالف on the store's branch: the library's loss, never the doctor's (DOC-19);
#   2. a Material Receipt puts the same quantity into the damaged store at zero value, where it waits to
#      be sold by weight (Damaged Stock Sale).
# Cancelling reverses both, as long as none of it has been sold.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from imed_erp.imederp.damaged_stock import (
	LOSS_ACCOUNT,
	acc,
	cancel_posted,
	check_own_branch,
	is_damaged_store,
	submit_new,
)
from imed_erp.imederp.doctype.stock_count.stock_count import recorded
from imed_erp.imederp.stock_count import branch_of


class DamagedStockEntry(Document):
	def validate(self):
		self.company = frappe.db.get_value("Warehouse", self.source_store, "company")
		if frappe.db.get_value("Warehouse", self.source_store, "is_group"):
			frappe.throw(_("{0} is a group of stores. Choose the store the items were damaged in.").format(self.source_store))
		if is_damaged_store(self.source_store):
			frappe.throw(_("{0} is the damaged store; choose the store the items were damaged in.").format(self.source_store))
		if not is_damaged_store(self.damaged_store):
			frappe.throw(_("{0} is not a damaged store (Warehouse > Damaged Store).").format(self.damaged_store))
		if frappe.db.get_value("Warehouse", self.damaged_store, "company") != self.company:
			frappe.throw(_("{0} and {1} belong to different companies.").format(self.source_store, self.damaged_store))
		self.branch = branch_of(self.source_store)
		if not self.branch:
			frappe.throw(_("{0} is not a store of a library branch.").format(self.source_store))
		check_own_branch(self.branch, self.source_store)
		if not (self.reason or "").strip():
			frappe.throw(_("Enter the reason for the damage."), title=_("Missing Reason"))
		self.check_items()
		self.check_obsolete_edition()
		self.set_values()

	def check_obsolete_edition(self):
		"""An obsolete edition's disposal (book_edition.dispose_as_scrap): only its own copies, from its own library,
		no more than it has left; the edition must be one whose curriculum changed."""
		if not self.book_edition:
			return
		from imed_erp.imederp.doctype.book_edition.book_edition import CANCELLED, get_disposed_qty, get_sold_qty

		edition = frappe.db.get_value(
			"Book Edition",
			self.book_edition,
			["docstatus", "status", "item_code", "cost_center", "total_qty"],
			as_dict=True,
			for_update=True,
		)
		if not edition or edition.docstatus != 1 or edition.status != CANCELLED:
			frappe.throw(_("Edition {0} is not obsolete (Cancel: Curriculum Changed).").format(self.book_edition))
		if edition.cost_center != self.branch:
			frappe.throw(_("Edition {0} is {1}'s; dispose of it from that library's store.").format(self.book_edition, edition.cost_center))
		if [row.item_code for row in self.items] != [edition.item_code]:
			frappe.throw(_("A disposal of edition {0} lists its item {1} only.").format(self.book_edition, edition.item_code))
		left = cint(edition.total_qty) - cint(get_sold_qty(self.book_edition)) - cint(get_disposed_qty(self.book_edition, exclude=self.name))
		if flt(self.items[0].qty) > left:
			frappe.throw(_("Edition {0} has {1} copies left to dispose of.").format(self.book_edition, left), title=_("Too Many Copies"))

	def check_items(self):
		seen = set()
		for row in self.items:
			if row.item_code in seen:
				frappe.throw(_("Row #{0}: {1} is listed twice.").format(row.idx, row.item_code))
			seen.add(row.item_code)
			if flt(row.qty) <= 0:
				frappe.throw(_("Row #{0}: the damaged quantity must be more than zero.").format(row.idx))
			item = frappe.db.get_value("Item", row.item_code, ["is_stock_item", "disabled", "stock_uom"], as_dict=True)
			if not item or not item.is_stock_item or item.disabled:
				frappe.throw(_("Row #{0}: {1} is not an active stock item.").format(row.idx, row.item_code))
			row.stock_uom = item.stock_uom

	def set_values(self):
		"""Cost and loss at the store's moving average; the Loss Entry's own values replace them on submit."""
		for row in self.items:
			qty, rate = recorded(row.item_code, self.source_store, self.posting_date, self.posting_time)
			if flt(row.qty) > qty:
				frappe.throw(
					_("Row #{0}: {1} has only {2} {3} in {4}.").format(row.idx, row.item_code, qty, row.stock_uom, self.source_store),
					title=_("Not Enough Stock"),
				)
			row.valuation_rate = rate
			row.loss_value = flt(flt(row.qty) * rate, row.precision("loss_value"))
		self.total_loss = sum(flt(row.loss_value) for row in self.items)

	def on_submit(self):
		common = {
			"doctype": "Stock Entry",
			"company": self.company,
			"posting_date": self.posting_date,
			"posting_time": self.posting_time,
			"set_posting_time": 1,
			"remarks": _("Damaged stock {0}: {1}").format(self.name, self.reason),
		}
		loss = frappe.get_doc(
			{
				**common,
				"stock_entry_type": "Material Issue",
				"purpose": "Material Issue",
				"items": [
					{
						"item_code": row.item_code,
						"qty": flt(row.qty),
						"uom": row.stock_uom,
						"conversion_factor": 1,
						"s_warehouse": self.source_store,
						"expense_account": acc(LOSS_ACCOUNT, self.company),
						"cost_center": self.branch,
					}
					for row in self.items
				],
			}
		)
		self.db_set("loss_entry", submit_new(loss))

		# The actual cost ERPNext took them out at.
		values = {
			d.item_code: (d.valuation_rate, d.amount)
			for d in frappe.get_all("Stock Entry Detail", filters={"parent": loss.name}, fields=["item_code", "valuation_rate", "amount"])
		}
		for row in self.items:
			row.db_set({"valuation_rate": values[row.item_code][0], "loss_value": values[row.item_code][1]})
		self.db_set("total_loss", sum(flt(v[1]) for v in values.values()))

		damaged = frappe.get_doc(
			{
				**common,
				"stock_entry_type": "Material Receipt",
				"purpose": "Material Receipt",
				"items": [
					{
						"item_code": row.item_code,
						"qty": flt(row.qty),
						"uom": row.stock_uom,
						"conversion_factor": 1,
						"t_warehouse": self.damaged_store,
						"basic_rate": 0,
						"allow_zero_valuation_rate": 1,
						"cost_center": self.branch,
					}
					for row in self.items
				],
			}
		)
		self.db_set("damaged_store_entry", submit_new(damaged))
		self.update_edition()

	def update_edition(self):
		if self.book_edition:
			from imed_erp.imederp.doctype.book_edition.book_edition import update_sold_qty

			update_sold_qty(self.book_edition)

	def before_cancel(self):
		sold = [row for row in self.items if flt(row.sold_qty)]
		if sold:
			frappe.throw(
				_("Part of this damaged stock was already sold by weight ({0}). Cancel the sale first.").format(
					", ".join(f"{row.item_code}: {row.sold_qty}" for row in sold)
				)
			)

	def on_cancel(self):
		# The damaged store first: if its stock was sold without this record, ERPNext refuses and nothing changes.
		cancel_posted("Stock Entry", self.damaged_store_entry)
		cancel_posted("Stock Entry", self.loss_entry)
		self.update_edition()


@frappe.whitelist()
def get_stock(item_code, store, posting_date, posting_time):
	"""For the screen: what the store holds of an item and its cost, as soon as the item is picked."""
	frappe.has_permission("Damaged Stock Entry", "create", throw=True)
	frappe.has_permission("Warehouse", "read", store, throw=True)
	qty, rate = recorded(item_code, store, posting_date, posting_time)
	return {"qty": qty, "valuation_rate": rate}
