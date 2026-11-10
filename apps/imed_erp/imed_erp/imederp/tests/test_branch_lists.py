# A branch manager lists their own branch's journal and stock entries only (imederp/branch_lists.py): the API probe
# of 10 Nov 2026 found Azarita's manager listing the halls' journal entry and Mawasah's stock receipts.
#
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_branch_lists
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from imed_erp.imederp import branch_lists

COMPANY = "Mohamed Mamdouh group"
SARA = "sara@imed.local"  # Azarita's manager: its cost center and its stores only


def account(**filters):
	return frappe.get_all("Account", filters={"company": COMPANY, "is_group": 0, **filters}, pluck="name", limit=1)[0]


class TestBranchLists(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("User", SARA):
			self.skipTest("no Azarita manager on this site (setup/setup_users.py)")

	def tearDown(self):
		frappe.set_user("Administrator")

	def journal(self, cost_center):
		return frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": COMPANY,
				"posting_date": today(),
				"accounts": [
					{"account": account(root_type="Expense"), "debit_in_account_currency": 7, "cost_center": cost_center},
					{"account": account(account_type="Cash"), "credit_in_account_currency": 7, "cost_center": cost_center},
				],
			}
		).insert(ignore_permissions=True)

	def test_a_manager_lists_her_own_branchs_journal_entries_only(self):
		halls = self.journal("قاعات Imed - MMG").name
		azarita = self.journal("مكتبة الأزاريطة - MMG").name
		frappe.set_user(SARA)
		listed = frappe.get_list("Journal Entry", pluck="name", limit_page_length=0)
		self.assertIn(azarita, listed)
		self.assertNotIn(halls, listed)

	def test_a_manager_lists_the_stock_entries_of_her_stores_only(self):
		stores = branch_lists.my_warehouses(SARA)
		self.assertTrue(stores and all("الأزاريطة" in s for s in stores))
		condition = branch_lists.stock_entry_conditions(SARA)
		self.assertIn("tabStock Entry Detail", condition)
		self.assertNotIn("المواساة", condition)

	def test_the_owner_and_the_accountant_keep_every_entry(self):
		self.assertEqual(branch_lists.journal_entry_conditions("Administrator"), "")
		if frappe.db.exists("User", "accountant@imed.local"):
			self.assertEqual(branch_lists.journal_entry_conditions("accountant@imed.local"), "")
			self.assertEqual(branch_lists.stock_entry_conditions("accountant@imed.local"), "")
