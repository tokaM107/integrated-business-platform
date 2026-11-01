# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# A hall's price by the length of the booking (the center's price list of 1 Nov 2026): one price for the first
# hour, one for a booking of up to two hours, and a price per hour after the second. One record per hall and
# price list (HAL-03: the customer's category decides the list), set by the owner or the accountant, never typed
# on a booking. Priced in booking_pricing.hall_tier_amount; a hall without a tier is priced by the hour from its
# service item's Item Price, as before.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class HallPriceTier(Document):
	def validate(self):
		if frappe.db.get_value("Booking Resource", self.resource, "resource_type") != "Hall":
			frappe.throw(_("{0} is not a hall: tiers price the halls only.").format(self.resource))
		for field in ("first_hour_rate", "two_hour_rate", "extra_hour_rate"):
			if flt(self.get(field)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(field))))
		if flt(self.two_hour_rate) < flt(self.first_hour_rate):
			frappe.throw(_("Two hours cannot cost less than the first hour."))
		if not frappe.db.get_value("Price List", self.price_list, "selling"):
			frappe.throw(_("{0} is not a selling price list.").format(self.price_list))
		filters = {"resource": self.resource, "price_list": self.price_list}
		if not self.is_new():
			filters["name"] = ["!=", self.name]
		other = frappe.db.get_value("Hall Price Tier", filters, "name")
		if other:
			frappe.throw(_("{0} already has a tier for {1}: {2}.").format(self.resource, self.price_list, other))
