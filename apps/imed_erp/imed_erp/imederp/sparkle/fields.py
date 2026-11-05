# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The field the Sparkle sync keeps on ERPNext's own Journal Entry: the Sparkle payment it posts, so each is posted
# once. Made on install and kept in step on every migrate (hooks.py).

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
	"Journal Entry": [
		{
			"fieldname": "sparkle_payment_id",
			"fieldtype": "Data",
			"label": "Sparkle Payment",
			"description": "The payment entry in Sparkle (the halls' booking site) this entry posts.",
			"insert_after": "user_remark",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"search_index": 1,
		}
	],
}


def make_custom_fields():
	"""after_install / after_migrate hook."""
	create_custom_fields(CUSTOM_FIELDS, update=True)
