# The assistant's read tools and its instructions, shared by every model provider (claude.py, gemini.py).
#
# AI-02 and the owner's rule of 1 Nov 2026: the assistant never creates, changes, deletes, submits or posts anything.
# It reads through a fixed set of tools (below), each of which calls Frappe as the user who asks, with that user's
# own permissions (frappe.get_list / frappe.get_doc / the query reports' own checks; never ignore_permissions), so a
# branch manager, were the assistant ever opened to her, would see her branch only. The model gets no database access,
# no SQL, no file system: only these tools, and the tools only read.
#
# Which model answers is the site's choice (docs/assistant/assistant.md); the tools are the same for all.

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_first_day, get_last_day, getdate, nowdate

MAX_TOOL_ROUNDS = 12  # a question may need a few reads; never an unbounded loop
MAX_ROWS = 200  # rows a list or report returns to the model
MAX_RESULT_CHARS = 60_000

# The reports the model may run (imederp/report; each checks its own readers). Report name -> short meaning.
REPORTS = {
	"Cash Box Balances": "what is in each cash box and wallet now, from the ledger",
	"Revenue by Period": "revenue by business per day, week or month (filters: from_date, to_date, period, business)",
	"Profit Before and After Shared Costs": "each business's revenue, expenses and profit for a period, shared premises costs split",
	"Outstanding Receivables": "who owes the company what, by customer and document",
	"Hall Bookings": "IMED hall bookings for a period: day, hall, type, attendees, rent, collected",
	"Treasury Balances": "the treasuries and their balances",
	"Expense Report": "expenses by category and business for a period",
	"Platform Fees": "BA Plus platform fees charged and collected per doctor",
	"Doctor Statement": "a doctor's account: accruals, payouts, charges, collections",
	"Doctor Debts": "what doctors owe on books and fees",
	"Daily Printing": "the libraries' printing counters, sheets sold and the difference per day",
	"Integration Status": "the state of each integration: XStudio, the libraries, BA Plus",
	"Unsold Editions": "doctors' editions with unsold copies",
	"Reorder Alerts": "stock items below their reorder level",
}
# DocTypes the model may list or count. Anything else is refused.
DOCTYPES = (
	"Booking", "Booking Resource", "Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry",
	"Expense", "Treasury Close", "Cash Discrepancy", "Cash Handover", "Doctor Agreement", "Doctor Ledger Entry",
	"Book Edition", "App Subscription", "Daily Counter Reading", "Printing Machine", "Customer", "Supplier", "Item",
	"Bin", "Stock Ledger Entry", "GL Entry", "Account", "Cost Center", "Warehouse", "Integration Import Log",
	"Studio Hour Package", "Recurring Expense", "Inter Business Transfer", "Hall Price Tier",
)

# Filters as a list of conditions: {"field": "booking_date", "operator": ">=", "value": "2026-11-01"}; a value that is
# a JSON list (for "in" / "between") or a number is written as JSON text ("[\"a\", \"b\"]", "150").
FILTERS_SCHEMA = {
	"type": "array",
	"items": {
		"type": "object",
		"properties": {
			"field": {"type": "string"},
			"operator": {"type": "string", "enum": ["=", "!=", ">", "<", ">=", "<=", "like", "not like", "in", "not in", "between", "is"]},
			"value": {"type": "string", "description": "the value; a JSON list for in/not in/between; 'set' or 'not set' for is"},
		},
		"required": ["field", "operator", "value"],
		"additionalProperties": False,
	},
}

