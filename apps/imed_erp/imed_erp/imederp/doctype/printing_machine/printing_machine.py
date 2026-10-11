# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A printing machine that paper is issued to (imederp/material_issue.py), so the paper it received can
# later be compared with its counter readings.

import frappe
from frappe import _
from frappe.model.document import Document


class PrintingMachine(Document):
	def validate(self):
		company = frappe.db.get_value("Warehouse", self.warehouse, "company")
		if self.cost_center:
			if frappe.db.get_value("Cost Center", self.cost_center, "is_group"):
				frappe.throw(_("Cost Center {0} is a group. Choose a branch under it.").format(self.cost_center))
			if frappe.db.get_value("Cost Center", self.cost_center, "company") != company:
				frappe.throw(_("Cost Center {0} and warehouse {1} belong to different companies.").format(self.cost_center, self.warehouse))


def serves_warehouse(machine, warehouse):
	"""True if `warehouse` is the machine's location or a warehouse under it."""
	location = frappe.db.get_value("Printing Machine", machine, "warehouse")
	if not location or not warehouse:
		return False
	if warehouse == location:
		return True
	return warehouse in frappe.db.get_descendants("Warehouse", location)
