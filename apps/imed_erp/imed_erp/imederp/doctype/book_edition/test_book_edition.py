# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Edition pricing (DOC-24/25/28): price per copy = (manufacturing cost + owner share) per sheet x sheets
# + doctor share, rounded up to 5 EGP with the difference to the owner. Rolled back afterwards.
#
# Run:
#   bench --site frontend run-tests --doctype "Book Edition"

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

# Every doctype these tests link to is made here or already exists on the site. Without this Frappe builds
# ERPNext's "_Test ..." records for them and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Academic Period", "Book Edition", "Cost Center", "Customer", "Doctor Agreement"]

LIBRARY = "مكتبة المواساة - MMG"


def make_doctor(name="_Test Doctor"):
	if frappe.db.exists("Customer", name):
		return name
	return (
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": frappe.get_all("Customer Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"territory": frappe.get_all("Territory", filters={"is_group": 0}, limit=1, pluck="name")[0],
			}
		)
		.insert()
		.name
	)


def make_agreement(agreement_type, share_type="Fixed", share_value=0):
	# Named after agreement_name, so tests asking for the same terms share one.
	name = f"_Test {agreement_type} {share_type} {share_value}"
	if frappe.db.exists("Doctor Agreement", name):
		return name
	return (
		frappe.get_doc(
			{
				"doctype": "Doctor Agreement",
				"agreement_name": name,
				"doctor": make_doctor(),
				"agreement_type": agreement_type,
				"share_type": share_type,
				"share_value": share_value,
			}
		)
		.insert()
		.name
	)


# The paper price depends on what the library has received; these tests fix it, test_paper_stock.py reads it
# from a real purchase.
PAPER_COST = "imed_erp.imederp.doctype.book_edition.book_edition.get_paper_cost"


class IntegrationTestBookEdition(IntegrationTestCase):
	def make_edition(self, agreement, **values):
		return frappe.get_doc(
			{
				"doctype": "Book Edition",
				# Named after edition_name, so each test edition needs its own.
				"edition_name": f"_Test Edition {frappe.generate_hash(length=6)}",
				"agreement": agreement,
				"cost_center": LIBRARY,
				"pages": 200,
				"unit_cost": 0.06,
				"owner_share": 0.1,
				**values,
			}
		).insert()

	@patch(PAPER_COST, return_value=0.30)
	def test_price_is_per_copy_and_rounded_up_to_the_owner(self, _):
		# Paper 0.26 average + 0.04 waste = 0.30; + 0.06 ink and binding + 0.10 owner = 0.46 a sheet.
		# 0.46 x 200 sheets = 92, + 15 doctor's share = 107 -> sold at 110, 3 to the owner.
		edition = self.make_edition(make_agreement("Books", "Fixed", 15))
		self.assertEqual(edition.paper_cost, 0.30)
		self.assertEqual(edition.doctor_share, 15)
		self.assertEqual(edition.calculated_price, 107)
		self.assertEqual(edition.selling_price, 110)
		self.assertEqual(edition.rounding_diff, 3)

	@patch(PAPER_COST, return_value=0.30)
	def test_selling_price_cannot_cut_into_the_shares(self, _):
		agreement = make_agreement("Books", "Fixed", 15)
		self.assertRaises(frappe.ValidationError, self.make_edition, agreement, selling_price=100)
		self.assertEqual(self.make_edition(agreement, selling_price=120).rounding_diff, 13)

	@patch(PAPER_COST, return_value=0)
	def test_no_approval_without_a_paper_price(self, _):
		edition = self.make_edition(make_agreement("Books", "Fixed", 15))
		self.assertRaises(frappe.ValidationError, edition.submit)

	def test_edition_belongs_to_a_books_agreement(self):
		self.assertRaises(frappe.ValidationError, self.make_edition, make_agreement("App"))
