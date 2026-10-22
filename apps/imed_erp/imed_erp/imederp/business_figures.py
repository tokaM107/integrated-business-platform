# The group's revenue and expenses by business, read from the ledger, for the Owner Dashboard's yesterday
# (owner_yesterday.py), Revenue by Period (RPT-01) and Profit Before and After Shared Costs (RPT-02).
#
# A business is a cost center (setup_core.py): an activity is a leaf (مكتبة الأزاريطة, مكتبة المواساة, قاعات Imed,
# استوديو X, تطبيق BA Plus, الإدارة الرئيسية, مصروفات المقر المشتركة), a group stands for the branches under it
# (مكتبات 2Be Doctor: both libraries; سنتر Imed: halls, studio and the shared premises). The site has no Branch
# dimension: the branches are these cost centers.
#
# What counts (accrual basis, docs/known-issues.md ACC-05): GL Entry on the Income and Expense accounts, of the group's
# company, not cancelled (is_cancelled = 0 drops a cancelled voucher and its reversal alike), not an opening entry and
# not a Period Closing Voucher (it moves the year's profit off the income and expense accounts). Only submitted
# documents reach the ledger, so a draft is never counted; each voucher posts its revenue once (the invoice), and a
# payment or a deposit moves cash and the customer's account, never revenue.
#
# The shared premises' expenses (EXP-03/04): an expense on مصروفات المقر المشتركة is split by ERPNext as it is posted
# (Cost Center Allocation, made by an Allocation Rule), so the ledger shows it on the businesses and keeps no trace of
# the shared cost center. The document still names it: the Expense's Journal Entry row, or a Purchase Invoice item.
# allocated() reads those documents to tell, in the ledger, the part of each business's expenses that came from the
# shared premises. What is still on the shared cost center in the ledger was not split (no rule covered its date).

import frappe
from frappe import _
from frappe.utils import flt, getdate

from imed_erp.imederp.owner_figures import COMPANY

# The designated cost center of the shared premises' expenses (README, Splitting the shared premises' expenses).
SHARED_PREMISES = "مصروفات المقر المشتركة"
PNL = ("Income", "Expense")
NO_COST_CENTER = ""


def company():
	return COMPANY


def business_tree():
	"""Every cost center of the company in tree order, as dicts: name, label, parent, is_group, depth."""
	rows = frappe.get_all(
		"Cost Center",
		filters={"company": company()},
		fields=["name", "cost_center_name", "parent_cost_center", "is_group", "lft", "rgt"],
		order_by="lft",
	)
	depth_of, tree = {}, []
	for row in rows:
		depth = depth_of.get(row.parent_cost_center, -1) + 1
		depth_of[row.name] = depth
		tree.append(
			frappe._dict(
				name=row.name,
				label=row.cost_center_name,
				parent=row.parent_cost_center,
				is_group=row.is_group,
				depth=depth,
				lft=row.lft,
				rgt=row.rgt,
			)
		)
	return tree


def subtree(cost_center=None):
	"""The business tree under `cost_center` (itself included), or the whole tree. Refuses another company's."""
	tree = business_tree()
	if not cost_center:
		return tree
	top = next((row for row in tree if row.name == cost_center), None)
	if not top:
		frappe.throw(_("{0} is not a business of {1}.").format(cost_center, company()))
	return [row for row in tree if top.lft <= row.lft and row.rgt <= top.rgt]


def activities(tree=None):
	"""The leaf cost centers: the businesses money is posted on."""
	return [row for row in (tree or business_tree()) if not row.is_group]


def shared_cost_centers():
	"""The shared premises' cost centers: those an allocation splits, and the designated one."""
	names = set(
		frappe.get_all(
			"Cost Center Allocation", filters={"company": company(), "docstatus": 1}, pluck="main_cost_center"
		)
	)
	abbr = frappe.get_cached_value("Company", company(), "abbr")
	if frappe.db.exists("Cost Center", f"{SHARED_PREMISES} - {abbr}"):
		names.add(f"{SHARED_PREMISES} - {abbr}")
	return names


def check_dates(from_date, to_date):
	if not from_date or not to_date:
		frappe.throw(_("Choose the dates."))
	from_date, to_date = getdate(from_date), getdate(to_date)
	if from_date > to_date:
		frappe.throw(_("From Date must be before To Date."))
	return from_date, to_date