TOOLS = [
	{
		"name": "dashboard_today",
		"description": "The Owner Dashboard's live band: today's revenue and expenses by business, the X Studio line "
		"as XStudio reports it, halls and studio bookings of the day, the IMED halls' state, platform fees, printing "
		"counters, and the integrations' health. Also the 15 dashboard cards (cash in the boxes, revenue, expenses and "
		"net this month, owed to us, we owe, platform fees, collections, cash shortages, open discrepancies, studio "
		"and hall bookings this month, unpaid on bookings, due on studio bookings). Start here for any question about "
		"today or this month.",
		"input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
		"strict": True,
	},
	{
		"name": "run_report",
		"description": "Run one of the ERP's reports and get its rows. Reports: "
		+ "; ".join(f"'{name}': {meaning}" for name, meaning in REPORTS.items())
		+ ". Pass the filters the report needs (dates as YYYY-MM-DD).",
		"input_schema": {
			"type": "object",
			"properties": {
				"report": {"type": "string", "enum": list(REPORTS)},
				"filters": {"type": "object", "additionalProperties": True, "description": "the report's filters, e.g. {\"from_date\": \"2026-11-01\", \"to_date\": \"2026-11-30\"}"},
			},
			"required": ["report", "filters"],
			"additionalProperties": False,
		},
		"strict": True,
	},
	{
		"name": "list_records",
		"description": "List records of a DocType with Frappe filters, as the asking user may see them. DocTypes: "
		+ ", ".join(DOCTYPES)
		+ ". Filters are a JSON object or a list of [field, operator, value]; operators =, !=, >, <, >=, <=, like, in, between. "
		"Use count_records when only the number matters.",
		"input_schema": {
			"type": "object",
			"properties": {
				"doctype": {"type": "string", "enum": list(DOCTYPES)},
				"filters": FILTERS_SCHEMA,
				"fields": {"type": "array", "items": {"type": "string"}, "description": "field names to return; [] for the name and the title"},
				"order_by": {"type": "string", "description": "e.g. 'booking_date desc'; '' for the default"},
				"limit": {"type": "integer", "minimum": 1, "maximum": 200},
			},
			"required": ["doctype", "filters", "fields", "order_by", "limit"],
			"additionalProperties": False,
		},
		"strict": True,
	},
	{
		"name": "count_records",
		"description": "Count the records of a DocType matching Frappe filters (same DocTypes and filters as list_records).",
		"input_schema": {
			"type": "object",
			"properties": {
				"doctype": {"type": "string", "enum": list(DOCTYPES)},
				"filters": FILTERS_SCHEMA,
			},
			"required": ["doctype", "filters"],
			"additionalProperties": False,
		},
		"strict": True,
	},
	{
		"name": "account_balance",
		"description": "The ledger balance of an account (a cash box, a wallet, a receivable or payable account) on a "
		"date, from ERPNext's own balance function. Use the account's full name as in the chart of accounts "
		"(list_records on Account to find it).",
		"input_schema": {
			"type": "object",
			"properties": {
				"account": {"type": "string"},
				"date": {"type": "string", "description": "YYYY-MM-DD; '' for today"},
			},
			"required": ["account", "date"],
			"additionalProperties": False,
		},
		"strict": True,
	},
]

SYSTEM = """You are the IMED ERP assistant for the owner of Mohamed Mamdouh group (Egypt; EGP): the IMED lecture halls, X Studio, the two 2Be Doctor libraries (Azarita and Mawasah), and the BA Plus app.

You answer questions about the business from the live ERP, through the tools only. You are read-only: you cannot create, change, delete, submit or post anything, and you never suggest you did. If asked to change something, say that it is done in the ERP's screens, not here.

How to answer:
- Read before answering. Start with dashboard_today for anything about today or this month; use run_report for periods and breakdowns; list_records and count_records for specific documents. Make several reads when a question needs them, and prefer a report's total to adding rows yourself.
- Pick the figure that answers the question asked, and say which one it is: revenue is invoiced revenue from the ledger; cash is what the ledger says is in a box; "due on XStudio bookings" is what XStudio bills less what it says was paid, and it is never posted here; a booking counted "held" is not cancelled and not a no-show. If two figures could answer, give the one asked and name the other in a few words.
- Zeros: the site may hold no accounting records yet. When a figure is zero and the tool shows no records behind it ("no records yet", "not configured", "not tracked"), say that it is missing data, not a result. Never present a missing figure as a zero result.
- Numbers: write amounts with thousands separators and two decimals, in EGP, and in words too when the user asked to have them read ("ألف ومية" style is fine in Arabic). Dates in day-month-year.
- Answer in the user's language (Arabic in Egyptian register when they write Arabic), briefly, the figure first, then one line on where it came from and the date it is as of. No tables longer than needed; no markdown headers.
- If the tools cannot answer (a permission refusal, a report that needs a filter you do not have), say exactly what is missing. Never guess a number."""


