# What the studio and the libraries took in, written to the ledger by itself (the user, 11 Nov 2026: "the month's
# revenue counted 6,100 only: it must hold the libraries, the studio and the app"). Both are run by systems of
# their own, mirrored here and, until now, shown only: XStudio's bookings and packages (imederp/xstudio/sync.py)
# and the libraries' documents (imederp/library_sync/sync.py). The owner's money figures read the ledger
# (owner_figures.py), so neither was in "Revenue This Month" nor in the cash boxes.
#
#   studio      what XStudio says was paid on a booking (Booking.xstudio_amount_paid) or a prepaid package (Studio
#               Hour Package.xstudio_paid_total): into خزينة X Studio, as the studio's revenue, when it is paid
#               (XStudio's payments carry no ids, so the figure posted is the difference since the last posting).
#               An amount XStudio lowers later is NOT reversed: it is listed for the accountant.
#   libraries   one figure a library a day: its final, not cancelled sales less its returns (the same rule as the
#               Owner Dashboard's cards, owner_periods.py), into the library's cash box, as its revenue. The
#               library's system is the source of truth, so a day that changes is corrected by the difference,
#               up or down.
#
# Every entry is a Journal Entry carrying a key (custom_imed_posting_key): what was already posted for a booking, a
# package or a library's day is read back from the submitted entries with its key, so a run never posts the same
# money twice and nothing is kept on the mirrored records. An entry is dated the day the money belongs to; when that
# day cannot take it any more (its treasury closed, an accounting period closed) it is dated today and says so.
# One target that fails is listed with its reason and the others go on.
#
# Off until switched on in Automatic Revenue Settings, each with the day it starts from. Runs from the scheduler
# (hooks.py) and by hand: bench --site <site> execute imed_erp.imederp.revenue_posting.run

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt, getdate, now_datetime, today

from imed_erp.imederp.library_revenue import LIBRARY_REVENUE
from imed_erp.imederp.library_sync.contract import RETURN_KINDS, SALES_KINDS
from imed_erp.imederp.system_user import as_administrator
from imed_erp.imederp.treasuries import BUSINESS_TREASURY

SETTINGS = "Automatic Revenue Settings"
KEY = "custom_imed_posting_key"
LOCK = "imed_erp_revenue_posting"
STUDIO = "استوديو X"
STUDIO_INCOME = "إيراد X Studio"

CUSTOM_FIELDS = {
	"Journal Entry": [
		{
			"fieldname": KEY,
			"fieldtype": "Data",
			"label": "Automatic Posting Of",
			"read_only": 1,
			"no_copy": 1,
			"search_index": 1,
			"insert_after": "custom_booking",
			"description": "Set by the system on an entry it posted by itself (imederp/revenue_posting.py).",
		},
	],
}


def make_custom_fields():
	"""after_install / after_migrate hook."""
	create_custom_fields(CUSTOM_FIELDS, update=True)


def company():
	from imed_erp.imederp.owner_figures import COMPANY

	return COMPANY


def full(name):
	return f"{name} - {frappe.get_cached_value('Company', company(), 'abbr')}"


def posted(key, income):
	"""What the submitted entries carrying `key` already put on the income account (credit less debit)."""
	return flt(
		frappe.db.sql(
			f"""select coalesce(sum(a.credit - a.debit), 0) from `tabJournal Entry Account` a
			join `tabJournal Entry` j on j.name = a.parent
			where j.docstatus = 1 and j.`{KEY}` = %s and a.account = %s""",
			(key, income),
		)[0][0],
		2,
	)


def make_entry(target, amount, date, late=False):
	"""Dr the cash box, Cr the income account (the other way round for a negative amount)."""
	value = abs(flt(amount, 2))
	debit, credit = (target["cash"], target["income"]) if amount > 0 else (target["income"], target["cash"])
	remark = target["remark"] + (" " + _("Dated today: its own day ({0}) is closed.").format(frappe.format_value(target["date"], {"fieldtype": "Date"})) if late else "")
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": company(),
			"posting_date": date,
			KEY: target["key"],
			"user_remark": remark,
			"accounts": [
				{"account": debit, "debit_in_account_currency": value, "cost_center": target["cost_center"]},
				{"account": credit, "credit_in_account_currency": value, "cost_center": target["cost_center"]},
			],
		}
	)
	entry.flags.imed_automatic_posting = True
	entry.insert(ignore_permissions=True)
	entry.submit()
	return entry.name


