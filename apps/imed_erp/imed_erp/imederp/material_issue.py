# Branch material requests and their issue from the main warehouse (Mawasah), with paper issued to a
# printing machine.
#
#   1. A branch asks for materials: an ERPNext Material Request of type Material Transfer, from a
#      warehouse that supplies the branches (Warehouse > Supplies Branches) to the branch's warehouse.
#      Saving it moves no stock.
#   2. "Request Approval" -> Pending Approval. A holder of APPROVER_ROLE (Raghad) approves it, which
#      submits it, or rejects it with a reason, which closes it for good. Nobody can submit it otherwise.
#   3. The store issues it: a Stock Entry (Material Transfer) made from the approved request, with the
#      person who received the goods. Stock moves only when that Stock Entry is submitted. A request can
#      be issued in several parts; the total never exceeds what was approved.
#   4. Paper (an item whose group, or a group above it, has Needs Printing Machine) is issued to one
#      printing machine per row. Several machines take several rows, each with its own quantity.
#
# Who did what stays on the documents: the request's owner and its approver / approval time, the Stock
# Entry's Issued By, Received By and posting date, and the machine on each Stock Entry row; Frappe's
# version history keeps every change. Quantities are compared in the item's stock UOM (stock_qty /
# transfer_qty), so whatever conversion factors the items have are used as they are.
#
# A Material Request that does not take stock out of a supplying warehouse (purchase requests, the
# requests ERPNext's reorder job raises) is left to ERPNext as before.

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt, now_datetime

from imed_erp.imederp.doctype.printing_machine.printing_machine import serves_warehouse
from imed_erp.imederp.expense_reminders import notify

APPROVER_ROLE = "Stock Request Approver"
PENDING, APPROVED, REJECTED = "Pending Approval", "Approved", "Rejected"
APPROVAL_FIELDS = ("custom_approval_status", "custom_approved_by", "custom_approved_on", "custom_rejection_reason")

# Created on every migrate (hooks.py: after_migrate), so the code and its fields always go together.
CUSTOM_FIELDS = {
	"Warehouse": [
		{
			"fieldname": "custom_supplies_branches",
			"fieldtype": "Check",
			"label": "Supplies Branches",
			"description": "Branches request materials from this warehouse (Material Request), and Raghad's approval is needed before they are issued.",
			"insert_after": "is_group",
		},
	],
	"Item Group": [
		{
			"fieldname": "custom_requires_printing_machine",
			"fieldtype": "Check",
			"label": "Needs Printing Machine",
			"description": "Items of this group (e.g. paper) are issued to a printing machine. Applies to the groups under it too.",
			"insert_after": "is_group",
		},
	],
	"Material Request": [
		{
			"fieldname": "custom_approval_section",
			"fieldtype": "Section Break",
			"label": "Approval",
			"insert_after": "items",
			"depends_on": "eval:doc.custom_approval_status",
		},
		{
			"fieldname": "custom_approval_status",
			"fieldtype": "Select",
			"label": "Approval Status",
			"options": "\nPending Approval\nApproved\nRejected",
			"insert_after": "custom_approval_section",
			"read_only": 1,
			"no_copy": 1,
			"in_list_view": 1,
			"in_standard_filter": 1,
			"translatable": 1,
		},
		{
			"fieldname": "custom_approved_by",
			"fieldtype": "Link",
			"options": "User",
			"label": "Approved / Rejected By",
			"insert_after": "custom_approval_status",
			"read_only": 1,
			"no_copy": 1,
			"ignore_user_permissions": 1,
		},
		{
			"fieldname": "custom_approval_column",
			"fieldtype": "Column Break",
			"insert_after": "custom_approved_by",
		},
		{
			"fieldname": "custom_approved_on",
			"fieldtype": "Datetime",
			"label": "Approved / Rejected On",
			"insert_after": "custom_approval_column",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "custom_rejection_reason",
			"fieldtype": "Small Text",
			"label": "Rejection Reason",
			"insert_after": "custom_approved_on",
			"read_only": 1,
			"no_copy": 1,
			"depends_on": "eval:doc.custom_approval_status=='Rejected'",
		},
	],
	"Material Request Item": [
		{
			"fieldname": "custom_printing_machine",
			"fieldtype": "Link",
			"options": "Printing Machine",
			"label": "Printing Machine",
			"insert_after": "item_name",
			"in_list_view": 1,
			"columns": 2,
		},
	],
	"Stock Entry": [
		{
			"fieldname": "custom_received_by",
			"fieldtype": "Data",
			"label": "Received By",
			"description": "The person who physically received the materials.",
			"insert_after": "posting_time",
			"depends_on": "eval:(doc.items || []).some(d => d.material_request)",
			"allow_on_submit": 0,
		},
		{
			"fieldname": "custom_issued_by",
			"fieldtype": "Link",
			"options": "User",
			"label": "Issued By",
			"insert_after": "custom_received_by",
			"read_only": 1,
			"no_copy": 1,
			"ignore_user_permissions": 1,
			"depends_on": "eval:doc.custom_issued_by",
		},
	],
	"Stock Entry Detail": [
		{
			# Same fieldname as on the request's row, so ERPNext's mapping copies the machine over.
			"fieldname": "custom_printing_machine",
			"fieldtype": "Link",
			"options": "Printing Machine",
			"label": "Printing Machine",
			"insert_after": "item_name",
			"in_list_view": 1,
			"columns": 2,
		},
	],
}


