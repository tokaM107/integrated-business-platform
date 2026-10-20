# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A package of a resource (STU-05): hours of smart board at a special price, a number of reels, a podcast with its
# cameras. Priced like everything sold: by the Item Price of its service item (booking_pricing.py).

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BookingPackage(Document):
	def validate(self):
		if flt(self.hours) < 0:
			frappe.throw(_("Hours Included cannot be negative."))
		if self.charged != "Once":
			self.hours = 0
		if frappe.db.get_value("Item", self.item, "is_stock_item"):
			frappe.throw(_("{0} is a stock item. A package is sold as a service.").format(self.item))
