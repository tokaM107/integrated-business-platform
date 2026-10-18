# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A printing machine in one of the libraries (PRN-01): Azarita has 1 Epson and 2 Riso, Mawasah 1 Epson and 3 Riso.
# Paper is issued to it (imederp/material_issue.py) and its counter is read (Printer Reading), so what it printed
# can be set against what was sold. Its ink cost per sheet comes from Printing Cost Settings for its type unless
# it is given for this machine.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

from imed_erp.imederp.doctype.printing_cost_settings.printing_cost_settings import get_machine_ink

# The cost center the libraries sit under; a machine works in one of them.
LIBRARIES = "مكتبات 2Be Doctor"


class PrintingMachine(Document):
	def validate(self):
		check_library(self.cost_center)
		company = frappe.db.get_value("Warehouse", self.warehouse, "company")
		if self.cost_center and frappe.db.get_value("Cost Center", self.cost_center, "company") != company:
			frappe.throw(_("Cost Center {0} and warehouse {1} belong to different companies.").format(self.cost_center, self.warehouse))
		self.set_ink()
		if self.last_maintenance and getdate(self.last_maintenance) > getdate(today()):
			frappe.throw(_("The last maintenance cannot be in the future."))

	def set_ink(self):
		# Left empty, or still the rate of the type it had before, it follows its type; a rate set for this
		# machine stays.
		before = self.get_doc_before_save()
		previous = get_machine_ink(before.machine_type) if before else None
		if self.ink_per_sheet in (None, "") or (before and self.has_value_changed("machine_type") and flt(self.ink_per_sheet) == flt(previous)):
			self.ink_per_sheet = get_machine_ink(self.machine_type)
		if flt(self.ink_per_sheet) < 0:
			frappe.throw(_("Ink Cost per Sheet cannot be negative."))


def check_library(cost_center):
	"""A machine, and its counter readings, belong to a library (a cost center under the libraries)."""
	if not cost_center:
		return  # Branch is mandatory; Frappe says so.
	if frappe.db.get_value("Cost Center", cost_center, "is_group"):
		frappe.throw(_("Cost Center {0} is a group. Choose a branch under it.").format(cost_center))
	abbr = frappe.get_cached_value("Company", frappe.db.get_value("Cost Center", cost_center, "company"), "abbr")
	if frappe.db.get_value("Cost Center", cost_center, "parent_cost_center") != f"{LIBRARIES} - {abbr}":
		frappe.throw(_("{0} is not a library. Printing machines work in a library.").format(cost_center), title=_("Not a Library"))


def serves_warehouse(machine, warehouse):
	"""True if `warehouse` is the machine's location or a warehouse under it."""
	location = frappe.db.get_value("Printing Machine", machine, "warehouse")
	if not location or not warehouse:
		return False
	if warehouse == location:
		return True
	return warehouse in frappe.db.get_descendants("Warehouse", location)