def user_context_line(context):
	return (
		f"Asking user: {context.get('full_name') or context.get('user')} ({context.get('user')}). "
		f"Today in Cairo: {nowdate()}. This month: {get_first_day(nowdate())} to {get_last_day(nowdate())}. "
		f"Company: {context.get('company') or 'Mohamed Mamdouh group'}. Language: {context.get('lang')}."
	)


# ---------------- the tools: read-only, as the asking user ----------------


def tool_dashboard_today():
	from imed_erp.imederp import owner_dashboard, owner_figures, owner_yesterday

	cards = {}
	for label, fn in (
		("Cash in the Cash Boxes", owner_figures.cash_in_boxes),
		("Revenue This Month", owner_figures.revenue_this_month),
		("Expenses This Month", owner_figures.expenses_this_month),
		("Net This Month", owner_figures.net_this_month),
		("Owed to Us", owner_figures.owed_to_us),
		("We Owe", owner_figures.we_owe),
		("Platform Fees This Month", owner_dashboard.platform_fees_this_month),
		("Collected from Doctors This Month", owner_dashboard.app_collections_this_month),
		("Cash Shortages This Month", owner_dashboard.cash_shortages_this_month),
		("Open Cash Discrepancies", owner_dashboard.cash_discrepancies_open),
		("Studio Bookings This Month", owner_dashboard.studio_bookings_this_month),
		("Studio Hours This Month", owner_dashboard.studio_hours_this_month),
		("Hall Bookings This Month", owner_dashboard.hall_bookings_this_month),
		("Unpaid on Bookings", owner_dashboard.unpaid_on_bookings_card),
		("Due on Studio Bookings (XStudio)", owner_dashboard.xstudio_due_this_month),
	):
		try:
			cards[label] = fn()["value"]
		except frappe.PermissionError:
			cards[label] = "not allowed for this user"
	band = owner_yesterday.get_yesterday()
	ledger_cards = ("Cash in the Cash Boxes", "Revenue This Month", "Expenses This Month", "Net This Month", "Owed to Us", "We Owe")
	if band.get("ledger_entries_all_time") == 0:
		for label in ledger_cards:
			if label in cards and not isinstance(cards[label], str):
				cards[label] = {"value": cards[label], "note": "no accounting record exists yet: this is missing data, not a result"}
	return {"cards": cards, "band": band}


def tool_run_report(report, filters):
	if report not in REPORTS:
		raise frappe.ValidationError(_("Report {0} is not one the assistant may run.").format(report))
	from frappe.desk.query_report import run

	result = run(report, filters=filters or {}, ignore_prepared_report=True)
	columns = [c.get("fieldname") or c.get("label") if isinstance(c, dict) else str(c) for c in result.get("columns") or []]
	rows = result.get("result") or []
	rows = [row if isinstance(row, dict) else dict(zip(columns, row)) for row in rows]
	return {"columns": columns, "rows": rows[:MAX_ROWS], "rows_total": len(rows), "truncated": len(rows) > MAX_ROWS}


