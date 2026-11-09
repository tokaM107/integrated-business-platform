# The accountant's screen (imederp/accountant_desk.py): it shows the company's money only to those who may read it,
# and counts what waits on the accountant through his own permissions.
#
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_accountant_desk
import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp import accountant_desk

ACCOUNTANT = "accountant@imed.local"


class TestAccountantDesk(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_screen_shows_the_money_and_what_waits_on_the_accountant(self):
		if not frappe.db.exists("User", ACCOUNTANT):
			self.skipTest("no accountant on this site (setup/setup_accountant.py)")
		frappe.set_user(ACCOUNTANT)
		self.assertTrue(accountant_desk.is_accountant_only())
		out = accountant_desk.overview()
		self.assertEqual([f["key"] for f in out["figures"]], ["cash", "revenue", "expenses", "owed_to_us", "we_owe"])
		waiting = {w["key"]: w for w in out["waiting"]}
		self.assertEqual(set(waiting), {"expenses", "handovers", "discrepancies", "closes", "weeks", "doctors"})
		self.assertTrue(all(isinstance(w["count"], int) for w in waiting.values()))

	def test_a_user_who_may_not_read_the_figures_is_refused(self):
		frappe.set_user("Guest")
		self.assertFalse(accountant_desk.is_accountant_only())
		self.assertRaises(frappe.PermissionError, accountant_desk.overview)
