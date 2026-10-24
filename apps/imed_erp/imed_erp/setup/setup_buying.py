# Buying (LIB-07, ACC-12): what the accountant needs to buy paper and materials from suppliers, cash or on
# credit, and to see what is owed to each supplier (ERPNext's Accounts Payable report).
#
# Run from bench console, after setup_core.py:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_buying.py").read(), {"frappe": frappe})
#
# Makes:
#   - the supplier group for paper and materials suppliers;
#   - the payment terms a purchase invoice is made on: cash (due the same day) or on credit (due in 30 days);
#   - Buying Settings: no purchase order or receipt required first. The library buys directly, and one
#     purchase invoice with "Update Stock" both receives the paper and records what is owed;
#   - the purchase invoice screen (public/js/purchase_invoice.js): Update Stock ticked on a new invoice,
#     and the unit shown next to the quantity in the items table.
#
# Idempotent: what exists is left as is. Safe to run again.

import frappe

SUPPLIER_GROUP = "موردي الورق والخامات"

# (name, days to pay). Each term is also its own one-line template, which is what an invoice picks.
PAYMENT_TERMS = [("نقدي", 0), ("آجل 30 يوم", 30)]
AFTER_INVOICE_DATE = "Day(s) after invoice date"

# Buying Settings field <- value.
BUYING_SETTINGS = {"po_required": "No", "pr_required": "No"}

# (doctype, field, property, value, type): Customize Form changes, kept as Property Setters.
PROPERTY_SETTERS = [
	("Purchase Invoice", "update_stock", "default", "1", "Text"),
	("Purchase Invoice Item", "uom", "in_list_view", "1", "Check"),
]


def ensure_supplier_group():
	if frappe.db.exists("Supplier Group", SUPPLIER_GROUP):
		print(f"exists Supplier Group {SUPPLIER_GROUP}")
		return
	frappe.get_doc(
		{"doctype": "Supplier Group", "supplier_group_name": SUPPLIER_GROUP, "parent_supplier_group": "All Supplier Groups"}
	).insert()
	print(f"create Supplier Group {SUPPLIER_GROUP}")


def ensure_payment_term(name, days):
	if frappe.db.exists("Payment Term", name):
		print(f"exists Payment Term {name}")
		return
	frappe.get_doc(
		{
			"doctype": "Payment Term",
			"payment_term_name": name,
			"invoice_portion": 100,
			"due_date_based_on": AFTER_INVOICE_DATE,
			"credit_days": days,
		}
	).insert()
	print(f"create Payment Term {name}: {days} day(s)")


def ensure_payment_terms_template(name, days):
	if frappe.db.exists("Payment Terms Template", name):
		print(f"exists Payment Terms Template {name}")
		return
	frappe.get_doc(
		{
			"doctype": "Payment Terms Template",
			"template_name": name,
			"terms": [
				{
					"payment_term": name,
					"invoice_portion": 100,
					"due_date_based_on": AFTER_INVOICE_DATE,
					"credit_days": days,
				}
			],
		}
	).insert()
	print(f"create Payment Terms Template {name}")


def ensure_buying_settings():
	settings = frappe.get_single("Buying Settings")
	diff = {field: value for field, value in BUYING_SETTINGS.items() if settings.get(field) != value}
	if not diff:
		print("exists Buying Settings: no purchase order or receipt required")
		return
	settings.update(diff)
	settings.save()
	print(f"update Buying Settings: {diff}")


def ensure_property_setter(doctype, field, prop, value, prop_type):
	current = frappe.db.get_value(
		"Property Setter", {"doc_type": doctype, "field_name": field, "property": prop}, "value"
	)
	if current == value:
		print(f"exists Property Setter {doctype}.{field} {prop} = {value}")
		return
	frappe.make_property_setter(
		{"doctype": doctype, "fieldname": field, "property": prop, "value": value, "property_type": prop_type},
		validate_fields_for_doctype=False,
	)
	print(f"update Property Setter {doctype}.{field} {prop} = {value}")


def run():
	if not frappe.db.exists("Supplier Group", "All Supplier Groups"):
		print("STOP   Supplier Group 'All Supplier Groups' not found. Run setup_core.py first.")
		return

	try:
		ensure_supplier_group()
		for name, days in PAYMENT_TERMS:
			ensure_payment_term(name, days)
			ensure_payment_terms_template(name, days)
		ensure_buying_settings()
		for spec in PROPERTY_SETTERS:
			ensure_property_setter(*spec)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		print("FAILED Rolled back; nothing was changed.")
		raise

	print("DONE   Buying setup finished.")


run()
