# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# What can be booked (HAL-01, STU-01): a hall, with how many it seats and its equipment, or one of the studio's
# services (smart board, reels, podcast, filming, location). Its price is the Item Price of the service item it is
# sold as, the price list only the owner changes (SEC-02); nothing is priced here. Bookings: booking.py.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

HALL = "Hall"


class BookingResource(Document):
	def validate(self):
		if frappe.db.get_value("Cost Center", self.cost_center, "is_group"):
			frappe.throw(_("Cost Center {0} is a group. Choose the business under it.").format(self.cost_center))
		if self.resource_type == HALL and cint(self.capacity) <= 0:
			frappe.throw(_("Enter how many people the hall seats."), title=_("Capacity Required"))
		if cint(self.capacity) < 0:
			frappe.throw(_("Capacity cannot be negative."))
		if self.item and frappe.db.get_value("Item", self.item, "is_stock_item"):
			frappe.throw(_("{0} is a stock item. A booking is sold as a service.").format(self.item))
