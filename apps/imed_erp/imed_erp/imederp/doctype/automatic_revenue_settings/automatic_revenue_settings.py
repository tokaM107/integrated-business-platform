# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# Whether the studio's payments (XStudio) and the libraries' sales (their own sales system) are written to the
# ledger by themselves, and from which day (the user, 11 Nov 2026). Off until switched on: imederp/revenue_posting.py
# reads this and does the posting.

import frappe
from frappe import _
from frappe.model.document import Document


class AutomaticRevenueSettings(Document):
	def validate(self):
		for on, start, label in ((self.post_studio, self.studio_from, _("Studio")), (self.post_libraries, self.libraries_from, _("Libraries"))):
			if on and not start:
				frappe.throw(_("{0}: say from which day.").format(label))
