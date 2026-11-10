# Something finished in a store (the owner, 10 Nov 2026): the branch asks, the owner approves, the accountant buys
# (imederp/material_issue.py, purchase requests).
#
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_purchase_requests
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp import material_issue

COMPANY = "Mohamed Mamdouh group"
SARA, OWNER, ACCOUNTANT = "sara@imed.local", "owner@imed.local", "accountant@imed.local"
STORE = "خامات الأزاريطة - MMG"
BRANCH = "مكتبة الأزاريطة - MMG"
SUPPLIER = "_Test Paper Supplier (purchase requests)"


class TestPurchaseRequests(IntegrationTestCase):
	def setUp(self):
		for user in (SARA, OWNER, ACCOUNTANT):
			if not frappe.db.exists("User", user):
				self.skipTest(f"{user} is not on this site (setup/setup_users.py)")
		frappe.set_user("Administrator")
		from imed_erp.setup.setup_accountant import give_rights

		give_rights()
		self.item = frappe.get_all("Item", filters={"is_stock_item": 1, "disabled": 0, "has_variants": 0, "has_serial_no": 0, "has_batch_no": 0}, pluck="name", limit=1)[0]
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": frappe.get_all("Supplier Group", pluck="name", limit=1)[0]}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def ask(self, qty=3):
		frappe.set_user(SARA)
		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": COMPANY,
				"transaction_date": today(),
				"schedule_date": today(),
				"set_warehouse": STORE,
				"items": [{"item_code": self.item, "qty": qty, "warehouse": STORE, "schedule_date": today(), "cost_center": BRANCH}],
			}
		).insert()
		return mr

	def test_the_branch_asks_the_owner_approves_the_accountant_buys(self):
		mr = self.ask()
		self.assertTrue(material_issue.is_purchase_request(mr))
		# Not submitted without the owner.
		self.assertRaisesRegex(frappe.ValidationError, "owner's approval", mr.submit)
		material_issue.request_approval(mr.name)
		self.assertEqual(frappe.db.get_value("Material Request", mr.name, "custom_approval_status"), "Pending Approval")

		# Neither the branch nor the accountant approves it.
		self.assertRaises(frappe.PermissionError, material_issue.approve, mr.name)
		frappe.set_user(ACCOUNTANT)
		self.assertRaises(frappe.PermissionError, material_issue.approve, mr.name)
		# Nor is it bought before the owner says so.
		self.assertRaises(frappe.ValidationError, material_issue.make_purchase_invoice, mr.name)

		frappe.set_user(OWNER)
		material_issue.approve(mr.name)
		mr.reload()
		self.assertEqual((mr.docstatus, mr.custom_approval_status, mr.custom_approved_by), (1, "Approved", OWNER))

		# The accountant sees it waiting, and buys it.
		frappe.set_user(ACCOUNTANT)
		from imed_erp.imederp.accountant_desk import waiting

		self.assertGreaterEqual({w["key"]: w["count"] for w in waiting()}["purchases"], 1)
		pi = frappe.get_doc(material_issue.make_purchase_invoice(mr.name))
		self.assertEqual((pi.update_stock, pi.items[0].warehouse, pi.items[0].material_request, flt(pi.items[0].qty)), (1, STORE, mr.name, 3))
		pi.supplier = SUPPLIER
		pi.posting_date = today()
		for row in pi.items:
			row.rate = 10
		pi.insert()
		pi.submit()
		mr.reload()
		self.assertEqual(flt(mr.per_received), 100)
		self.assertRaisesRegex(frappe.ValidationError, "has been bought", material_issue.make_purchase_invoice, mr.name)

	def test_the_owner_rejects_with_a_reason_and_the_request_is_closed(self):
		mr = self.ask()
		material_issue.request_approval(mr.name)
		frappe.set_user(OWNER)
		self.assertRaises(frappe.ValidationError, material_issue.reject, mr.name, "")
		material_issue.reject(mr.name, "عندنا منه في المواساة")
		self.assertEqual(frappe.db.get_value("Material Request", mr.name, ["docstatus", "custom_approval_status"]), (0, "Rejected"))

	def test_only_the_accountant_and_the_managers_buy(self):
		frappe.set_user(SARA)
		self.assertRaises(frappe.PermissionError, material_issue.make_purchase_invoice, "anything")

	def test_the_owners_own_request_needs_no_approval(self):
		frappe.set_user("Administrator")
		mr = frappe.new_doc("Material Request")
		mr.material_request_type = "Purchase"
		mr.owner = OWNER
		self.assertFalse(material_issue.is_purchase_request(mr))
		mr.owner = "Administrator"  # ERPNext's reorder job
		self.assertFalse(material_issue.is_purchase_request(mr))
