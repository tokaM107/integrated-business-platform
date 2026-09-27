import frappe

ABBR = "MMG"

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
    "is_hidden": 0,
    "sequence_id": 1,
    "content": "[]",
    "shortcuts": [
        {"type": "Report", "link_to": "Profit and Loss Statement", "label": "Profit per Business", "doc_view": "", "color": "Green"},
        {"type": "Report", "link_to": "Stock Balance", "label": "Stock & Paper", "doc_view": "", "color": "Blue"},
        {"type": "Report", "link_to": "General Ledger", "label": "Cash Movements", "doc_view": "", "color": "Grey"},
        {"type": "Report", "link_to": "Accounts Receivable", "label": "Who Owes Us", "doc_view": "", "color": "Orange"},
        {"type": "DocType", "link_to": "Doctor Agreement", "label": "Doctor Agreements", "color": "Purple"},
        {"type": "DocType", "link_to": "Book Edition", "label": "Book Editions", "color": "Purple"},
        {"type": "DocType", "link_to": "Printer Reading", "label": "Paper Counters", "color": "Cyan"},
    ],
    "links": [
        {"type": "Card Break", "label": "Daily Numbers", "link_count": 3, "onboard": 0},
        {"type": "Link", "label": "Sales Invoices", "link_type": "DocType", "link_to": "Sales Invoice", "onboard": 0},
        {"type": "Link", "label": "Payments", "link_type": "DocType", "link_to": "Payment Entry", "onboard": 0},
        {"type": "Link", "label": "Expenses", "link_type": "DocType", "link_to": "Journal Entry", "onboard": 0},
        {"type": "Card Break", "label": "Doctors", "link_count": 3, "onboard": 0},
        {"type": "Link", "label": "Agreements", "link_type": "DocType", "link_to": "Doctor Agreement", "onboard": 0},
        {"type": "Link", "label": "Editions", "link_type": "DocType", "link_to": "Book Edition", "onboard": 0},
        {"type": "Link", "label": "Doctor Ledger", "link_type": "DocType", "link_to": "Doctor Ledger Entry", "onboard": 0},
    ],
}).insert()

frappe.db.commit()
print("Workspace created:", ws.name)