def parse_filters(filters):
	"""The model's conditions as Frappe filters: [[field, operator, value], ...]."""
	if isinstance(filters, str):
		filters = json.loads(filters or "[]")
	if isinstance(filters, dict):
		return filters
	out = []
	for cond in filters or []:
		field, operator, value = cond["field"], cond["operator"], cond.get("value", "")
		if operator in ("in", "not in", "between") or (isinstance(value, str) and value[:1] in "[{"):
			try:
				value = json.loads(value)
			except (TypeError, ValueError):
				pass
		elif isinstance(value, str):
			try:
				value = int(value) if value.lstrip("-").isdigit() else (float(value) if value.replace(".", "", 1).lstrip("-").isdigit() else value)
			except ValueError:
				pass
		out.append([field, operator, value])
	return out


def tool_list_records(doctype, filters, fields, order_by, limit):
	if doctype not in DOCTYPES:
		raise frappe.ValidationError(_("The assistant may not read {0}.").format(doctype))
	meta = frappe.get_meta(doctype)
	fields = [f for f in (fields or []) if f == "name" or meta.get_field(f) or f in ("owner", "creation", "modified", "docstatus")]
	if not fields:
		fields = ["name"] + ([meta.title_field] if meta.title_field else [])
	rows = frappe.get_list(
		doctype,
		filters=parse_filters(filters),
		fields=fields,
		order_by=order_by or None,
		limit_page_length=min(cint(limit) or 50, MAX_ROWS),
	)  # as the current user: get_list applies permissions
	return {"rows": rows, "count": len(rows)}


def tool_count_records(doctype, filters):
	if doctype not in DOCTYPES:
		raise frappe.ValidationError(_("The assistant may not read {0}.").format(doctype))
	if not frappe.has_permission(doctype, "read"):
		raise frappe.PermissionError(_("Not allowed to read {0}.").format(doctype))
	return {"count": frappe.db.count(doctype, parse_filters(filters))}


def tool_account_balance(account, date):
	if not frappe.has_permission("GL Entry", "read"):
		raise frappe.PermissionError(_("Not allowed to read the ledger."))
	if not frappe.db.exists("Account", account):
		raise frappe.ValidationError(_("No account named {0}.").format(account))
	from erpnext.accounts.utils import get_balance_on

	day = getdate(date) if date else getdate(nowdate())
	return {"account": account, "date": str(day), "balance": flt(get_balance_on(account, date=day), 2)}


TOOL_FUNCTIONS = {
	"dashboard_today": lambda **kw: tool_dashboard_today(),
	"run_report": lambda **kw: tool_run_report(kw.get("report"), kw.get("filters")),
	"list_records": lambda **kw: tool_list_records(kw.get("doctype"), kw.get("filters"), kw.get("fields"), kw.get("order_by"), kw.get("limit")),
	"count_records": lambda **kw: tool_count_records(kw.get("doctype"), kw.get("filters")),
	"account_balance": lambda **kw: tool_account_balance(kw.get("account"), kw.get("date")),
}


def run_tool(name, arguments):
	"""The tool's result as JSON text, or an error the model can read. Every tool reads; a failure (a permission
	refusal, a wrong filter) is returned as is_error, never hidden. Whatever happens, nothing is written: the
	transaction is rolled back after each tool."""
	frappe.db.savepoint("assistant_tool")
	try:
		if name not in TOOL_FUNCTIONS:
			raise frappe.ValidationError(_("Unknown tool {0}.").format(name))
		result = TOOL_FUNCTIONS[name](**(arguments or {}))
		text = json.dumps(result, default=str, ensure_ascii=False)
		if len(text) > MAX_RESULT_CHARS:
			text = text[:MAX_RESULT_CHARS] + '... (truncated: ask for a narrower filter)"}'
		return text, False
	except Exception as e:
		frappe.clear_messages()
		return json.dumps({"error": str(getattr(e, "message", None) or e)[:500]}, ensure_ascii=False), True
	finally:
		frappe.db.rollback(save_point="assistant_tool")  # read-only by contract: nothing a tool may have touched survives


