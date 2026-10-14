# Which edition each copy sold comes from (DOC-14, DOC-15, DOC-16, DOC-17).
#
# A Book Edition names the Item it is sold as (book_edition.item_code). A sales invoice row of that item names the
# edition in book_edition, a field on Sales Invoice Item, so the sale points at one edition and never at another
# one with a similar name. The invoice is ERPNext's own record of the sale: the edition's Sold Qty is worked out
# from the submitted invoices that name it (book_edition.get_sold_qty), again on every submit and cancel, so a
# sale is never counted twice and a cancelled one stops counting.
#
# hooks.py runs on Sales Invoice:
#   validate    set_editions       each row of an edition's item names one of its editions that is on sale;
#                                  on submit, no edition sells more copies than it has left
#   on_submit   update_sold        the editions sold recount their Sold Qty and Remaining Qty
#   on_cancel   update_sold
#
# When the item has one edition on sale, the row takes it by itself (the point of sale cannot show the field).
# When it has several (a new edition while copies of the last one are carried forward), the row must name one:
# which copies go first is not decided (docs/known-issues.md), so none is picked for the seller.
# Nothing here posts to the ledger or moves stock: the invoice's own entries are ERPNext's.

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt

from imed_erp.imederp.doctype.book_edition.book_edition import SELLABLE, get_sold_qty, update_sold_qty

FIELD = "book_edition"

CUSTOM_FIELDS = {
	"Sales Invoice Item": [
		{
			"fieldname": FIELD,
			"fieldtype": "Link",
			"label": "Book Edition",
			"options": "Book Edition",
			"insert_after": "item_name",
			"search_index": 1,
			"print_hide": 1,
			"description": "The edition the copies sold come from. Filled in when the item has one edition on sale.",
		},
	],
}


def make_custom_fields():
	"""after_install / after_migrate hook."""
	create_custom_fields(CUSTOM_FIELDS, update=True)


def editions_on_sale(item_code):
	return frappe.get_all(
		"Book Edition",
		filters={"item_code": item_code, "docstatus": 1, "status": ["in", SELLABLE]},
		pluck="name",
		order_by="edition_date, creation",
	)


def set_editions(doc, method=None):
	"""Sales Invoice validate hook."""
	if not frappe.get_meta(doc.doctype + " Item").has_field(FIELD):
		return
	for row in doc.items:
		if not row.item_code:
			continue
		if row.get(FIELD):
			check_edition(doc, row)
			continue
		if doc.is_return:
			# A credit note names the editions of the invoice it returns (copied with its rows).
			continue
		on_sale = editions_on_sale(row.item_code)
		if len(on_sale) == 1:
			row.set(FIELD, on_sale[0])
		elif len(on_sale) > 1:
			frappe.throw(
				_("Row #{0}: {1} has more than one edition on sale ({2}). Choose the edition the copies come from.").format(
					row.idx, row.item_code, ", ".join(on_sale)
				),
				title=_("Choose the Edition"),
			)
		elif frappe.db.exists("Book Edition", {"item_code": row.item_code, "docstatus": 1}):
			# The item's editions are all cancelled: selling it without naming one would sell their copies anyway,
			# past the cancellation, and count them nowhere.
			frappe.throw(
				_("Row #{0}: {1} has no edition on sale; its editions were cancelled because the curriculum changed.").format(
					row.idx, row.item_code
				),
				title=_("Edition Cancelled"),
			)
	if doc.docstatus == 1 and not doc.is_return:
		check_copies_left(doc)


def check_edition(doc, row):
	edition = frappe.db.get_value(
		"Book Edition", row.get(FIELD), ["item_code", "docstatus", "status"], as_dict=True
	)
	if not edition:
		frappe.throw(_("Row #{0}: Book Edition {1} not found.").format(row.idx, row.get(FIELD)))
	if edition.item_code != row.item_code:
		frappe.throw(
			_("Row #{0}: edition {1} is sold as {2}, not {3}.").format(
				row.idx, row.get(FIELD), edition.item_code or _("no item"), row.item_code
			),
			title=_("Wrong Edition"),
		)
	if doc.is_return:
		return
	if edition.docstatus != 1:
		frappe.throw(_("Row #{0}: edition {1} is not approved (submitted) yet.").format(row.idx, row.get(FIELD)))
	if edition.status not in SELLABLE:
		frappe.throw(
			_("Row #{0}: edition {1} was cancelled because the curriculum changed; its copies are no longer sold.").format(
				row.idx, row.get(FIELD)
			),
			title=_("Edition Cancelled"),
		)


def check_copies_left(doc):
	"""On submit: an edition never sells more copies than it has. Its row is locked first, so two invoices
	submitted at the same moment are counted one after the other."""
	wanted = {}
	for row in doc.items:
		if row.get(FIELD):
			wanted[row.get(FIELD)] = wanted.get(row.get(FIELD), 0) + flt(row.stock_qty or row.qty)
	for edition, qty in sorted(wanted.items()):
		try:
			total, status = frappe.db.get_value("Book Edition", edition, ["total_qty", "status"], for_update=True)
			total = cint(total)
			# A locking read: the edition's lock was waited for, so another invoice's sale may have been committed
			# since this transaction began; a plain read would not see it.
			left = total - get_sold_qty(edition, exclude_invoice=doc.name, for_update=True)
		except frappe.QueryDeadlockError:
			# MariaDB refuses a locking read of a row another sale changed after this transaction began (snapshot
			# isolation): nothing is saved, and submitting again counts that sale.
			frappe.throw(
				_("Another sale of edition {0} was saved at the same moment. Submit this invoice again.").format(edition),
				title=_("Submit Again"),
			)
		if status not in SELLABLE:
			# Read again under the lock: the edition may have been cancelled while this invoice was being submitted.
			frappe.throw(
				_("Edition {0} was cancelled because the curriculum changed; its copies are no longer sold.").format(edition),
				title=_("Edition Cancelled"),
			)
		if qty > left:
			frappe.throw(
				_("Edition {0} has {1} copies left; this invoice sells {2}.").format(
					edition, frappe.format_value(left, {"fieldtype": "Float"}), frappe.format_value(qty, {"fieldtype": "Float"})
				),
				title=_("Not Enough Copies"),
			)


def update_sold(doc, method=None):
	"""Sales Invoice on_submit and on_cancel hook."""
	for edition in {row.get(FIELD) for row in doc.items if row.get(FIELD)}:
		update_sold_qty(edition)
