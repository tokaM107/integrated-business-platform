# The accountant's own screen (شاشة المحاسب, page imed-accountant; the owner, 9 Nov 2026: "an accountant's account,
# the screen he should see"; 10 Nov 2026, the design approved: "what matters to the accountant"). In order:
#
#   today      the cash in the safes now (the businesses' safes and his custody: no bank, no wallet), what came into
#              them today and what went out, and the safes not closed yet today
#   waiting    what waits on him, each with a line saying what it is: expenses and doctors' entries to approve,
#              purchase requests the owner approved, cash handed to him, discrepancies, closes and weeks to review
#   safes      each safe's balance, and whether its day was closed today
#   month      each business's revenue, expenses and net, from the first of the month to today
#   outside    owed to us by customers, owed by us to suppliers, owed to the doctors: each on its own
#
# Every count and line of "waiting" is read through get_list, so it never shows more than his permissions do; the
# figures are read from the ledger (owner_figures.py, business_figures.py), which the accountant may read.
import frappe
from frappe import _
from frappe.utils import flt, fmt_money, get_first_day, today

from imed_erp.imederp import owner_figures as figures
from imed_erp.imederp.roles import ACCOUNTANT
from imed_erp.imederp.treasuries import BUSINESS_TREASURY

# A discrepancy still being dealt with (cash_discrepancy.json); the others are closed.
OPEN_DISCREPANCY = ["Pending Investigation", "Responsibility Determined", "Recovery Recommended", "Pending Review"]
# The accountant's own custody (setup_coa.py): cash he holds, a safe of his.
CUSTODY = "عهدة المحاسب النقدية"
CUSTOMERS, SUPPLIERS = "العملاء", "الموردون"
# What the group owes the doctors (books' shares, students' fees collected for them), and what they owe it.
DOCTORS_OWED = ("مستحقات للأطباء — الكتب", "مقبوضات الطلبة لحساب الأطباء — التطبيق")
DOCTORS_OWE = ("مديونيات الأطباء — الكتب", "مستحقات على الأطباء — رسوم المنصة")


def is_accountant_only():
	"""The accountant's account: Accountant, without the owner's or the system's roles (they keep their own pages)."""
	roles = frappe.get_roles()
	return ACCOUNTANT in roles and not {"Super Admin", "System Manager"} & set(roles)


def full(name):
	abbr = frappe.get_cached_value("Company", figures.COMPANY, "abbr")
	return f"{name} - {abbr}"


def existing(names):
	return [full(n) for n in names if frappe.db.exists("Account", full(n))]


def money(value):
	return fmt_money(flt(value), precision=0, currency=frappe.db.get_default("currency") or "EGP")


def short(name):
	return (name or "").rsplit(" - ", 1)[0]


def rows_of(doctype, filters, fields, order_by="creation desc"):
	# Asked first, not found out by an error: a refused get_list also leaves "Insufficient Permission for ..." in
	# the messages, and the desk showed it as a box over his own screen (seen 11 Nov 2026, Material Request).
	if not frappe.has_permission(doctype, "read"):
		return None  # not his to see: the tile is left out
	try:
		return frappe.get_list(doctype, filters=filters, fields=fields, order_by=order_by, limit_page_length=0)
	except frappe.PermissionError:
		frappe.clear_last_message()
		return None


def describe(key, rows):
	"""The line under a waiting item: what it is, at a glance."""
	if not rows:
		return _("مفيش")
	if key == "expenses":
		top = max(rows, key=lambda r: flt(r.amount))
		return _("أكبرها: {0} {1}").format(top.expense_category or "", money(top.amount))
	if key == "purchases":
		items = frappe.get_all("Material Request Item", filters={"parent": ["in", [r.name for r in rows[:3]]]}, fields=["item_name", "warehouse"], limit=3)
		return "، ".join(f"{i.item_name} ({short(i.warehouse)})" for i in items)
	if key == "handovers":
		return "، ".join(_("من {0} {1}").format(short(r.treasury), money(r.amount)) for r in rows[:2])
	if key == "discrepancies":
		return "، ".join(f"{_(r.kind)} {money(r.amount)}، {short(r.business)}" for r in rows[:2])
	if key == "closes":
		return "، ".join(f"{short(r.treasury)} {frappe.format_value(r.close_date, {'fieldtype': 'Date'})}" for r in rows[:2])
	if key == "weeks":
		return "، ".join(frappe.format_value(r.week_start, {"fieldtype": "Date"}) for r in rows[:2])
	if key == "doctors":
		return _("أكبرها: {0}").format(money(max(flt(r.amount) for r in rows)))
	return ""


WAITING = [
	("expenses", "مصروفات مستنية موافقتك", "Expense", {"docstatus": 0, "approval_status": "Pending Approval"}, ["name", "amount", "expense_category"]),
	# Something finished in a store, asked for by its branch and approved by the owner: his to buy (10 Nov 2026).
	("purchases", "طلبات شراء وافق عليها المالك", "Material Request", {"docstatus": 1, "material_request_type": "Purchase", "custom_approval_status": "Approved", "per_received": ["<", 100], "status": ["not in", ["Stopped", "Cancelled"]]}, ["name"]),
	("handovers", "فلوس مسلّمة ليك ومستنية الاستلام", "Cash Handover", {"docstatus": 1, "status": "Pending Receipt", "receiver_kind": "Accountant"}, ["name", "treasury", "amount"]),
	("discrepancies", "عجز أو زيادة لسه مفتوحة", "Cash Discrepancy", {"status": ["in", OPEN_DISCREPANCY]}, ["name", "kind", "amount", "business"]),
	("closes", "تقفيلات خزنة محتاجة مراجعة", "Treasury Close", {"docstatus": 1, "needs_review": 1}, ["name", "treasury", "close_date"]),
	("weeks", "أسابيع محتاجة مراجعة", "Weekly Cash Reconciliation", {"docstatus": ["<", 2], "needs_review": 1}, ["name", "week_start"]),
	("doctors", "قيود دكاترة مستنية موافقتك", "Doctor Ledger Entry", {"docstatus": 0, "approval_status": "Pending Approval"}, ["name", "amount"]),
]


