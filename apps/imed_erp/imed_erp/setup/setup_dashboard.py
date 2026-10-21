# Owner Dashboard: Number Cards, Dashboard Charts, the "Owner Dashboard" workspace, and the branding
# settings the IMED ERP theme relies on (app name, launcher icon style, Owner Dashboard icon).
# The workspace JSON in imederp/workspace/ references these cards and charts, but they
# live only in the database, so this script is what recreates them on a new site.
#
# Run from bench console (after setup_core.py):
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_dashboard.py").read(), {"frappe": frappe})
#
# Note: unlike the other setup scripts, this one deletes and recreates the cards, charts and workspace.

import frappe

COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"

# IMED ERP palette (see public/css/imed_theme.css): colour carries meaning, not decoration.
# Teal = income, amber = needs attention, slate = neutral counts.
TEAL, TEAL_LIGHT, AMBER, SLATE = "#0f766e", "#1d9386", "#b7791f", "#48565f"

# ---------------- Number Cards ----------------
# full=1 shows the exact amount (EGP 92,437.50) instead of "92.44 K"; it also avoids Frappe showing
# "EGP NaN" for a sum of zero (shorten_number(0) returns an empty string).
#
# The owner's request of 21 Oct 2026: the sidebar has every screen, the dashboard the money. First the money,
# worked out from the ledger (imederp/owner_figures.py, "Custom" cards), then the bookings' own figures.
money_cards = [
    dict(label="Cash in the Cash Boxes", method="cash_in_boxes", color=TEAL),
    dict(label="Revenue This Month", method="revenue_this_month", color=TEAL),
    dict(label="Expenses This Month", method="expenses_this_month", color=AMBER),
    dict(label="Net This Month", method="net_this_month", color=TEAL),
    dict(label="Owed to Us", method="owed_to_us", color=AMBER),
    dict(label="We Owe", method="we_owe", color=SLATE),
]
# The owner's own figures (5.1): the studio's bookings and hours and the halls' bookings. A booking is not
# submitted; a cancelled one or a no-show is left out.
booking_cards = [
    dict(label="Studio Bookings", doc="Booking",
         func="Count", field="", color=TEAL,
         filters=[["Booking", "cost_center", "=", "استوديو X - MMG"],
                  ["Booking", "status", "not in", ["Cancelled", "No Show"]]]),
    # Hours, not money: no currency, and the full number (a zero would otherwise show as NaN).
    dict(label="Studio Hours", doc="Booking",
         func="Sum", field="hours", color=TEAL, full=1, plain=1,
         filters=[["Booking", "cost_center", "=", "استوديو X - MMG"],
                  ["Booking", "status", "not in", ["Cancelled", "No Show"]]]),
    dict(label="Hall Bookings", doc="Booking",
         func="Count", field="", color=SLATE,
         filters=[["Booking", "cost_center", "=", "قاعات Imed - MMG"],
                  ["Booking", "status", "not in", ["Cancelled", "No Show"]]]),
    dict(label="Unpaid on Bookings", doc="Booking",
         func="Sum", field="outstanding_amount", color=AMBER, full=1,
         filters=[["Booking", "status", "not in", ["Cancelled", "No Show"]]]),
]
cards = money_cards + booking_cards
# Cards the dashboard showed before 21 Oct 2026: counts and all-time sums, not the owner's money.
RETIRED_CARDS = ["Total Sales", "Invoices Count", "Outstanding from Customers", "Total Purchases", "Customers",
                 "Doctor Agreements"]
for label in RETIRED_CARDS:
    if frappe.db.exists("Number Card", label):
        frappe.delete_doc("Number Card", label, force=1)
        print("removed card:", label)

created_cards = []
for c in cards:
    try:
        if frappe.db.exists("Number Card", c["label"]):
            frappe.delete_doc("Number Card", c["label"], force=1)
        values = {
            "doctype": "Number Card",
            "label": c["label"],
            "is_public": 1,
            "color": c["color"],
            "show_full_number": c.get("full", 0),
        }
        if c.get("method"):
            values.update({
                "type": "Custom",
                "method": f"imed_erp.imederp.owner_figures.{c['method']}",
                "currency": frappe.get_cached_value("Company", COMPANY, "default_currency"),
                "show_full_number": 1,
                "show_percentage_stats": 0,
            })
        else:
            values.update({
                "type": "Document Type",
                "document_type": c["doc"],
                "function": c["func"],
                "aggregate_function_based_on": c["field"],
                "filters_json": frappe.as_json(c["filters"]),
                "show_percentage_stats": 1,
                "stats_time_interval": "Monthly",
            })
        doc = frappe.get_doc(values).insert()
        if c.get("plain"):
            # Frappe fills an empty currency with the user's default on insert.
            frappe.db.set_value("Number Card", doc.name, "currency", None)
        c["real"] = doc.name
        created_cards.append(c)
        print("card:", doc.name)
    except Exception as e:
        print("SKIPPED card:", c["label"], "->", str(e)[:120])

