# Damaged stock and its sale by weight (LIB-09, PRN-07, DOC-19).
#
# Requirements v1.2:
#   LIB-09  damaged stock is recorded with its quantity and reason and taken off the balance; its sale by
#           weight is recorded as revenue; damaged stored editions included (DOC-19).
#   PRN-07  the same for damaged paper.
#   DOC-19  copies damaged in storage are a loss on the library, never charged to the doctor.
#   Open question (customer returns): there are none; only damaged stock is sold, by weight.
#
# Decided with the owner's representative (12 Oct 2026):
#   - Damage is a loss at once: the damaged quantity leaves its store at its cost, which is posted to
#     الهالك والتالف on the branch's cost center (the library's loss, DOC-19; never a Doctor Ledger Entry).
#     The same quantity goes into the damaged store (Warehouse > Damaged Store: التالف — المواساة) at zero
#     value, so the store keeps count of what is waiting to be sold without carrying a cost twice.
#   - The branch manager records and submits it; the owner and the accountant cancel.
#   - Azarita's damaged stock goes to the damaged store at Mawasah too; its loss stays on Azarita's library.
#
# The sale by weight (Damaged Stock Sale) takes the damaged items out of the damaged store (zero value, so
# no cost of sale) and invoices the weight in kilograms at the price per kilogram: a Sales Invoice of the
# non-stock item SCRAP_ITEM, whose revenue is إيراد بيع التالف بالوزن, and the cash into the branch's cash
# box. Sheets and copies are never converted to kilograms: what left is counted in its own unit, and the
# weight is what the scale showed.
#
# The documents these make (two Stock Entries for a damage; a Stock Entry, a Sales Invoice and a Payment
# Entry for a sale) are cancelled only by cancelling the damage or the sale (block_cancel_of_posted_entry).

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from imed_erp.imederp.system_user import as_administrator

# Account names of the chart of accounts (setup_coa.py), without the company abbreviation.
LOSS_ACCOUNT = "الهالك والتالف"
SCRAP_REVENUE_ACCOUNT = "إيراد بيع التالف بالوزن"

# The non-stock item a sale by weight is invoiced with, and the weight unit (ERPNext's own).
SCRAP_ITEM = "DAMAGED-BY-WEIGHT"
WEIGHT_UOM = "Kg"
# The buyer used when the sale is not to a known customer (setup_library.py makes it).
SCRAP_BUYER = "مشتري التالف"

CUSTOM_FIELDS = {
	"Warehouse": [
		{
			"fieldname": "custom_is_damaged_store",
			"fieldtype": "Check",
			"label": "Damaged Store",
			"description": "Damaged stock is moved here at zero value until it is sold by weight (Damaged Stock Entry, Damaged Stock Sale).",
			"insert_after": "custom_supplies_branches",
		},
	],
}


def make_custom_fields():
	"""after_install / after_migrate hook."""
	create_custom_fields(CUSTOM_FIELDS, update=True)


def acc(name, company):
	return f"{name} - {frappe.get_cached_value('Company', company, 'abbr')}"


def is_damaged_store(warehouse):
	return bool(warehouse) and bool(frappe.db.get_value("Warehouse", warehouse, "custom_is_damaged_store"))


@frappe.whitelist()
def default_damaged_store(company=None):
	"""The company's damaged store, when it has exactly one."""
	filters = {"custom_is_damaged_store": 1, "is_group": 0, "disabled": 0}
	if company:
		filters["company"] = company
	stores = frappe.get_all("Warehouse", filters=filters, pluck="name")
	return stores[0] if len(stores) == 1 else None


def check_own_branch(branch, what):
	"""A branch manager works only for their own branch (their cost centers in User Permission)."""
	allowed = frappe.get_all("User Permission", filters={"user": frappe.session.user, "allow": "Cost Center"}, pluck="for_value")
	if allowed and branch not in allowed:
		frappe.throw(
			_("{0} is not your branch's. You can work for: {1}.").format(what, ", ".join(sorted(allowed))),
			title=_("Not Your Branch"),
		)


def as_system(fn, *args):
	"""Post a document in the system's name: branch managers record damage and sales, they do not write
	stock entries or invoices on stores and accounts outside their own. The app's document keeps who did it."""
	# SEC-02: set_user alone would replace the person's web session and log them out (system_user.py).
	with as_administrator():
		return fn(*args)


def submit_new(doc):
	doc.flags.from_damaged_stock = True
	as_system(lambda: (doc.insert(), doc.submit()))
	return doc.name


def cancel_posted(doctype, name):
	if not name or frappe.db.get_value(doctype, name, "docstatus") != 1:
		return
	doc = frappe.get_doc(doctype, name)
	doc.flags.from_damaged_stock = True
	doc.flags.ignore_permissions = True
	as_system(doc.cancel)


# Holders may move stock in or out of the damaged store by hand, to correct a mistake.
CORRECTION_ROLE = "Accounts Manager"


def guard_damaged_store(doc, method=None):
	"""validate hook on the stock documents: the damaged store is filled only by a damage record (with its
	reason and its loss) and emptied only by a sale by weight. A plain transfer would bring stock in at its
	cost with no reason and no loss; a plain issue or invoice would take it out without a sale by weight.
	Stock counts (Stock Reconciliation) are not touched."""
	if doc.flags.from_damaged_stock or CORRECTION_ROLE in frappe.get_roles():
		return
	if doc.doctype in ("Sales Invoice", "POS Invoice") and not doc.get("update_stock"):
		return
	for row in doc.get("items") or []:
		for field in ("s_warehouse", "t_warehouse", "warehouse", "target_warehouse"):
			if is_damaged_store(row.get(field)):
				frappe.throw(
					_("Row #{0}: {1} is the damaged store. Damaged items go in through Damaged Stock Entry and out through Damaged Stock Sale.").format(
						row.idx, row.get(field)
					),
					title=_("Damaged Store"),
				)


# Which field of the damage or sale names each document it posts.
POSTED_BY = {
	"Stock Entry": [
		("Damaged Stock Entry", "loss_entry"),
		("Damaged Stock Entry", "damaged_store_entry"),
		("Damaged Stock Sale", "stock_entry"),
	],
	"Sales Invoice": [("Damaged Stock Sale", "sales_invoice")],
	"Payment Entry": [("Damaged Stock Sale", "payment_entry")],
}


def block_cancel_of_posted_entry(doc, method=None):
	"""before_cancel hook: what a damage or a sale posted is reversed only by cancelling that damage or sale,
	otherwise the record would still show stock moved or money received that no longer is."""
	if doc.flags.from_damaged_stock:
		return
	for source, field in POSTED_BY.get(doc.doctype, []):
		name = frappe.db.get_value(source, {field: doc.name, "docstatus": 1})
		if name:
			frappe.throw(_("{0} was posted by {1} {2}. Cancel the {1} instead.").format(doc.name, _(source), name))