def make_custom_fields():
	"""after_migrate hook."""
	create_custom_fields(CUSTOM_FIELDS, update=True)


# ---------- What a branch request is ----------


def is_supplying_warehouse(warehouse):
	return bool(warehouse) and bool(frappe.db.get_value("Warehouse", warehouse, "custom_supplies_branches"))


def is_branch_request(mr):
	"""A transfer out of a warehouse that supplies the branches: the requests this module governs."""
	if mr.material_request_type != "Material Transfer":
		return False
	sources = [d.from_warehouse for d in mr.get("items")] + [mr.set_from_warehouse]
	return any(is_supplying_warehouse(w) for w in sources)


def needs_machine(item_code):
	"""Paper and the like: its item group, or a group above it, has Needs Printing Machine."""
	group = frappe.db.get_value("Item", item_code, "item_group")
	if not group:
		return False
	lft, rgt = frappe.db.get_value("Item Group", group, ["lft", "rgt"])
	return bool(
		frappe.db.exists(
			"Item Group", {"lft": ["<=", lft], "rgt": [">=", rgt], "custom_requires_printing_machine": 1}
		)
	)


def validate_machine(machine, warehouse, row_label):
	if frappe.db.get_value("Printing Machine", machine, "disabled"):
		frappe.throw(_("{0}: printing machine {1} is disabled.").format(row_label, machine))
	if not serves_warehouse(machine, warehouse):
		frappe.throw(
			_("{0}: printing machine {1} is not at {2}. Choose a machine of that branch.").format(
				row_label, machine, warehouse
			)
		)


# ---------- Material Request ----------


def material_request_onload(doc, method=None):
	"""The form shows the approval buttons from these."""
	doc.set_onload("is_branch_request", is_branch_request(doc))
	doc.set_onload("is_stock_approver", is_approver())


def validate_material_request(doc, method=None):
	before = doc.get_doc_before_save()
	if before and before.get("custom_approval_status") == REJECTED:
		frappe.throw(_("Material Request {0} was rejected and is closed. Make a new request instead.").format(doc.name))

	if not doc.flags.imed_approval:
		protect_approval_fields(doc, before)

	if not is_branch_request(doc):
		return

	for row in doc.items:
		label = _("Row #{0}").format(row.idx)
		row.from_warehouse = row.from_warehouse or doc.set_from_warehouse
		row.warehouse = row.warehouse or doc.set_warehouse
		# The form fills in the requester's own cost center, used by ERPNext for purchase expenses only.
		# On a transfer it means nothing, and the store serving the branch is not allowed that cost center,
		# so it could neither see the request nor issue it. The issue gets its cost center as any
		# transfer the store makes does.
		row.cost_center = None
		if not is_supplying_warehouse(row.from_warehouse):
			frappe.throw(_("{0}: materials are requested from the main warehouse; {1} does not supply the branches.").format(label, row.from_warehouse or _("empty")))
		if not row.warehouse:
			frappe.throw(_("{0}: choose the warehouse the materials go to.").format(label))
		if row.warehouse == row.from_warehouse or is_supplying_warehouse(row.warehouse):
			frappe.throw(_("{0}: the materials must go to a branch, not to {1}.").format(label, row.warehouse))
		if frappe.db.get_value("Warehouse", row.warehouse, "is_group"):
			frappe.throw(_("{0}: {1} is a group warehouse. Choose the warehouse that will hold the materials.").format(label, row.warehouse))
		if flt(row.qty) <= 0:
			frappe.throw(_("{0}: the quantity must be more than zero.").format(label))
		item = frappe.db.get_value("Item", row.item_code, ["is_stock_item", "disabled"], as_dict=True)
		if not item or not item.is_stock_item or item.disabled:
			frappe.throw(_("{0}: {1} is not an active stock item.").format(label, row.item_code))
		if row.get("custom_printing_machine"):
			validate_machine(row.custom_printing_machine, row.warehouse, label)

	# What was asked for is what gets approved: a change while waiting sends it back to draft.
	if before and doc.custom_approval_status == PENDING and request_rows(before) != request_rows(doc):
		doc.custom_approval_status = None