def ledger(from_date, to_date, cost_centers=None, by_date=False):
	"""{(cost center or "", root type[, posting date]): debit - credit} on the income and expense accounts.
	One grouped query: the database adds up, whatever the number of entries."""
	conditions = [
		"gl.company = %(company)s",
		"gl.is_cancelled = 0",
		"gl.is_opening = 'No'",
		"gl.voucher_type != 'Period Closing Voucher'",
		"gl.posting_date between %(from_date)s and %(to_date)s",
		"acc.root_type in %(pnl)s",
	]
	values = {"company": company(), "from_date": from_date, "to_date": to_date, "pnl": PNL}
	if cost_centers is not None:
		if not cost_centers:
			return {}
		conditions.append("gl.cost_center in %(cost_centers)s")
		values["cost_centers"] = tuple(cost_centers)
	date = ", gl.posting_date" if by_date else ""
	rows = frappe.db.sql(
		f"""select coalesce(gl.cost_center, '') as cost_center, acc.root_type{date}, sum(gl.debit - gl.credit)
		from `tabGL Entry` gl join `tabAccount` acc on acc.name = gl.account
		where {" and ".join(conditions)}
		group by coalesce(gl.cost_center, ''), acc.root_type{date}""",
		values,
	)
	return {tuple(row[:-1]): flt(row[-1]) for row in rows}


def allocated(from_date, to_date):
	"""What ERPNext split onto the businesses from the shared premises' lines of the period:
	frappe._dict(by_business={(business, root type): debit - credit}, by_shared={shared cost center: debit - credit}).

	For every submitted Journal Entry (an Expense's, a bill paid in parts) and Purchase Invoice of the period with a
	line on a shared cost center: what the ledger holds for each account on each business, less the lines the
	document itself put on that business. What is left came from the shared line."""
	result = frappe._dict(by_business={}, by_shared={})
	shared = shared_cost_centers()
	if not shared:
		return result
	values = {"company": company(), "from_date": from_date, "to_date": to_date, "shared": tuple(shared)}
	sources = {
		"Journal Entry": frappe.db.sql(
			"""select row.parent, row.account, row.cost_center, sum(row.debit - row.credit)
			from `tabJournal Entry Account` row join `tabJournal Entry` doc on doc.name = row.parent
			where doc.docstatus = 1 and doc.company = %(company)s
				and doc.posting_date between %(from_date)s and %(to_date)s
				and row.parent in (
					select parent from `tabJournal Entry Account` where cost_center in %(shared)s
				)
			group by row.parent, row.account, row.cost_center""",
			values,
		),
		"Purchase Invoice": frappe.db.sql(
			"""select row.parent, row.expense_account, row.cost_center, sum(row.base_net_amount)
			from `tabPurchase Invoice Item` row join `tabPurchase Invoice` doc on doc.name = row.parent
			where doc.docstatus = 1 and doc.company = %(company)s
				and doc.posting_date between %(from_date)s and %(to_date)s
				and row.parent in (
					select parent from `tabPurchase Invoice Item` where cost_center in %(shared)s
				)
			group by row.parent, row.expense_account, row.cost_center""",
			values,
		),
	}
	for voucher_type, lines in sources.items():
		if not lines:
			continue
		# What the document put directly on each business (its own lines, not the shared ones), and the shared cost
		# center its shared line is on.
		direct, source_of = {}, {}
		for voucher_no, account, cost_center, amount in lines:
			if cost_center in shared:
				source_of.setdefault(voucher_no, cost_center)
			else:
				key = (voucher_no, account, cost_center)
				direct[key] = direct.get(key, 0) + flt(amount)
		entries = frappe.db.sql(
			"""select gl.voucher_no, gl.account, gl.cost_center, acc.root_type, sum(gl.debit - gl.credit)
			from `tabGL Entry` gl join `tabAccount` acc on acc.name = gl.account
			where gl.voucher_type = %(voucher_type)s and gl.voucher_no in %(vouchers)s and gl.is_cancelled = 0
				and acc.root_type in %(pnl)s and gl.cost_center not in %(shared)s
			group by gl.voucher_no, gl.account, gl.cost_center, acc.root_type""",
			{
				"voucher_type": voucher_type,
				"vouchers": tuple({line[0] for line in lines}),
				"pnl": PNL,
				"shared": tuple(shared),
			},
		)
		for voucher_no, account, cost_center, root_type, amount in entries:
			split = flt(amount) - direct.get((voucher_no, account, cost_center), 0)
			if abs(split) >= 0.005:
				key = (cost_center, root_type)
				result.by_business[key] = flt(result.by_business.get(key, 0) + split, 2)
				source = source_of[voucher_no]
				result.by_shared[source] = flt(result.by_shared.get(source, 0) + split, 2)
	return result
