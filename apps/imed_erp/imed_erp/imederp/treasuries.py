# Each business's own cash box (CORE-01, ACC-01). A branch manager pays expenses and sends transfers only
# from their own business's cash box or from the group's wallets; the owner and the accountant may use any
# treasury. setup_library.py points each library's cash sales at its own cash box through these names too.

import frappe
from frappe import _

# Business (cost center) -> its cash box, both without the company abbreviation.
BUSINESS_TREASURY = {
	"قاعات Imed": "خزينة سنتر Imed",
	"استوديو X": "خزينة X Studio",
	"مصروفات المقر المشتركة": "الخزينة الرئيسية",
	"مكتبة الأزاريطة": "خزينة مكتبة الأزاريطة",
	"مكتبة المواساة": "خزينة مكتبة المواساة",
	"تطبيق BA Plus": "خزينة تطبيق BA Plus",
}

# One InstaPay and one Vodafone Cash number for the whole group (CORE-03), so every business may use them.
WALLETS = ["محفظة InstaPay", "محفظة Vodafone Cash"]

# Holders may pay from any treasury.
ANY_TREASURY_ROLE = "Accounts Manager"


def abbr_of(cost_center):
	company = frappe.db.get_value("Cost Center", cost_center, "company")
	return frappe.get_cached_value("Company", company, "abbr")


def plain(name, abbr):
	suffix = f" - {abbr}"
	return name[: -len(suffix)] if name and name.endswith(suffix) else name


def allowed_treasuries(business):
	"""The full account names a branch manager of `business` may pay from."""
	abbr = abbr_of(business)
	own = BUSINESS_TREASURY.get(plain(business, abbr))
	return [f"{name} - {abbr}" for name in ([own] if own else []) + WALLETS]


def check_treasury(business, treasury):
	if not business or not treasury or ANY_TREASURY_ROLE in frappe.get_roles():
		return
	allowed = allowed_treasuries(business)
	if treasury not in allowed:
		frappe.throw(
			_("{0} is not a treasury of {1}. Choose one of: {2}.").format(treasury, business, ", ".join(allowed)),
			title=_("Wrong Treasury"),
		)


def user_treasuries(user=None):
    """Every treasury a user without ANY_TREASURY_ROLE may use: their businesses' cash boxes and the wallets."""
    user = user or frappe.session.user
    businesses = frappe.get_all(
        "User Permission", filters={"user": user, "allow": "Cost Center"}, pluck="for_value"
    )
    allowed = set()
    for business in businesses:
        allowed.update(allowed_treasuries(business))
    return allowed


def check_entry_treasuries(doc, method=None):
    """Journal Entry and Payment Entry validate hook: a branch manager may make regular entries (owner's
    decision of 7 Oct 2026), but only on their own business's cash box or the group's wallets (8 Oct 2026).
    Expenses and transfers check their treasury themselves and post their entries in the system's name."""
    if ANY_TREASURY_ROLE in frappe.get_roles() or doc.flags.from_expense or doc.flags.from_inter_business_transfer:
        return
    if doc.doctype == "Journal Entry":
        accounts = [row.account for row in doc.accounts]
    else:
        accounts = [doc.paid_from, doc.paid_to]
    treasuries = [a for a in accounts if a and frappe.db.get_value("Account", a, "account_type") in ("Cash", "Bank")]
    if not treasuries:
        return
    allowed = user_treasuries()
    for treasury in treasuries:
        if treasury not in allowed:
            frappe.throw(
                _("{0} is not your business's treasury. You can use: {1}.").format(treasury, ", ".join(sorted(allowed)) or "-"),
                title=_("Wrong Treasury"),
            )
