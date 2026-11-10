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
		self.assertEqual(set(out["today"]), {"cash", "came", "went", "not_closed", "closable"})
		self.assertEqual([o["key"] for o in out["outside"]], ["customers", "suppliers", "doctors"])
		self.assertEqual(round(out["today"]["cash"], 2), round(sum(s["balance"] for s in out["safes"]), 2))
		self.assertFalse(any("محفظة" in s["label"] for s in out["safes"]))  # safes only, no wallet
		self.assertEqual(round(out["month"]["total"]["net"], 2), round(sum(r["net"] for r in out["month"]["rows"]), 2))
		waiting = {w["key"]: w for w in out["waiting"]}
		self.assertEqual(set(waiting), {"expenses", "handovers", "discrepancies", "closes", "weeks", "doctors", "purchases"})
		self.assertTrue(all(isinstance(w["count"], int) for w in waiting.values()))

	def test_a_user_who_may_not_read_the_figures_is_refused(self):
		frappe.set_user("Guest")
		self.assertFalse(accountant_desk.is_accountant_only())
		self.assertRaises(frappe.PermissionError, accountant_desk.overview)

	def test_what_is_not_the_accountants_is_refused_to_him_only(self):
		from imed_erp import hooks

		self.assertEqual(set(hooks._NOT_THE_ACCOUNTANTS), set(accountant_desk.NOT_HIS))
		if not frappe.db.exists("User", ACCOUNTANT):
			self.skipTest("no accountant on this site")
		self.assertFalse(frappe.has_permission("Printing Machine", "read", doc=frappe.new_doc("Printing Machine"), user=ACCOUNTANT))
		self.assertEqual(accountant_desk.query_conditions(ACCOUNTANT), "1=0")
		self.assertEqual(accountant_desk.query_conditions("Administrator"), "")
		frappe.set_user(ACCOUNTANT)
		self.assertEqual(frappe.get_list("Daily Counter Reading", limit_page_length=0), [])
		self.assertTrue(frappe.has_permission("Expense", "read"))  # his own work untouched
