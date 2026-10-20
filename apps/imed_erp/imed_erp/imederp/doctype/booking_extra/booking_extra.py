# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# An extra a booking may add (STU-04, HAL-11): a microphone, lights. Priced by the Item Price of its service item
# (booking_pricing.py).

import frappe
from frappe import _
from frappe.model.document import Document


class BookingExtra(Document):
	def validate(self):
		if frappe.db.get_value("Item", self.item, "is_stock_item"):
			frappe.throw(_("{0} is a stock item. An extra is sold as a service.").format(self.item))
