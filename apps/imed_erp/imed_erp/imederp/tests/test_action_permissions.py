# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The server actions behind the buttons whose visibility changed on 2 Nov 2026 (and the owner's own ones), called
# directly as each kind of user, as an API request would: a hidden button is never the protection. Each action
# checks the role before it reads the document, so a name that does not exist tells the two answers apart: a
# refused user gets PermissionError, an allowed one gets "not found". Nothing is written.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_action_permissions

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.app_payment.app_payment import cancel_payment
from imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy import approve_recovery, withdraw_recovery, write_off
from imed_erp.imederp.doctype.studio_hour_package.studio_hour_package import cancel_package
from imed_erp.imederp.doctype.treasury_close.treasury_close import reopen

OWNER, ACCOUNTANT, BRANCH_MANAGER, STAFF = "owner@imed.local", "accountant@imed.local", "sara@imed.local", "hr@imed.local"
MISSING = "_no_such_record_"

# action -> the users the server lets through (today's policy, unchanged here)
MATRIX = {
	"Reopen a daily close": (lambda: reopen(MISSING, "test"), {OWNER, ACCOUNTANT}),
	"Cancel a studio package": (lambda: cancel_package(MISSING, "test"), {OWNER, ACCOUNTANT}),
	"Cancel an App Payment": (lambda: cancel_payment(MISSING, "test"), {OWNER, ACCOUNTANT}),
	"Write off a shortage": (lambda: write_off(MISSING, "test"), {OWNER, ACCOUNTANT}),
	"Withdraw an approved recovery": (lambda: withdraw_recovery(MISSING, "test"), {OWNER, ACCOUNTANT}),
	"Approve a recovery": (lambda: approve_recovery(MISSING), {OWNER}),
}


class IntegrationTestActionPermissions(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.clear_messages()

	def test_each_action_answers_each_user_as_the_matrix_says(self):
		for action, (call, allowed) in MATRIX.items():
			for user in (OWNER, ACCOUNTANT, BRANCH_MANAGER, STAFF):
				with self.subTest(action=action, user=user):
					frappe.set_user(user)
					try:
						call()
					except frappe.PermissionError:
						self.assertNotIn(user, allowed, f"{user} was refused {action}")
					except frappe.DoesNotExistError:
						self.assertIn(user, allowed, f"{user} got past the role check of {action}")
					else:
						self.fail(f"{action} did something for {user} with a record that does not exist")
					finally:
						frappe.set_user("Administrator")
						frappe.clear_messages()
