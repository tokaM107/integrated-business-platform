# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

# Which type a period's parent must be: Term > Round > Module.
PARENT_TYPE = {"Round": "Term", "Module": "Round"}


class AcademicPeriod(Document):
	def validate(self):
		if getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(_("End Date {0} is before Start Date {1}.").format(self.end_date, self.start_date))

		if self.period_type == "Term":
			# A term is the top of the tree.
			self.parent_period = None
			return

		expected = PARENT_TYPE[self.period_type]
		if not self.parent_period:
			frappe.throw(_("A {0} must belong to a {1}. Set Parent Period.").format(_(self.period_type), _(expected)))
		parent = frappe.db.get_value(
			"Academic Period", self.parent_period, ["period_type", "start_date", "end_date"], as_dict=True
		)
		if parent.period_type != expected:
			frappe.throw(
				_("A {0} must belong to a {1}, but {2} is a {3}.").format(
					_(self.period_type), _(expected), self.parent_period, _(parent.period_type)
				)
			)
		if getdate(self.start_date) < getdate(parent.start_date) or getdate(self.end_date) > getdate(parent.end_date):
			frappe.throw(
				_("{0} ({1} to {2}) must fall inside {3} ({4} to {5}).").format(
					self.period_name, self.start_date, self.end_date, self.parent_period, parent.start_date, parent.end_date
				)
			)
