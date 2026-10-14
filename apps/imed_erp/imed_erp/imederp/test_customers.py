# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# One customer per phone number (CRM-01, CRM-04; imederp/customers.py). Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_customers

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.customers import PHONE_KEY, normalize_phone

# A test module outside a doctype folder builds no "_Test ..." records; keep it here, not under a doctype.
SARA = "sara@imed.local"


class IntegrationTestCustomers(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		# Each test starts from the real customers only: the numbers are reused from test to test.
		frappe.db.rollback()

	def customer(self, name, mobile_no=None, user="Administrator"):
		frappe.set_user(user)
		try:
			return frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_type": "Individual",
					"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
					"territory": frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0],
					"mobile_no": mobile_no,
				}
			).insert()
		finally:
			frappe.set_user("Administrator")

	def test_every_spelling_of_an_egyptian_number_is_the_same_key(self):
		for typed in (
			"01012345678",
			"010 1234 5678",
			"010-1234-5678",
			"(010) 12345678",
			"+201012345678",
			"+20 10 1234 5678",
			"+20 010 1234 5678",
			"00201012345678",
			"201012345678",
			"1012345678",
			"٠١٠١٢٣٤٥٦٧٨",
			"۰۱۰۱۲۳۴۵۶۷۸",
		):
			self.assertEqual(normalize_phone(typed), "+201012345678", typed)

	def test_landlines_and_foreign_numbers(self):
		self.assertEqual(normalize_phone("03 4567890"), "+2034567890")
		self.assertEqual(normalize_phone("02 12345678"), "+20212345678")
		self.assertEqual(normalize_phone("+20 3 4567890"), "+2034567890")
		self.assertEqual(normalize_phone("+966 50 123 4567"), "+966501234567")
		self.assertEqual(normalize_phone("00966501234567"), "+966501234567")

	def test_blank_is_no_number(self):
		for blank in (None, "", "   "):
			self.assertIsNone(normalize_phone(blank))

	def test_what_is_not_a_phone_number_is_refused(self):
		for wrong in ("0101234567", "01312345678", "010123456789", "abc", "01012345678 ext 5", "+1 23", "966501234567", "+20+10"):
			self.assertRaises(frappe.ValidationError, normalize_phone, wrong)

	def test_a_customer_keeps_the_number_as_typed_and_gets_its_key(self):
		customer = self.customer("_Test Phone Customer A", "010 1234 5678")
		self.assertEqual(customer.get(PHONE_KEY), "+201012345678")
		self.assertEqual(frappe.db.get_value("Customer", customer.name, "mobile_no"), "010 1234 5678")
		contact = frappe.db.get_value("Customer", customer.name, "customer_primary_contact")
		self.assertEqual(frappe.db.get_value("Contact", contact, "mobile_no"), "010 1234 5678")

	def test_the_same_number_in_another_spelling_is_refused(self):
		first = self.customer("_Test Phone Customer A", "01012345678")
		for typed in ("+20 10 1234 5678", "00201012345678", "٠١٠١٢٣٤٥٦٧٨"):
			with self.assertRaisesRegex(frappe.DuplicateEntryError, first.name):
				self.customer("_Test Phone Customer B", typed)
		self.assertEqual(frappe.db.count("Customer", {"customer_name": "_Test Phone Customer B"}), 0)

	def test_a_branch_manager_is_refused_too(self):
		self.customer("_Test Phone Customer A", "01112345678")
		self.assertRaises(frappe.DuplicateEntryError, self.customer, "_Test Phone Customer B", "+201112345678", SARA)
		# ... and adds a customer with a new number.
		self.assertEqual(self.customer("_Test Phone Customer C", "01212345678", SARA).get(PHONE_KEY), "+201212345678")

	def test_customers_without_a_number_are_allowed(self):
		a = self.customer("_Test Phone Customer A")
		b = self.customer("_Test Phone Customer B", "  ")
		self.assertIsNone(frappe.db.get_value("Customer", a.name, PHONE_KEY))
		self.assertIsNone(frappe.db.get_value("Customer", b.name, PHONE_KEY))

	def test_saving_a_customer_again_is_not_a_duplicate_of_itself(self):
		customer = self.customer("_Test Phone Customer A", "01512345678")
		customer.reload()
		customer.custom_college = "طب الإسكندرية"
		customer.custom_academic_year = "الفرقة الثالثة"
		customer.save()
		self.assertEqual(customer.get(PHONE_KEY), "+201512345678")

	def test_a_number_changed_on_the_contact_is_checked_and_reaches_the_customer(self):
		self.customer("_Test Phone Customer A", "01012345678")
		b = self.customer("_Test Phone Customer B", "01112345678")
		contact = frappe.get_doc("Contact", frappe.db.get_value("Customer", b.name, "customer_primary_contact"))

		contact.phone_nos[0].phone = "+20 10 1234 5678"
		self.assertRaises(frappe.DuplicateEntryError, contact.save)

		contact.reload()
		contact.phone_nos[0].phone = "012 0000 1111"
		contact.save()
		self.assertEqual(
			frappe.db.get_value("Customer", b.name, ["mobile_no", PHONE_KEY]), ("012 0000 1111", "+201200001111")
		)

	def test_the_database_refuses_a_second_customer_with_the_key(self):
		"""What stops two people saving the same number at the same moment, after both passed the check."""
		a = self.customer("_Test Phone Customer A", "01012345678")
		b = self.customer("_Test Phone Customer B")
		frappe.db.savepoint("phone_key")
		with self.assertRaises(Exception) as refused:
			frappe.db.set_value("Customer", b.name, PHONE_KEY, a.get(PHONE_KEY))
		self.assertTrue(frappe.db.is_unique_key_violation(refused.exception))
		frappe.db.rollback(save_point="phone_key")

	def test_other_contacts_keep_any_number(self):
		"""A supplier's or a user's contact is not a customer's: its number is not checked or keyed."""
		contact = frappe.get_doc({"doctype": "Contact", "first_name": "_Test Not A Customer"})
		contact.add_phone("12345", is_primary_mobile_no=True)
		contact.insert()
		contact.phone_nos[0].phone = "+1 23"
		contact.save()

	def test_a_customer_saved_before_the_rule_can_still_be_edited(self):
		"""An old customer with an invalid number, or one another customer has, is listed by
		setup_customer_phones.py; editing its other fields is not refused."""
		a = self.customer("_Test Phone Customer A", "01012345678")
		for old_number in ("12345", "+20 10 1234 5678"):
			b = self.customer("_Test Phone Customer B")
			frappe.db.set_value("Customer", b.name, "mobile_no", old_number)
			b.reload()
			b.custom_college = "طب الإسكندرية"
			b.save()
			self.assertIsNone(frappe.db.get_value("Customer", b.name, PHONE_KEY))
			frappe.delete_doc("Customer", b.name)
		# ... and an old valid number nobody else has gets its key on the next save.
		c = self.customer("_Test Phone Customer C")
		frappe.db.set_value("Customer", c.name, "mobile_no", "011 2222 3333")
		c.reload()
		c.save()
		self.assertEqual(frappe.db.get_value("Customer", c.name, PHONE_KEY), "+201122223333")
		self.assertEqual(frappe.db.get_value("Customer", a.name, PHONE_KEY), "+201012345678")

	def test_messages_show_the_number_as_text(self):
		with self.assertRaises(frappe.ValidationError) as refused:
			normalize_phone("<img src=x onerror=alert(1)>")
		self.assertNotIn("<img", str(refused.exception))
