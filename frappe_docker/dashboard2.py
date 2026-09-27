import frappe

COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"

# ---------------- Number Cards ----------------
cards = [
    dict(label="Total Sales", doc="Sales Invoice",
         func="Sum", field="grand_total", color="#22c55e",
         filters=[["Sales Invoice", "docstatus", "=", 1]]),
    dict(label="Invoices Count", doc="Sales Invoice",
         func="Count", field="", color="#3b82f6",
         filters=[["Sales Invoice", "docstatus", "=", 1]]),
    dict(label="Outstanding from Customers", doc="Sales Invoice",
         func="Sum", field="outstanding_amount", color="#f97316",
         filters=[["Sales Invoice", "docstatus", "=", 1]]),
    dict(label="Total Purchases", doc="Purchase Receipt",
         func="Sum", field="grand_total", color="#a855f7",
         filters=[["Purchase Receipt", "docstatus", "=", 1]]),
    dict(label="Customers", doc="Customer",
         func="Count", field="", color="#06b6d4", filters=[]),
    dict(label="Doctor Agreements", doc="Doctor Agreement",
         func="Count", field="", color="#ec4899", filters=[]),
]

created_cards = []
for c in cards:
    try:
        if frappe.db.exists("Number Card", c["label"]):
            frappe.delete_doc("Number Card", c["label"], force=1)
        doc = frappe.get_doc({
            "doctype": "Number Card",
            "label": c["label"],
            "type": "Document Type",
            "document_type": c["doc"],
            "function": c["func"],
            "aggregate_function_based_on": c["field"],
            "filters_json": frappe.as_json(c["filters"]),
            "is_public": 1,
            "show_percentage_stats": 1,
            "stats_time_interval": "Monthly",
            "color": c["color"],
        }).insert()
        c["real"] = doc.name
        created_cards.append(c)
        print("card:", doc.name)
    except Exception as e:
        print("SKIPPED card:", c["label"], "->", str(e)[:120])

frappe.db.commit()

# ---------------- Charts ----------------
charts = [
    dict(label="Sales Trend", doc="Sales Invoice",
         based_on="posting_date", value_field="grand_total",
         ctype="Line", color="#22c55e", timespan="Last Quarter", time_interval="Weekly",
         parent_doc=None),
    dict(label="Revenue by Business", doc="Sales Invoice Item",
         based_on="cost_center", value_field="base_net_amount",
         ctype="Bar", color="#3b82f6", timespan=None, time_interval=None,
         parent_doc="Sales Invoice"),
    dict(label="Stock Value by Warehouse", doc="Bin",
         based_on="warehouse", value_field="stock_value",
         ctype="Donut", color="#a855f7", timespan=None, time_interval=None,
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
            "document_type": ch["doc"],
            "type": ch["ctype"],
            "color": ch["color"],
            "is_public": 1,
            "filters_json": "[]",
        }
        if ch["ctype"] in ("Bar", "Donut"):
            d.update({
                "chart_type": "Group By",
                "group_by_type": "Sum",
                "group_by_based_on": ch["based_on"],
                "aggregate_function_based_on": ch["value_field"],
                "number_of_groups": 8,
            })
        else:
            d.update({
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
shortcuts = [
    {"type": "Report", "link_to": "Profit and Loss Statement", "label": "Profit per Business", "color": "Green", "doc_view": ""},
    {"type": "Report", "link_to": "Stock Balance", "label": "Stock & Paper", "color": "Blue", "doc_view": ""},
    {"type": "Report", "link_to": "General Ledger", "label": "Cash Movements", "color": "Grey", "doc_view": ""},
    {"type": "Report", "link_to": "Accounts Receivable", "label": "Who Owes Us", "color": "Orange", "doc_view": ""},
]
for dt, lbl, col in [("Doctor Agreement", "Doctor Agreements", "Purple"),
                     ("Book Edition", "Book Editions", "Purple"),
                     ("Printer Reading", "Paper Counters", "Cyan"),
                     ("App Subscription", "App Subscriptions", "Pink")]:
    if frappe.db.exists("DocType", dt):
        shortcuts.append({"type": "DocType", "link_to": dt, "label": lbl, "color": col})

# ---------------- Content layout ----------------
content = [{"type": "header", "data": {"text": "<span>Key Numbers</span>", "col": 12}}]
for c in created_cards:
    content.append({"type": "number_card", "data": {"number_card_name": c["real"], "col": 4}})

if created_charts:
    content += [
        {"type": "spacer", "data": {"col": 12}},
        {"type": "header", "data": {"text": "<span>Charts</span>", "col": 12}},
    ]
    for ch in created_charts:
        col = 12 if ch["ctype"] == "Line" else 6
        content.append({"type": "chart", "data": {"chart_name": ch["real"], "col": col}})

content += [
    {"type": "spacer", "data": {"col": 12}},
    {"type": "header", "data": {"text": "<span>Reports & Modules</span>", "col": 12}},
]
for s in shortcuts:
    content.append({"type": "shortcut", "data": {"shortcut_name": s["label"], "col": 3}})

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
    "sequence_id": 1,
    "content": frappe.as_json(content),
    "number_cards": [{"number_card_name": c["real"], "label": c["label"]} for c in created_cards],
    "charts": [{"chart_name": ch["real"], "label": ch["label"]} for ch in created_charts],
    "shortcuts": shortcuts,
}).insert()

frappe.db.commit()
print("\nWorkspace ready:", ws.name)
print("Cards:", len(created_cards), "| Charts:", len(created_charts), "| Shortcuts:", len(shortcuts))