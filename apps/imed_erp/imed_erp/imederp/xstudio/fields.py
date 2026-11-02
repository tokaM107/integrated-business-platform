# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The fields the XStudio sync keeps on ERPNext's own Customer (the app's own doctypes carry theirs in their JSON).
# Made on install and kept in step on every migrate (hooks.py).

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
	"Customer": [
		{
			"fieldname": "xstudio_section",
			"fieldtype": "Section Break",
			"label": "XStudio",
			"insert_after": "custom_academic_year",
			"collapsible": 1,
			"depends_on": "eval:doc.xstudio_customer_id",
		},
		{
			"fieldname": "xstudio_customer_id",
			"fieldtype": "Data",
			"label": "XStudio Customer ID",
			"description": "The customer's id in XStudio: one customer here per XStudio customer.",
			"insert_after": "xstudio_section",
			"unique": 1,
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
		},
		{
			"fieldname": "xstudio_needs_review",
			"fieldtype": "Check",
			"label": "XStudio Customer Without a Usable Phone",
			"description": "XStudio has no phone for this customer, or one that cannot be called: no number was made up. Add the right number when known.",
			"insert_after": "xstudio_customer_id",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
		},
		{
			"fieldname": "xstudio_last_synced_at",
			"fieldtype": "Datetime",
			"label": "Last Read From XStudio",
			"insert_after": "xstudio_needs_review",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
		},
	],
}


def make_custom_fields():
	"""after_install / after_migrate hook."""
	create_custom_fields(CUSTOM_FIELDS, update=True)