def request_rows(doc):
	return [
		(d.item_code, flt(d.qty), d.uom, d.from_warehouse, d.warehouse, d.get("custom_printing_machine"))
		for d in doc.items
	]


def protect_approval_fields(doc, before):
	"""Only the approval actions below write these, whatever the form or the API sends."""
	for field in APPROVAL_FIELDS:
		old = before.get(field) if before else None
		if (doc.get(field) or None) != (old or None):
			# Editing a pending request clears its status in validate_material_request; that is allowed.
			if field == "custom_approval_status" and not doc.get(field) and old == PENDING:
				continue
			frappe.throw(_("{0} is set by the approval actions only.").format(_(doc.meta.get_label(field))), frappe.PermissionError)


def before_submit_material_request(doc, method=None):
	if not is_branch_request(doc):
		return
	if not (doc.flags.imed_approval and doc.custom_approval_status == APPROVED):
		frappe.throw(
			_("A branch request is submitted by approving it. Click Request Approval, then Raghad approves it."),
			title=_("Approval Needed"),
		)


@frappe.whitelist()
def request_approval(name):
	doc = frappe.get_doc("Material Request", name)
	doc.check_permission("write")
	if not is_branch_request(doc):
		frappe.throw(_("Material Request {0} is not a branch request from the main warehouse.").format(name))
	if doc.docstatus != 0 or doc.custom_approval_status:
		frappe.throw(_("Approval can only be requested for a draft that has not been sent yet."))
	doc.flags.imed_approval = True
	doc.custom_approval_status = PENDING
	doc.save()
	notify(
		get_approvers(doc),
		_("Material Request {0} from {1} is waiting for your approval.").format(doc.name, destinations(doc)),
		"Material Request",
		doc.name,
	)


@frappe.whitelist()
def approve(name):
	doc = get_pending(name)
	doc.flags.imed_approval = True
	doc.custom_approval_status = APPROVED
	doc.custom_approved_by = frappe.session.user
	doc.custom_approved_on = now_datetime()
	doc.submit()
	notify_requester(doc, _("Material Request {0} was approved and can be issued."))


@frappe.whitelist()
def reject(name, reason=None):
	doc = get_pending(name)
	doc.flags.imed_approval = True
	# db_set: from now on validate refuses every save.
	doc.db_set(
		{
			"custom_approval_status": REJECTED,
			"custom_approved_by": frappe.session.user,
			"custom_approved_on": now_datetime(),
			"custom_rejection_reason": reason,
		}
	)
	doc.add_comment("Comment", _("Rejected: {0}").format(reason or _("no reason given")))
	notify_requester(doc, _("Material Request {0} was rejected.") + (f" {reason}" if reason else ""))


def get_pending(name):
	frappe.only_for(APPROVER_ROLE)
	# Locked, so two clicks cannot both approve it.
	frappe.db.get_value("Material Request", name, "name", for_update=True)
	doc = frappe.get_doc("Material Request", name)
	doc.check_permission("read")
	# The approver decides only for the warehouses her User Permissions give her.
	for row in doc.items:
		if not frappe.has_permission("Warehouse", "read", doc=row.from_warehouse):
			frappe.throw(_("You cannot approve requests from {0}.").format(row.from_warehouse), frappe.PermissionError)
	if doc.docstatus != 0 or doc.custom_approval_status != PENDING:
		frappe.throw(_("Material Request {0} is not waiting for approval.").format(name))
	return doc


def notify_requester(doc, subject):
	notify([doc.owner], subject.format(doc.name), "Material Request", doc.name)


def destinations(doc):
	return ", ".join(sorted({d.warehouse for d in doc.items if d.warehouse}))


def is_approver(user=None):
	return APPROVER_ROLE in frappe.get_roles(user)


def get_approvers(doc):
	"""Enabled holders of the approver role who may see the request's source warehouses."""
	users = frappe.get_all("Has Role", filters={"role": APPROVER_ROLE, "parenttype": "User"}, pluck="parent")
	users = frappe.get_all(
		"User",
		filters={"name": ["in", [u for u in users if u != "Administrator"] or [""]], "enabled": 1, "user_type": "System User"},
		pluck="name",
	)
	sources = {d.from_warehouse for d in doc.items}
	return [u for u in users if all(frappe.has_permission("Warehouse", "read", doc=w, user=u) for w in sources)]


