# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Branch requests from the main warehouse, row by row, with what was issued against each row: one line
# per issue (Stock Entry row), or one line while nothing is issued yet. Shows who asked, who approved,
# who issued, who received, when, and the printing machine the paper went to
# (imederp/material_issue.py). Each user sees only the requests whose warehouses their User
# Permissions allow.

import frappe
from frappe import _
from frappe.utils import flt

from imed_erp.imederp.material_issue import APPROVED, is_supplying_warehouse


def execute(filters=None):
	return get_columns(), get_data(frappe._dict(filters or {}))


def get_columns():
	return [
		{"label": _("Material Request"), "fieldname": "material_request", "fieldtype": "Link", "options": "Material Request", "width": 160},
		{"label": _("Request Date"), "fieldname": "transaction_date", "fieldtype": "Date", "width": 100},
		{"label": _("Requested By"), "fieldname": "requested_by", "fieldtype": "Link", "options": "User", "width": 150},
		{"label": _("Approval Status"), "fieldname": "approval_status", "fieldtype": "Data", "width": 120},
		{"label": _("Approved / Rejected By"), "fieldname": "approved_by", "fieldtype": "Link", "options": "User", "width": 150},
		{"label": _("Approved / Rejected On"), "fieldname": "approved_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Request Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		# Data, not Link: Frappe drops report rows whose Link values fall outside the user's User Permissions,
		# and a branch is not allowed the main warehouse it asks.
		{"label": _("From Warehouse"), "fieldname": "from_warehouse", "fieldtype": "Data", "width": 170},
		{"label": _("To Warehouse"), "fieldname": "to_warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 170},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 150},
		{"label": _("Requested Qty"), "fieldname": "requested_qty", "fieldtype": "Float", "width": 100},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Approved (Stock UOM)"), "fieldname": "approved_stock_qty", "fieldtype": "Float", "width": 120},
		{"label": _("Issued in Total (Stock UOM)"), "fieldname": "issued_total", "fieldtype": "Float", "width": 130},
		{"label": _("Still to Issue (Stock UOM)"), "fieldname": "remaining", "fieldtype": "Float", "width": 130},
		{"label": _("Stock Entry"), "fieldname": "stock_entry", "fieldtype": "Link", "options": "Stock Entry", "width": 160},
		{"label": _("Issue Date"), "fieldname": "issue_date", "fieldtype": "Date", "width": 100},
		{"label": _("Issue Time"), "fieldname": "issue_time", "fieldtype": "Time", "width": 80},
		{"label": _("Issued Qty"), "fieldname": "issued_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Issued UOM"), "fieldname": "issued_uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Issued (Stock UOM)"), "fieldname": "issued_stock_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Stock UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Printing Machine"), "fieldname": "printing_machine", "fieldtype": "Link", "options": "Printing Machine", "width": 140},
		{"label": _("Received By"), "fieldname": "received_by", "fieldtype": "Data", "width": 140},
		{"label": _("Issued By"), "fieldname": "issued_by", "fieldtype": "Link", "options": "User", "width": 150},
	]


def get_data(filters):
	allowed = set(frappe.get_list("Warehouse", pluck="name"))
	if filters.warehouse and filters.warehouse not in allowed:
		frappe.throw(_("Not permitted to view warehouse {0}").format(filters.warehouse), frappe.PermissionError)

	mr = frappe.qb.DocType("Material Request")
	mri = frappe.qb.DocType("Material Request Item")
	query = (
		frappe.qb.from_(mr)
		.inner_join(mri)
		.on(mri.parent == mr.name)
		.select(
			mr.name.as_("material_request"),
			mr.transaction_date,
			mr.owner.as_("requested_by"),
			mr.custom_approval_status.as_("approval_status"),
			mr.custom_approved_by.as_("approved_by"),
			mr.custom_approved_on.as_("approved_on"),
			mr.status,
			mri.name.as_("mr_item"),
			mri.from_warehouse,
			mri.warehouse.as_("to_warehouse"),
			mri.item_code,
			mri.item_name,
			mri.qty.as_("requested_qty"),
			mri.uom,
			mri.stock_qty.as_("approved_stock_qty"),
			mri.stock_uom,
			mri.custom_printing_machine.as_("requested_machine"),
		)
		.where((mr.material_request_type == "Material Transfer") & (mr.docstatus < 2))
		.orderby(mr.transaction_date, order=frappe.qb.desc)
		.orderby(mr.name, order=frappe.qb.desc)
		.orderby(mri.idx)
	)
	for key, condition in (
		("from_date", lambda v: mr.transaction_date >= v),
		("to_date", lambda v: mr.transaction_date <= v),
		("material_request", lambda v: mr.name == v),
		("approval_status", lambda v: mr.custom_approval_status == v),
		("warehouse", lambda v: mri.warehouse == v),
		("item_code", lambda v: mri.item_code == v),
		("requested_by", lambda v: mr.owner == v),
	):
		if filters.get(key):
			query = query.where(condition(filters[key]))

	# The store sees what is asked of it, a branch what it asked for.
	request_rows = [
		r
		for r in query.run(as_dict=True)
		if is_supplying_warehouse(r.from_warehouse) and (r.from_warehouse in allowed or r.to_warehouse in allowed)
	]
	if not request_rows:
		return []

	se = frappe.qb.DocType("Stock Entry")
	sed = frappe.qb.DocType("Stock Entry Detail")
	issues = (
		frappe.qb.from_(sed)
		.inner_join(se)
		.on(se.name == sed.parent)
		.select(
			sed.material_request_item,
			se.name.as_("stock_entry"),
			se.posting_date.as_("issue_date"),
			se.posting_time.as_("issue_time"),
			se.custom_received_by.as_("received_by"),
			se.custom_issued_by.as_("issued_by"),
			sed.qty.as_("issued_qty"),
			sed.uom.as_("issued_uom"),
			sed.transfer_qty.as_("issued_stock_qty"),
			sed.custom_printing_machine.as_("printing_machine"),
		)
		.where((se.docstatus == 1) & sed.material_request_item.isin([r.mr_item for r in request_rows]))
		.orderby(se.posting_date)
		.orderby(se.posting_time)
		.orderby(sed.idx)
		.run(as_dict=True)
	)
	by_row = {}
	for issue in issues:
		by_row.setdefault(issue.material_request_item, []).append(issue)

	data = []
	for row in request_rows:
		row_issues = by_row.get(row.mr_item, [])
		row.issued_total = sum(flt(i.issued_stock_qty) for i in row_issues)
		row.remaining = max(flt(row.approved_stock_qty) - row.issued_total, 0) if row.approval_status == APPROVED else None
		row.approval_status = _(row.approval_status) if row.approval_status else _("Draft")
		row.status = _(row.status)
		# Before anything is issued, the machine the request names (if any).
		for issue in row_issues or [frappe._dict(printing_machine=row.requested_machine)]:
			if filters.printing_machine and issue.printing_machine != filters.printing_machine:
				continue
			data.append({**row, **issue})
	return data
