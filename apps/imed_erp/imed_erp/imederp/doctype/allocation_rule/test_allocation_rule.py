# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Allocation rules (EXP-03/04): the shared premises' expenses are split between the halls and the studio.
# Uses the real cost centers, treasury and categories (setup_core.py, setup_expenses.py); everything made
# here is rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Allocation Rule"

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

# Every doctype the rule links to already exists on the site. Without this Frappe builds ERPNext's
# "_Test ..." records for them and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Allocation Rule",
	"Company",
	"Cost Center",
	"Cost Center Allocation",
]

ABBR = "MMG"
SHARED = f"مصروفات المقر المشتركة - {ABBR}"
HALLS = f"قاعات Imed - {ABBR}"
STUDIO = f"استوديو X - {ABBR}"
TREASURY = f"الخزينة الرئيسية - {ABBR}"
RECEIPT = "/files/_test_allocation_receipt.png"


class IntegrationTestAllocationRule(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Only the File record is needed: the expense checks that the receipt was uploaded, not its content.
		frappe.get_doc({"doctype": "File", "file_name": "receipt.png", "file_url": RECEIPT}).db_insert()

	def free_date(self):
		"""A day after every expense and rule already on the shared cost center, so a new rule is accepted."""
		last_expense = frappe.db.get_value(
			"Expense", {"activity": SHARED, "docstatus": 1}, "posting_date", order_by="posting_date desc"
		)
		last_rule = frappe.db.get_value(
			"Allocation Rule", {"main_cost_center": SHARED, "docstatus": 1}, "valid_from", order_by="valid_from desc"
		)
		dates = [getdate(today())] + [getdate(add_days(d, 1)) for d in (last_expense, last_rule) if d]
		return max(dates)

	def make_rule(self, shares, valid_from=None, submit=True):
		rule = frappe.get_doc(
			{
				"doctype": "Allocation Rule",
				"main_cost_center": SHARED,
				"valid_from": valid_from or self.free_date(),
				"businesses": [{"cost_center": c, "percentage": p} for c, p in shares],
			}
		).insert()
		if submit:
			rule.submit()
		return rule

	def post_expense(self, amount, posting_date):
		"""Submit an electricity bill on the shared cost center; returns its debit per business."""
		# ERPNext caches the allocation per request; each expense here stands for a request of its own.
		getattr(frappe.local, "request_cache", {}).clear()
		expense = frappe.get_doc(
			{
				"doctype": "Expense",
				"posting_date": posting_date,
				"activity": SHARED,
				"expense_category": "الكهرباء",
				"amount": amount,
				"treasury": TREASURY,
				"receipt": RECEIPT,
			}
		).insert()
		expense.submit()
		return self.split_of(expense)

	def split_of(self, expense):
		split = {}
		for row in frappe.get_all(
			"GL Entry",
			filters={"voucher_no": expense.journal_entry, "is_cancelled": 0},
			fields=["cost_center", "debit"],
		):
			split[row.cost_center] = split.get(row.cost_center, 0) + row.debit
		return {cost_center: debit for cost_center, debit in split.items() if debit}

	def test_electricity_is_split_by_itself(self):
		# The task's acceptance test.
		rule = self.make_rule([(HALLS, 60), (STUDIO, 40)])

		allocation = frappe.get_doc("Cost Center Allocation", rule.cost_center_allocation)
		self.assertEqual(allocation.docstatus, 1)
		self.assertEqual(str(allocation.valid_from), str(rule.valid_from))
		self.assertEqual({r.cost_center: r.percentage for r in allocation.allocation_percentages}, {HALLS: 60, STUDIO: 40})

		self.assertEqual(self.post_expense(10000, rule.valid_from), {HALLS: 6000, STUDIO: 4000})

	def test_bill_paid_in_two_parts(self):
		rule = self.make_rule([(HALLS, 60), (STUDIO, 40)])

		first = self.post_expense(6000, rule.valid_from)
		second = self.post_expense(4000, rule.valid_from)

		self.assertEqual(first, {HALLS: 3600, STUDIO: 2400})
		self.assertEqual(second, {HALLS: 2400, STUDIO: 1600})
		self.assertEqual(first[HALLS] + second[HALLS], 6000)
		self.assertEqual(first[STUDIO] + second[STUDIO], 4000)

	def test_new_rule_leaves_past_expenses_alone(self):
		old_rule = self.make_rule([(HALLS, 60), (STUDIO, 40)])
		before = self.post_expense(10000, old_rule.valid_from)

		new_rule = self.make_rule([(HALLS, 50), (STUDIO, 50)], valid_from=add_days(old_rule.valid_from, 1))
		after = self.post_expense(10000, new_rule.valid_from)

		self.assertEqual(after, {HALLS: 5000, STUDIO: 5000})
		self.assertEqual(before, {HALLS: 6000, STUDIO: 4000})

	def test_valid_from_must_be_after_the_last_expense(self):
		rule = self.make_rule([(HALLS, 60), (STUDIO, 40)])
		# Split, so its ledger entries are on the businesses; the expense itself still counts.
		expense_day = add_days(rule.valid_from, 3)
		self.post_expense(10000, expense_day)

		for day in (expense_day, add_days(expense_day, -1)):
			with self.subTest(day=day):
				self.assertRaises(
					frappe.ValidationError, self.make_rule, [(HALLS, 50), (STUDIO, 50)], valid_from=day, submit=False
				)
		self.make_rule([(HALLS, 50), (STUDIO, 50)], valid_from=add_days(expense_day, 1), submit=False)

	def test_valid_from_must_be_after_the_latest_rule(self):
		rule = self.make_rule([(HALLS, 60), (STUDIO, 40)])
		self.assertRaises(
			frappe.ValidationError, self.make_rule, [(HALLS, 50), (STUDIO, 50)], valid_from=rule.valid_from, submit=False
		)

	def test_cancelling_a_rule_brings_back_the_previous_one(self):
		previous = self.make_rule([(HALLS, 60), (STUDIO, 40)])
		rule = self.make_rule([(HALLS, 50), (STUDIO, 50)], valid_from=add_days(previous.valid_from, 1))
		rule.cancel()

		self.assertEqual(frappe.db.get_value("Cost Center Allocation", rule.cost_center_allocation, "docstatus"), 2)
		self.assertEqual(self.post_expense(10000, rule.valid_from), {HALLS: 6000, STUDIO: 4000})

	def test_rejects_invalid_rules(self):
		for title, shares in (
			("business twice", [(HALLS, 60), (HALLS, 40)]),
			("shared cost center in its own table", [(HALLS, 60), (SHARED, 40)]),
			("a group", [(f"سنتر Imed - {ABBR}", 60), (STUDIO, 40)]),
			("shares not adding up to 100", [(HALLS, 60), (STUDIO, 30)]),
		):
			with self.subTest(title):
				self.assertRaises(frappe.ValidationError, self.make_rule, shares, submit=False)