def settle(target):
	"""Bring what is posted for one target up to what it should be. Returns ("posted", entry, amount),
	("review", None, amount) for a fall that is not posted, or (None, None, 0) when nothing is to be done."""
	difference = flt(flt(target["amount"], 2) - posted(target["key"], target["income"]), 2)
	if abs(difference) < 0.01:
		return None, None, 0
	if difference < 0 and not target.get("follows_source"):
		return "review", None, difference
	day = min(getdate(target["date"]), getdate(today()))
	frappe.db.savepoint("imed_revenue_target")
	try:
		return "posted", make_entry(target, difference, day), difference
	except frappe.ValidationError:
		# Its own day cannot take it (the treasury's day is closed, a period is closed): today, and it says so.
		frappe.db.rollback(save_point="imed_revenue_target")
		frappe.clear_messages()
		if day == getdate(today()):
			raise
		return "posted", make_entry(target, difference, today(), late=True), difference


# ---------------- the targets ----------------
def studio_targets(start):
	cost_center, cash, income = full(STUDIO), full(BUSINESS_TREASURY[STUDIO]), full(STUDIO_INCOME)
	targets = []
	for b in frappe.get_all(
		"Booking",
		filters={"source_system": "xstudio", "booking_date": [">=", start], "xstudio_amount_paid": [">", 0]},
		fields=["name", "booking_date", "xstudio_amount_paid", "xstudio_customer_name"],
		order_by="booking_date, name",
	):
		targets.append(
			{
				"key": f"xstudio:booking:{b.name}",
				"amount": b.xstudio_amount_paid,
				"date": b.booking_date,
				"cash": cash,
				"income": income,
				"cost_center": cost_center,
				"remark": _("Studio booking {0} ({1}): paid in XStudio.").format(b.name, b.xstudio_customer_name or "-"),
			}
		)
	for p in frappe.get_all(
		"Studio Hour Package",
		filters={"source_system": "xstudio", "purchase_date": [">=", start], "xstudio_paid_total": [">", 0], "docstatus": ["<", 2]},
		fields=["name", "purchase_date", "xstudio_paid_total", "package_name"],
		order_by="purchase_date, name",
	):
		targets.append(
			{
				"key": f"xstudio:package:{p.name}",
				"amount": p.xstudio_paid_total,
				"date": p.purchase_date,
				"cash": cash,
				"income": income,
				"cost_center": cost_center,
				"remark": _("Studio package {0} ({1}): paid in XStudio.").format(p.name, p.package_name or "-"),
			}
		)
	return targets


def library_targets(start):
	targets = {}
	for cost_center, day, kind, value in frappe.db.sql(
		"""select cost_center, date(reg_date), document_kind, coalesce(sum(total), 0) from `tabLibrary Sales Document`
		where is_final = 1 and is_cancelled = 0 and reg_date >= %s and cost_center is not null and cost_center != ''
			and document_kind in %s
		group by cost_center, date(reg_date), document_kind""",
		(f"{start} 00:00:00", SALES_KINDS + RETURN_KINDS),
	):
		library = (cost_center or "").rsplit(" - ", 1)[0]
		if library not in LIBRARY_REVENUE or library not in BUSINESS_TREASURY:
			continue
		target = targets.setdefault(
			(cost_center, str(day)),
			{
				"key": f"library:{cost_center}:{day}",
				"amount": 0,
				"date": day,
				"cash": full(BUSINESS_TREASURY[library]),
				"income": full(LIBRARY_REVENUE[library]),
				"cost_center": cost_center,
				"remark": _("{0}: sales less returns of {1}, from the library's sales system.").format(library, frappe.format_value(day, {"fieldtype": "Date"})),
				"follows_source": True,
			},
		)
		target["amount"] += flt(value) if kind in SALES_KINDS else -flt(value)
	# A day posted earlier whose documents were all cancelled since is brought back to nothing.
	for key, cost_center in frappe.db.sql(
		f"""select distinct j.`{KEY}`, a.cost_center from `tabJournal Entry` j join `tabJournal Entry Account` a on a.parent = j.name
		where j.docstatus = 1 and j.`{KEY}` like 'library:%%'"""
	):
		day = key.rsplit(":", 1)[-1]
		if (cost_center, day) in targets or getdate(day) < getdate(start):
			continue
		library = (cost_center or "").rsplit(" - ", 1)[0]
		if library in LIBRARY_REVENUE:
			targets[(cost_center, day)] = {
				"key": key, "amount": 0, "date": day, "cash": full(BUSINESS_TREASURY[library]), "income": full(LIBRARY_REVENUE[library]),
				"cost_center": cost_center, "remark": _("{0}: the sales of {1} were taken back in the library's sales system.").format(library, day), "follows_source": True,
			}
	return [targets[k] for k in sorted(targets)]


