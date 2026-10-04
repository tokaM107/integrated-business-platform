# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

# Which type a period's parent must be: Term > Round > Module.
PARENT_TYPE = {"Round": "Term", "Module": "Round"}


class AcademicPeriod(Document):
	def validate(self):
		if getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(f"End Date {self.end_date} is before Start Date {self.start_date}.")

		if self.period_type == "Term":
			# A term is the top of the tree.
			self.parent_period = None
			return

		expected = PARENT_TYPE[self.period_type]
		if not self.parent_period:
			frappe.throw(f"A {self.period_type} must belong to a {expected}. Set Parent Period.")
		parent = frappe.db.get_value(
			"Academic Period", self.parent_period, ["period_type", "start_date", "end_date"], as_dict=True
		)
		if parent.period_type != expected:
			frappe.throw(
				f"A {self.period_type} must belong to a {expected}, but {self.parent_period} is a {parent.period_type}."
			)
		if getdate(self.start_date) < getdate(parent.start_date) or getdate(self.end_date) > getdate(parent.end_date):
			frappe.throw(
				f"{self.period_name} ({self.start_date} to {self.end_date}) must fall inside "
				f"{self.parent_period} ({parent.start_date} to {parent.end_date})."
			)