def waiting():
	"""What waits on the accountant: key, label, count, a line saying what it is, and the list it opens."""
	out = []
	for key, label, doctype, filters, fields in WAITING:
		rows = rows_of(doctype, filters, fields)
		if rows is None:
			continue
		out.append({"key": key, "label": _(label), "count": len(rows), "detail": describe(key, rows), "doctype": doctype, "filters": filters})
	return out


def safes():
	"""The businesses' safes and the accountant's custody, each with its balance and whether its day was closed
	today (None: a safe whose days are not closed, such as the main treasury)."""
	names = existing(list(dict.fromkeys(list(BUSINESS_TREASURY.values()) + [CUSTODY])))
	day = today()
	closed_today = set(frappe.get_all("Treasury Close", filters={"close_date": day, "docstatus": 1, "treasury": ["in", names or [""]]}, pluck="treasury"))
	ever_closed = set(frappe.get_all("Treasury Close", filters={"docstatus": 1, "treasury": ["in", names or [""]]}, pluck="treasury", distinct=True))
	return [
		{
			"account": name,
			"label": _("عهدتك") if name == full(CUSTODY) else short(name),
			"balance": figures.balance([name]),
			"closed_today": (name in closed_today) if name in ever_closed else None,
		}
		for name in names
	]


def money_today(names):
	"""What came into the safes today and what went out: each voucher's net on the safes, so money moved from one
	safe to another counts neither in nor out."""
	if not names:
		return 0.0, 0.0
	rows = frappe.db.sql(
		"""select voucher_no, sum(debit - credit) from `tabGL Entry`
		where company = %(company)s and is_cancelled = 0 and posting_date = %(day)s and account in %(accounts)s
		group by voucher_type, voucher_no""",
		{"company": figures.COMPANY, "day": today(), "accounts": tuple(names)},
	)
	came = sum(flt(net) for _voucher, net in rows if flt(net) > 0)
	went = -sum(flt(net) for _voucher, net in rows if flt(net) < 0)
	return flt(came, 2), flt(went, 2)


def month_by_business():
	"""Each business's revenue, expenses and net this month (first of the month to today), the shared premises' too."""
	from imed_erp.imederp import business_figures as bf

	start, end = get_first_day(today()), today()
	ledger = bf.ledger(start, end)
	rows = []
	for business in bf.activities():
		revenue = -flt(ledger.get((business.name, "Income")))
		expenses = flt(ledger.get((business.name, "Expense")))
		if not revenue and not expenses and business.label == "الإدارة الرئيسية":
			continue
		rows.append({"business": business.label, "revenue": flt(revenue, 2), "expenses": flt(expenses, 2), "net": flt(revenue - expenses, 2)})
	untagged_revenue = -flt(ledger.get(("", "Income")))
	untagged_expenses = flt(ledger.get(("", "Expense")))
	if untagged_revenue or untagged_expenses:
		rows.append({"business": _("من غير نشاط"), "revenue": flt(untagged_revenue, 2), "expenses": flt(untagged_expenses, 2), "net": flt(untagged_revenue - untagged_expenses, 2)})
	total = {k: flt(sum(r[k] for r in rows), 2) for k in ("revenue", "expenses", "net")}
	return {"from": str(start), "to": str(end), "rows": rows, "total": total}


def outside():
	customers = figures.balance(existing([CUSTOMERS]))
	suppliers = figures.balance(existing([SUPPLIERS]), -1)
	doctors_owed = figures.balance(existing(DOCTORS_OWED), -1)
	doctors_owe = figures.balance(existing(DOCTORS_OWE))
	return [
		{"key": "customers", "label": _("لينا عند العملاء"), "value": customers, "detail": _("عربون وفواتير لسه متدفعتش"), "report": "Accounts Receivable"},
		{"key": "suppliers", "label": _("علينا للموردين"), "value": suppliers, "detail": _("ورق وخامات آجل"), "report": "Accounts Payable"},
		{
			"key": "doctors",
			"label": _("مستحقات الدكاترة"),
			"value": doctors_owed,
			"detail": _("نصيبهم من الكتب والكورسات") + (_("، وعليهم {0}").format(money(doctors_owe)) if doctors_owe > 0 else ""),
			"report": "Doctor Receivables",
		},
	]


@frappe.whitelist()
def overview():
	figures.check_reader()
	boxes = safes()
	came, went = money_today([b["account"] for b in boxes])
	closable = [b for b in boxes if b["closed_today"] is not None]
	return {
		"user": frappe.utils.get_fullname(frappe.session.user),
		"today": {
			"cash": flt(sum(b["balance"] for b in boxes), 2),
			"came": came,
			"went": went,
			"not_closed": [b["label"] for b in closable if not b["closed_today"]],
			"closable": len(closable),
		},
		"waiting": waiting(),
		"safes": boxes,
		"month": month_by_business(),
		"outside": outside(),
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