# ---------------- the run ----------------
def run():
	"""One run. Returns {"posted": n, "amount": x, "review": [...], "failed": [...]}; nothing when both are off."""
	settings = frappe.get_single(SETTINGS)
	if not cint(settings.post_studio) and not cint(settings.post_libraries):
		return None
	if cint(frappe.db.sql("select get_lock(%s, 0)", LOCK)[0][0]) != 1:
		return None
	result = {"posted": 0, "amount": 0.0, "review": [], "failed": []}
	try:
		targets = []
		if cint(settings.post_studio) and settings.studio_from:
			targets += studio_targets(settings.studio_from)
		if cint(settings.post_libraries) and settings.libraries_from:
			targets += library_targets(settings.libraries_from)
		with as_administrator():
			for target in targets:
				frappe.db.savepoint("imed_revenue_run")
				try:
					what, entry, amount = settle(target)
				except Exception as e:
					frappe.db.rollback(save_point="imed_revenue_run")
					frappe.clear_messages()
					result["failed"].append(f"{target['key']}: {str(e)[:140]}")
					continue
				if what == "posted":
					result["posted"] += 1
					result["amount"] = flt(result["amount"] + amount, 2)
				elif what == "review":
					result["review"].append(f"{target['key']}: {amount}")
		message = _("{0} entries posted, {1} in all.").format(result["posted"], frappe.format_value(result["amount"], {"fieldtype": "Currency"}))
		if result["review"]:
			message += "\n" + _("Lowered in XStudio after posting, for the accountant: {0}").format("; ".join(result["review"][:20]))
		if result["failed"]:
			message += "\n" + _("Not posted: {0}").format("; ".join(result["failed"][:20]))
		frappe.db.set_single_value(SETTINGS, {"last_run_at": now_datetime(), "last_message": message}, update_modified=False)
		frappe.db.commit()
	finally:
		frappe.db.sql("select release_lock(%s)", LOCK)
	return result


# ---------------- from the settings' screen ----------------
ROLES = ("System Manager", "Super Admin", "Accounts Manager")


@frappe.whitelist()
def preview(studio_from=None, libraries_from=None):
	"""What a run would post from these days, without posting anything: for the settings' screen, before it is
	switched on. Returns a list of {"what", "count", "amount"} and the amounts lowered in XStudio."""
	frappe.only_for(ROLES)
	groups, lowered = {}, 0
	targets = (studio_targets(studio_from) if studio_from else []) + (library_targets(libraries_from) if libraries_from else [])
	for target in targets:
		difference = flt(flt(target["amount"], 2) - posted(target["key"], target["income"]), 2)
		if abs(difference) < 0.01:
			continue
		if difference < 0 and not target.get("follows_source"):
			lowered += 1
			continue
		kind = target["key"].split(":")[0:2]
		what = {"xstudio": _("Studio bookings") if kind[1] == "booking" else _("Studio packages"), "library": (target["cost_center"] or "").rsplit(" - ", 1)[0]}[kind[0]]
		group = groups.setdefault(what, {"what": what, "count": 0, "amount": 0.0})
		group["count"] += 1
		group["amount"] = flt(group["amount"] + difference, 2)
	return {"groups": list(groups.values()), "lowered": lowered}


@frappe.whitelist(methods=["POST"])
def run_now():
	"""Run once from the settings' screen (the scheduler runs it every quarter of an hour anyway)."""
	frappe.only_for(ROLES)
	return run()
