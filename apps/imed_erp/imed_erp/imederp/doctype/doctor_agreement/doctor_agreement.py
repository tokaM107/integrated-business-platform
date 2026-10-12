# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# A doctor is a Customer in this group (CRM-01): one record for the person, whatever they buy or earn.
# setup/setup_core.py makes it.
DOCTOR_GROUP = "طبيب"


class DoctorAgreement(Document):
	def validate(self):
		self.validate_doctor()

	def validate_doctor(self):
		if frappe.db.get_value("Customer", self.doctor, "customer_group") != DOCTOR_GROUP:
			frappe.throw(
				_("{0} is not a doctor. Choose a customer in the {1} group, or move this customer to it.").format(
					self.doctor, DOCTOR_GROUP
				),
				title=_("Not a Doctor"),
			)
