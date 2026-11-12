# The owner's "does the month's income cover the fixed expenses" (imederp/owner_cover.py, 12 Nov 2026).
#
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_owner_cover
import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp import owner_cover


class TestOwnerCover(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_colour_says_passed_covered_or_not(self):
		self.assertEqual(owner_cover.state(1200, 1000), "green")  # passed them: above 110%
		self.assertEqual(owner_cover.state(1100, 1000), "yellow")  # 110% is still "covers them, just"
		self.assertEqual(owner_cover.state(1000, 1000), "yellow")
		self.assertEqual(owner_cover.state(999, 1000), "red")  # does not cover them
		self.assertEqual(owner_cover.state(0, 0), "none")

	def test_seven_months_this_one_never_below_the_last_three(self):
		out = owner_cover.cover()
		months = out["months"]
		self.assertEqual(len(months), owner_cover.MONTHS_BACK + 1)
		self.assertTrue(months[-1].current and not any(m.current for m in months[:-1]))
		past = [m.fixed for m in months[:-1] if m.fixed > 0][-3:]
		if past:
			self.assertGreaterEqual(round(months[-1].fixed, 2), round(sum(past) / len(past), 2) - 0.01)
		for m in months:
			self.assertIn(m.state, ("green", "yellow", "red", "none"))

	def test_only_the_owner_sees_it(self):
		if frappe.db.exists("User", "accountant@imed.local"):
			frappe.set_user("accountant@imed.local")
			self.assertRaises(frappe.PermissionError, owner_cover.get_cover)
