# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Edition pricing (DOC-24/25, owner's decisions of 8 Oct 2026): price per copy = (paper + ink + overheads +
# profit) per sheet x sheets + binding + optional marketing + the doctor's amount, not rounded; a price set
# by hand, higher or lower, is kept. Rolled back afterwards.
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
				"pages": 210,
				"ink_cost": 0.10,
				"overhead_cost": 0.05,
				"owner_share": 0.25,
				"binding_cost": 20,
				**values,
			}
		).insert()

	@patch(PAPER_COST, return_value=0.30)
	def test_price_is_per_copy_with_no_rounding(self, _):
		# Paper 0.26 average + 0.04 waste = 0.30; + 0.10 ink + 0.05 overheads + 0.25 profit = 0.70 a sheet.
		# 0.70 x 210 sheets = 147, + 20 binding + 80 the doctor asked for = 247, sold at 247.
		edition = self.make_edition(make_agreement("Books", "Fixed", 80))
		self.assertEqual(edition.paper_cost, 0.30)
		self.assertEqual(edition.doctor_share, 80)
		self.assertEqual(edition.calculated_price, 247)
		self.assertEqual(edition.selling_price, 247)
		self.assertEqual(edition.rounding_diff, 0)

	@patch(PAPER_COST, return_value=0.30)
	def test_marketing_is_optional_and_added_per_copy(self, _):
		edition = self.make_edition(make_agreement("Books", "Fixed", 80), marketing_cost=10)
		self.assertEqual(edition.calculated_price, 257)
		self.assertEqual(edition.selling_price, 257)

	@patch(PAPER_COST, return_value=0.30)
	def test_rates_come_from_the_settings_and_stay_once_submitted(self, _):
		settings = frappe.get_single("Printing Cost Settings")
		settings.update({"ink_per_sheet": 0.08, "overheads_per_sheet": 0.06, "profit_per_sheet": 0.20, "binding_per_copy": 25})
		settings.save()
		edition = frappe.get_doc(
			{
				"doctype": "Book Edition",
				"edition_name": f"_Test Edition {frappe.generate_hash(length=6)}",
				"agreement": make_agreement("Books", "Fixed", 80),
				"cost_center": LIBRARY,
				"pages": 100,
			}
		).insert()
		self.assertEqual(
			(edition.ink_cost, edition.overhead_cost, edition.owner_share, edition.binding_cost), (0.08, 0.06, 0.20, 25)
		)
		edition.submit()

		# A later price change on the settings leaves the submitted edition as it was approved.
		settings.ink_per_sheet = 0.15
		settings.save()
		edition.reload()
		self.assertEqual(edition.ink_cost, 0.08)

	def test_settings_rates_cannot_be_negative(self):
		settings = frappe.get_single("Printing Cost Settings")
		settings.waste_per_sheet = -0.01
		self.assertRaises(frappe.ValidationError, settings.save)

	@patch(PAPER_COST, return_value=0.30)
	def test_price_set_by_hand_higher_or_lower(self, _):
		agreement = make_agreement("Books", "Fixed", 80)
		# Higher: 13 more for the library.
		self.assertEqual(self.make_edition(agreement, selling_price=260).rounding_diff, 13)
		# Lower, to sell more: 7 less for the library; the doctor's 80 stays.
		lower = self.make_edition(agreement, selling_price=240)
		self.assertEqual((lower.rounding_diff, lower.doctor_share), (-7, 80))
		# Even below cost (0.45 x 210 + 20 + 80 = 194.5) it is saved, with a warning.
		self.assertEqual(self.make_edition(agreement, selling_price=180).selling_price, 180)

	@patch(PAPER_COST, return_value=0)
	def test_no_approval_without_a_paper_price(self, _):
		edition = self.make_edition(make_agreement("Books", "Fixed", 80))
		self.assertRaises(frappe.ValidationError, edition.submit)

	def test_edition_belongs_to_a_books_agreement(self):
		self.assertRaises(frappe.ValidationError, self.make_edition, make_agreement("App"))

	@patch(PAPER_COST, return_value=0.30)
	def test_edition_belongs_to_a_library(self, _):
		agreement = make_agreement("Books", "Fixed", 80)
		self.assertRaises(frappe.ValidationError, self.make_edition, agreement, cost_center="قاعات Imed - MMG")

	@patch(PAPER_COST, return_value=0.30)
	def test_percentage_agreement_warns_that_the_doctors_amount_is_missing(self, _):
		agreement = make_agreement("Books", "Percentage", 10)
		frappe.clear_messages()
		edition = self.make_edition(agreement)
		self.assertFalse(edition.doctor_share)
		self.assertIn(agreement, " ".join(str(m) for m in frappe.get_message_log()))

		# Once the amount is typed in, there is nothing to warn about.
		frappe.clear_messages()
		self.make_edition(agreement, doctor_share=80)
		self.assertNotIn(agreement, " ".join(str(m) for m in frappe.get_message_log()))

	@patch(PAPER_COST, return_value=0.30)
	def test_editing_a_draft_updates_its_price(self, _):
		edition = self.make_edition(make_agreement("Books", "Fixed", 80))
		self.assertEqual(edition.selling_price, 247)
		edition.pages = 220
		edition.save()
		# 0.70 x 220 = 154, + 20 + 80 = 254.
		self.assertEqual((edition.calculated_price, edition.selling_price, edition.rounding_diff), (254, 254, 0))

	@patch(PAPER_COST, return_value=0.30)
	def test_price_set_by_hand_is_kept_when_the_draft_changes(self, _):
		edition = self.make_edition(make_agreement("Books", "Fixed", 80), selling_price=230)
		edition.pages = 220
		edition.save()
		self.assertEqual((edition.calculated_price, edition.selling_price), (254, 230))

	@patch(PAPER_COST, return_value=0.30)
	def test_one_books_profit_does_not_change_another(self, _):
		agreement = make_agreement("Books", "Fixed", 80)
		cheaper = self.make_edition(agreement, owner_share=0.15)
		other = self.make_edition(agreement)
		self.assertEqual((cheaper.owner_share, other.owner_share), (0.15, 0.25))
		self.assertEqual(frappe.db.get_single_value("Printing Cost Settings", "profit_per_sheet") or 0.25, 0.25)
