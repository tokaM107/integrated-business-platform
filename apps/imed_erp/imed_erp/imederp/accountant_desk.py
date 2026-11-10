# The accountant's own screen (شاشة المحاسب, page imed-accountant; the owner, 9 Nov 2026: "an accountant's account,
# the screen he should see, what he may open, and nothing that does not concern him"): the company's money at a
# glance, what waits on him (expenses to approve, cash handed to him, discrepancies, closes and weeks to review,
# doctors' entries to approve), and the documents he makes most. Every count is read through get_list, so it never
# shows more than his permissions do; the figures are the owner's (owner_figures.py), which the accountant may read.
import frappe
from frappe import _

from imed_erp.imederp import owner_figures as figures
from imed_erp.imederp.roles import ACCOUNTANT

# A discrepancy still being dealt with (cash_discrepancy.json); the others are closed.
OPEN_DISCREPANCY = ["Pending Investigation", "Responsibility Determined", "Recovery Recommended", "Pending Review"]


def is_accountant_only():
	"""The accountant's account: Accountant, without the owner's or the system's roles (they keep their own pages)."""
	roles = frappe.get_roles()
	return ACCOUNTANT in roles and not {"Super Admin", "System Manager"} & set(roles)


def count(doctype, filters):
	try:
		return len(frappe.get_list(doctype, filters=filters, pluck="name", limit_page_length=0))
	except frappe.PermissionError:
		return None  # not his to see: the tile is left out


def waiting():
	"""What waits on the accountant: (key, label, count, doctype, the list's filters)."""
	rows = [
		("expenses", _("مصروفات مستنية موافقتك"), "Expense", {"docstatus": 0, "approval_status": "Pending Approval"}),
		("handovers", _("فلوس مسلّمة ليك ومستنية الاستلام"), "Cash Handover", {"docstatus": 1, "status": "Pending Receipt", "receiver_kind": "Accountant"}),
		("discrepancies", _("عجز أو زيادة لسه مفتوحة"), "Cash Discrepancy", {"status": ["in", OPEN_DISCREPANCY]}),
		("closes", _("تقفيلات خزنة محتاجة مراجعة"), "Treasury Close", {"docstatus": 1, "needs_review": 1}),
		("weeks", _("أسابيع محتاجة مراجعة"), "Weekly Cash Reconciliation", {"docstatus": ["<", 2], "needs_review": 1}),
		("doctors", _("قيود دكاترة مستنية موافقتك"), "Doctor Ledger Entry", {"docstatus": 0, "approval_status": "Pending Approval"}),
	]
	out = []
	for key, label, doctype, filters in rows:
		n = count(doctype, filters)
		if n is not None:
			out.append({"key": key, "label": label, "count": n, "doctype": doctype, "filters": filters})
	return out


@frappe.whitelist()
def overview():
	figures.check_reader()
	revenue, expenses = figures.revenue_and_expenses()
	return {
		"user": frappe.utils.get_fullname(frappe.session.user),
		"figures": [
			{"key": "cash", "label": _("الفلوس في الخزن"), "value": figures.balance(figures.leaf_accounts(account_type=["in", ["Cash", "Bank"]]))},
			{"key": "revenue", "label": _("إيرادات الشهر"), "value": revenue},
			{"key": "expenses", "label": _("مصروفات الشهر"), "value": expenses},
			{"key": "owed_to_us", "label": _("لينا عند الناس"), "value": figures.balance(figures.leaf_accounts(account_type="Receivable"))},
			{"key": "we_owe", "label": _("علينا للناس"), "value": figures.balance(figures.under(figures.PAYABLES_GROUP), -1)},
		],
		"boxes": [{"account": account, "balance": value} for account, value in figures.cash_box_balances() if value],
		"waiting": waiting(),
	}


# What is not the accountant's (the owner, 9 and 10 Nov 2026: "remove what does not matter to him", then "fix it":
# hidden from his sidebar first, refused on the server now): the libraries' counters and printing machines, the
# halls' and studio's prices and resources, and the integrations' settings. The stock counts stay his (a count dated
# in the past is the accountant's), and so do the bookings and the studio's packages: their money (deposits, a
# package cancelled and paid back) is the accounts'.
NOT_HIS = (
	"Daily Counter Reading",
	"Printer Reading",
	"Printing Machine",
	"Booking Resource",
	"Booking Package",
	"Booking Extra",
	"Hall Price Tier",
	"XStudio Settings",
	"Sparkle Settings",
)


def accountant_only(user=None):
	user = user or frappe.session.user
	if not user or user in ("Administrator", "Guest"):
		return False
	roles = set(frappe.get_roles(user))
	return ACCOUNTANT in roles and not {"Super Admin", "System Manager"} & roles


def has_permission(doc, ptype=None, user=None, debug=False):
	"""Frappe asks this for each of NOT_HIS (hooks.py has_permission): only ever a refusal, never a right added."""
	return not accountant_only(user)


def query_conditions(user=None):
	"""The lists of NOT_HIS are empty for him (hooks.py permission_query_conditions)."""
	return "1=0" if accountant_only(user) else ""


def boot_session(bootinfo):
	"""Nor are they offered to him (the search, the links): taken out of what the desk is told he may read."""
	if not accountant_only():
		return
	user = bootinfo.get("user") or {}
	for key in ("can_read", "can_write", "can_create", "can_select", "can_search", "can_get_report", "can_export", "can_print", "can_email"):
		if isinstance(user.get(key), list):
			user[key] = [d for d in user[key] if d not in NOT_HIS]
