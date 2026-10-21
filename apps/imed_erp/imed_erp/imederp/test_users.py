# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# CORE-07: a user is disabled, never deleted, even by the owner. Rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_users

import frappe
from frappe.tests import IntegrationTestCase


class IntegrationTestUsers(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("users_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="users_test")

	def make_user(self):
		return frappe.get_doc(
			{"doctype": "User", "email": f"_test-core07-{frappe.generate_hash(length=5)}@imed.local", "first_name": "_Test", "send_welcome_email": 0}
		).insert(ignore_permissions=True)

	def test_core07_the_owner_disables_a_user_but_does_not_delete_one(self):
		user = self.make_user()
		frappe.set_user("owner@imed.local")
		self.assertRaisesRegex(frappe.PermissionError, "disable the account", frappe.delete_doc, "User", user.name)
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("User", user.name))
		frappe.db.set_value("User", user.name, "enabled", 0)

	def test_core07_the_developers_may_remove_an_account_made_by_mistake(self):
		user = self.make_user()
		frappe.delete_doc("User", user.name)
		self.assertFalse(frappe.db.exists("User", user.name))