# ---------- Stock Entry: the issue ----------


def request_rows_of(se):
	"""(Stock Entry row, Material Request Item) for the rows issued against a branch request."""
	rows, requests = [], {}
	for row in se.items:
		if not row.material_request or not row.material_request_item:
			continue
		if row.material_request not in requests:
			requests[row.material_request] = frappe.get_doc("Material Request", row.material_request)
		mr = requests[row.material_request]
		if not is_branch_request(mr):
			continue
		mr_item = next((d for d in mr.items if d.name == row.material_request_item), None)
		if not mr_item:
			frappe.throw(_("Row #{0}: the row of Material Request {1} was not found.").format(row.idx, row.material_request))
		rows.append((row, mr, mr_item))
	return rows


def validate_stock_entry(doc, method=None):
	for row, mr, mr_item in request_rows_of(doc):
		label = _("Row #{0}").format(row.idx)
		if mr.docstatus != 1 or mr.custom_approval_status != APPROVED:
			frappe.throw(_("{0}: Material Request {1} is not approved, so nothing can be issued from it.").format(label, mr.name))
		if mr.status in ("Stopped", "Cancelled"):
			frappe.throw(_("{0}: Material Request {1} is {2}.").format(label, mr.name, _(mr.status)))
		if doc.purpose != "Material Transfer":
			frappe.throw(_("A branch request is issued with a Material Transfer."))
		if row.s_warehouse != mr_item.from_warehouse or row.t_warehouse != mr_item.warehouse:
			frappe.throw(
				_("{0}: issue from {1} to {2}, as approved.").format(label, mr_item.from_warehouse, mr_item.warehouse)
			)
		if flt(row.qty) <= 0:
			frappe.throw(_("{0}: the quantity issued must be more than zero.").format(label))

		approved_machine = mr_item.get("custom_printing_machine")
		if approved_machine and row.custom_printing_machine and row.custom_printing_machine != approved_machine:
			frappe.throw(_("{0}: the request was approved for printing machine {1}.").format(label, approved_machine))
		row.custom_printing_machine = row.custom_printing_machine or approved_machine

	# A machine is checked wherever it is set, request or not.
	for row in doc.items:
		if row.get("custom_printing_machine"):
			validate_machine(row.custom_printing_machine, row.t_warehouse, _("Row #{0}").format(row.idx))


def before_submit_stock_entry(doc, method=None):
	rows = request_rows_of(doc)
	if not rows:
		return
	if not (doc.custom_received_by or "").strip():
		frappe.throw(_("Enter who received the materials (Received By)."), title=_("Missing Recipient"))
	for row, mr, mr_item in rows:
		if needs_machine(row.item_code) and not row.custom_printing_machine:
			frappe.throw(
				_("Row #{0}: {1} is issued to a printing machine. Choose the machine.").format(row.idx, row.item_code),
				title=_("Missing Printing Machine"),
			)
	check_not_over_issued(doc, rows)
	doc.custom_issued_by = frappe.session.user


def check_not_over_issued(doc, rows):
	"""The total issued for each request row stays within what was approved, also when two issues are
	submitted at the same time: the request is locked until this transaction ends."""
	for name in sorted({mr.name for _row, mr, _item in rows}):
		frappe.db.get_value("Material Request", name, "name", for_update=True)

	this_issue = {}
	for row, _mr, mr_item in rows:
		this_issue[mr_item.name] = this_issue.get(mr_item.name, 0) + flt(row.transfer_qty)

	for row, mr, mr_item in rows:
		if mr_item.name not in this_issue:
			continue
		issued_before = flt(
			frappe.db.sql(
				"""select sum(transfer_qty) from `tabStock Entry Detail`
				where material_request_item = %s and docstatus = 1 and parent != %s""",
				(mr_item.name, doc.name),
			)[0][0]
		)
		total = issued_before + this_issue.pop(mr_item.name)
		approved = flt(frappe.db.get_value("Material Request Item", mr_item.name, "stock_qty"))
		if flt(total, 6) > flt(approved, 6):
			frappe.throw(
				_("Row #{0}: {1} would be issued {2} {3} in total, but {4} were approved in Material Request {5} ({6} already issued).").format(
					row.idx, row.item_code, total, row.stock_uom, approved, mr.name, issued_before
				),
				title=_("More Than Approved"),
			)
