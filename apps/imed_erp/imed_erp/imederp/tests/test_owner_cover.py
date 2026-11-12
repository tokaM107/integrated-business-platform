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
		self.assertEqual(owner_cover.state(5000, 0), "none")  # no fixed expenses recorded: no colour, never green

	def test_the_fixed_expenses_are_found_by_name_word_or_category(self):
		names = {a.account_name for a in owner_cover.fixed_accounts()}
		for expected in ("الإيجار", "المرافق", "الرواتب والأجور"):
			if frappe.db.exists("Account", {"account_name": expected, "company": owner_cover.COMPANY}):
				self.assertIn(expected, names)
		self.assertFalse(any(n in ("الخامات والمستهلكات", "التسويق", "الصيانة") for n in names))

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

	def test_the_income_holds_what_the_studio_and_the_libraries_took_in_once(self):
		"""The ledger's income, and what is not posted to it yet from the studio and the libraries: never twice."""
		from frappe.utils import add_months, flt, get_first_day, getdate, nowdate

		from imed_erp.imederp import revenue_posting as rp

		today = getdate(nowdate())
		first = get_first_day(add_months(get_first_day(today), -owner_cover.MONTHS_BACK))
		ledger = sum(-v for v in owner_cover.by_month(first, today, root_type="Income").values())
		full = sum(owner_cover.income_by_month(first, today).values())
		posted = dict(
			frappe.db.sql(
				f"""select j.`{rp.KEY}`, sum(a.credit_in_account_currency - a.debit_in_account_currency)
				from `tabJournal Entry` j join `tabJournal Entry Account` a on a.parent = j.name
				join `tabAccount` acc on acc.name = a.account and acc.root_type = 'Income'
				where j.docstatus = 1 and ifnull(j.`{rp.KEY}`, '') != '' group by j.`{rp.KEY}`"""
			)
		)
		unposted = sum(
			flt(t["amount"]) - flt(posted.get(t["key"]))
			for t in rp.studio_targets(first) + rp.library_targets(first)
			if getdate(t["date"]) <= today
		)
		self.assertAlmostEqual(full, ledger + unposted, places=2)