frappe.db.commit()

# ---------------- Charts ----------------
# Only submitted sales: Frappe's charts count drafts too unless told otherwise.
charts = [
    # What is in each cash box now: the Cash Box Balances report's own chart.
    dict(label="Cash by Cash Box", report="Cash Box Balances", ctype="Bar", color=TEAL),
    dict(label="Revenue by Business", doc="Sales Invoice Item",
         based_on="cost_center", value_field="base_net_amount",
         ctype="Bar", color=TEAL_LIGHT, timespan=None, time_interval=None,
         parent_doc="Sales Invoice", filters=[["Sales Invoice Item", "docstatus", "=", 1]]),
    dict(label="Sales Trend", doc="Sales Invoice",
         based_on="posting_date", value_field="grand_total",
         ctype="Line", color=TEAL, timespan="Last Quarter", time_interval="Weekly",
         parent_doc=None, filters=[["Sales Invoice", "docstatus", "=", 1]]),
    dict(label="Stock Value by Warehouse", doc="Bin",
         based_on="warehouse", value_field="stock_value",
         ctype="Donut", color=TEAL, timespan=None, time_interval=None,
         parent_doc=None),
]

created_charts = []
for ch in charts:
    try:
        if frappe.db.exists("Dashboard Chart", ch["label"]):
            frappe.delete_doc("Dashboard Chart", ch["label"], force=1)
        d = {
            "doctype": "Dashboard Chart",
            "chart_name": ch["label"],
            "type": ch["ctype"],
            "color": ch["color"],
            "is_public": 1,
        }
        if ch.get("report"):
            d.update({"chart_type": "Report", "report_name": ch["report"], "use_report_chart": 1, "filters_json": "{}"})
        elif ch["ctype"] in ("Bar", "Donut"):
            d.update({
                "document_type": ch["doc"],
                "filters_json": frappe.as_json(ch.get("filters", [])),
                "chart_type": "Group By",
                "group_by_type": "Sum",
                "group_by_based_on": ch["based_on"],
                "aggregate_function_based_on": ch["value_field"],
                "number_of_groups": 8,
            })
        else:
            d.update({
                "document_type": ch["doc"],
                "filters_json": frappe.as_json(ch.get("filters", [])),
                "chart_type": "Sum",
                "based_on": ch["based_on"],
                "value_based_on": ch["value_field"],
                "timespan": ch["timespan"],
                "time_interval": ch["time_interval"],
            })
        if ch.get("parent_doc"):
            d["parent_document_type"] = ch["parent_doc"]

        doc = frappe.get_doc(d).insert()
        ch["real"] = doc.name
        created_charts.append(ch)
        print("chart:", doc.name)
    except Exception as e:
        print("SKIPPED chart:", ch["label"], "->", str(e)[:120])

frappe.db.commit()

# ---------------- Shortcuts ----------------
# The owner follows everything himself and mostly confirms (owner, 12 Oct 2026): what waits for him comes
# first, with its count. Every list and report is in the sidebar (ImedERP; owner, 21 Oct 2026), so the
# dashboard keeps only these. The section headers are written in Arabic (a workspace header is shown as
# written); the shortcut labels are translated.
def waiting(doctype, label, filters):
    return {
        "type": "DocType", "link_to": doctype, "label": label, "doc_view": "List", "color": "Orange",
        "stats_filter": frappe.as_json([[doctype, *f] for f in filters]), "format": "{} مستني",
    }


approvals = [
    waiting("Expense", "Expenses Waiting for Approval", [["approval_status", "=", "Pending Approval"], ["docstatus", "=", 0]]),
    waiting("Book Edition", "Editions to Approve", [["docstatus", "=", 0]]),
    waiting("Inter Business Transfer", "Transfers to Confirm", [["status", "=", "Sent"]]),
    # DOC-22: a charge on a doctor is applied only once the owner or the accountant approves (submits) it.
    waiting("Doctor Ledger Entry", "Doctor Charges to Approve", [["approval_status", "=", "Pending Approval"], ["docstatus", "=", 0]]),
]
shortcuts = approvals


