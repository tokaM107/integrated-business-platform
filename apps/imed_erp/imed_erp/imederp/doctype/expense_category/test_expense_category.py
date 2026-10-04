# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.doctype.expense_category.test_expense_category

import frappe
from frappe.tests import IntegrationTestCase

from imed_erp.imederp.doctype.expense_category.expense_category import get_expense_account

IGNORE_TEST_RECORD_DEPENDENCIES = ["Account", "Expense Category"]


def make_category(name, parent=None, is_group=0, expense_account=None):
	return frappe.get_doc(
		{
			"doctype": "Expense Category",
			"expense_category_name": name,
			"parent_expense_category": parent,
			"is_group": is_group,
			"expense_account": expense_account,
		}
	).insert()


class IntegrationTestExpenseCategory(IntegrationTestCase):
	def test_tree_and_inherited_account(self):
		account, other = frappe.get_all(
			"Account", filters={"root_type": "Expense", "is_group": 0}, order_by="lft", limit=2, pluck="name"
		)
		root = make_category("_Test Cat Root", is_group=1, expense_account=account).name
		group = make_category("_Test Cat Group", root, is_group=1).name
		leaf = make_category("_Test Cat Leaf", group).name
		own = make_category("_Test Cat Own", group, expense_account=other).name

		self.assertEqual(set(frappe.db.get_descendants("Expense Category", root)), {group, leaf, own})
		self.assertEqual(get_expense_account(leaf), account, "A category without an account uses its nearest parent's")
		self.assertEqual(get_expense_account(own), other, "A category's own account wins over its parent's")

	def test_parent_must_be_group(self):
		leaf = make_category("_Test Cat Not Group").name
		self.assertRaises(frappe.ValidationError, make_category, "_Test Cat Child", leaf)

	def test_group_with_children_stays_a_group(self):
		group = make_category("_Test Cat Has Children", is_group=1)
		make_category("_Test Cat Its Child", group.name)
		group.is_group = 0
		self.assertRaises(frappe.ValidationError, group.save)

	def test_account_must_be_an_expense_account(self):
		income = frappe.get_all("Account", filters={"root_type": "Income", "is_group": 0}, limit=1, pluck="name")[0]
		self.assertRaises(frappe.ValidationError, make_category, "_Test Cat Income", expense_account=income)