def header(text):
    return [{"type": "header", "data": {"text": f"<span class=\"h4\"><b>{text}</b></span>", "col": 12}}]


def spacer():
    return [{"type": "spacer", "data": {"col": 12}}]


# ---------------- Content layout ----------------
# What waits for the owner, then the money, then the bookings, then the charts.
content = header("محتاج موافقتك")
content += [{"type": "shortcut", "data": {"shortcut_name": s["label"], "col": 6}} for s in approvals]

content += spacer() + header("الفلوس")
for c in created_cards:
    if c in money_cards:
        content.append({"type": "number_card", "data": {"number_card_name": c["real"], "col": 4}})
for ch in created_charts:
    if ch.get("report"):
        content.append({"type": "chart", "data": {"chart_name": ch["real"], "col": 12}})

content += spacer() + header("الحجوزات")
for c in created_cards:
    if c in booking_cards:
        content.append({"type": "number_card", "data": {"number_card_name": c["real"], "col": 3}})

other_charts = [ch for ch in created_charts if not ch.get("report")]
if other_charts:
    content += spacer() + header("الإيرادات والمخزون")
    for ch in other_charts:
        col = 12 if ch["ctype"] == "Line" else 6
        content.append({"type": "chart", "data": {"chart_name": ch["real"], "col": col}})

# ---------------- Workspace ----------------
if frappe.db.exists("Workspace", "Owner Dashboard"):
    frappe.delete_doc("Workspace", "Owner Dashboard", force=1)

ws = frappe.get_doc({
    "doctype": "Workspace",
    "name": "Owner Dashboard",
    "label": "Owner Dashboard",
    "title": "Owner Dashboard",
    "module": "ImedERP",
    "icon": "dashboard",
    "public": 1,
    # Screen 2 of the requirements is the owner's alone.
    "roles": [{"role": "Super Admin"}, {"role": "System Manager"}],
    "sequence_id": 1,
    "content": frappe.as_json(content),
    "number_cards": [{"number_card_name": c["real"], "label": c["label"]} for c in created_cards],
    "charts": [{"chart_name": ch["real"], "label": ch["label"]} for ch in created_charts],
    "shortcuts": shortcuts,
}).insert()

# The owner lands on his dashboard when he logs in.
for user in frappe.get_all("Has Role", filters={"role": "Super Admin", "parenttype": "User"}, pluck="parent"):
    if user != "Administrator" and frappe.db.get_value("User", user, "default_workspace") != ws.name:
        frappe.db.set_value("User", user, "default_workspace", ws.name)
        print(f"set    User {user}: opens on {ws.name}")

frappe.db.commit()
print("\nWorkspace ready:", ws.name)
print("Cards:", len(created_cards), "| Charts:", len(created_charts), "| Shortcuts:", len(shortcuts))

# ---------------- Branding ----------------
# Idempotent. The theme itself is CSS loaded by hooks.py; these are the settings it relies on.
if frappe.db.get_single_value("System Settings", "app_name") != "IMED ERP":
    frappe.db.set_single_value("System Settings", "app_name", "IMED ERP")
    print("set    System Settings.app_name = IMED ERP")
# The logo on the home screen and the login page comes from Navbar Settings (Frappe only falls back to
# the first apps' app_logo_url hooks, never to a third app's).
LOGO = "/assets/imed_erp/images/imed-mark.svg"
if frappe.db.get_single_value("Navbar Settings", "app_logo") != LOGO:
    frappe.db.set_single_value("Navbar Settings", "app_logo", LOGO)
    print(f"set    Navbar Settings.app_logo = {LOGO}")
# Subtle launcher icons (tinted tile, coloured glyph) read calmer than a wall of solid squares.
if frappe.db.get_single_value("Desktop Settings", "icon_style") != "Subtle":
    frappe.db.set_single_value("Desktop Settings", "icon_style", "Subtle")
    print("set    Desktop Settings.icon_style = Subtle")
# Linking the Owner Dashboard icon to this app makes Frappe use
# public/icons/desktop_icons/<style>/owner_dashboard.svg instead of a gray letter tile.
if frappe.db.exists("Desktop Icon", "Owner Dashboard") and frappe.db.get_value("Desktop Icon", "Owner Dashboard", "app") != "imed_erp":
    frappe.db.set_value("Desktop Icon", "Owner Dashboard", "app", "imed_erp")
    print("set    Desktop Icon Owner Dashboard.app = imed_erp")
frappe.db.commit()
frappe.clear_cache()
print("Branding ready.")
