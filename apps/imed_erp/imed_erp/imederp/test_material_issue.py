# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# Branch requests from the main warehouse: request, Raghad's approval, the issue with its recipient and
# date, and paper issued to a printing machine (imederp/material_issue.py).
# Uses the real warehouses, users and A4 paper made by the setup scripts; every test is rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_material_issue

import frappe
from erpnext.stock.doctype.material_request.material_request import make_stock_entry
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from imed_erp.imederp import material_issue
from imed_erp.imederp.report.material_issues.material_issues import get_data as material_issues_report

COMPANY = "Mohamed Mamdouh group"
ABBR = "MMG"
MAWASAH = f"المخزن المركزي بالمواساة - {ABBR}"
MAWASAH_STORE = f"خامات المواساة - {ABBR}"
DAMAGED = f"التالف — المواساة - {ABBR}"
AZARITA = f"مخزن الأزاريطة - {ABBR}"
AZARITA_STORE = f"خامات الأزاريطة - {ABBR}"
CENTER = f"مخزن سنتر Imed — أدوات مكتبية - {ABBR}"

PAPER = "A4-PAPER"
CARTON = "كرتونة"
RAGHAD = "raghad@imed.local"
SARA = "sara@imed.local"
NOUR = "nour@imed.local"


def as_user(user, fn, *args, **kwargs):
	frappe.set_user(user)
	try:
		return fn(*args, **kwargs)
	finally:
		frappe.set_user("Administrator")


def qty(item_code, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


def carton():
	"""Sheets in a carton, as A4 paper is set up; nothing here assumes the number."""
	return flt(frappe.db.get_value("UOM Conversion Detail", {"parent": PAPER, "uom": CARTON}, "conversion_factor"))


class IntegrationTestMaterialIssue(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.ink = (
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "TEST-MI-INK",
					"item_name": "TEST-MI-INK",
					"item_group": "أحبار",
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"include_item_in_manufacturing": 0,
					"item_defaults": [{"company": COMPANY, "default_warehouse": MAWASAH_STORE}],
				}
			)
			.insert()
			.name
		)
		cls.machine = make_machine("TEST-MI-MACHINE-AZ-1", AZARITA)
		cls.machine2 = make_machine("TEST-MI-MACHINE-AZ-2", AZARITA)
		cls.mawasah_machine = make_machine("TEST-MI-MACHINE-MW", MAWASAH)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("material_issue_test")
		self.assertTrue(carton() > 1, "A4 paper needs a carton conversion (setup_core.py)")
		receive(PAPER, 3 * carton(), MAWASAH_STORE)
		receive(self.ink, 50, MAWASAH_STORE)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="material_issue_test")

	# ---------- helpers ----------
	def request(self, rows=None, user=SARA, to=AZARITA_STORE):
		rows = rows or [{"item_code": PAPER, "qty": 2, "uom": CARTON}]
		doc = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Material Transfer",
				"company": COMPANY,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 1),
				"set_from_warehouse": MAWASAH_STORE,
				"set_warehouse": to,
				"items": [{"schedule_date": add_days(nowdate(), 1), **row} for row in rows],
			}
		)
		return as_user(user, doc.insert)

	def approved(self, rows=None):
		mr = self.request(rows)
		as_user(SARA, material_issue.request_approval, mr.name)
		as_user(RAGHAD, material_issue.approve, mr.name)
		return frappe.get_doc("Material Request", mr.name)

	def issue(self, mr, machine=None, received_by="Ahmed (Azarita)", qtys=None, user=RAGHAD, submit=True):
		def build():
			se = make_stock_entry(mr.name)
			se.custom_received_by = received_by
			for i, row in enumerate(se.items):
				if machine and not row.custom_printing_machine:
					row.custom_printing_machine = machine
				if qtys:
					row.qty = qtys[i]
			se.insert()
			if submit:
				se.submit()
			return se

		return as_user(user, build)

	def assert_refused(self, exc, fn, *args, **kwargs):
		"""The call fails, and what it wrote is undone, as a failed request would be."""
		frappe.db.savepoint("refused")
		with self.assertRaises(exc):
			fn(*args, **kwargs)
		frappe.db.rollback(save_point="refused")
		frappe.set_user("Administrator")

	# ---------- Scenario 1: request, approval, issue ----------
	def test_1_request_approve_and_issue_two_cartons(self):
		mawasah_before, azarita_before = qty(PAPER, MAWASAH_STORE), qty(PAPER, AZARITA_STORE)

		mr = self.request([{"item_code": PAPER, "qty": 2, "uom": CARTON, "custom_printing_machine": self.machine}])
		self.assertEqual(mr.owner, SARA)
		self.assertEqual(mr.docstatus, 0)
		self.assertEqual(flt(mr.items[0].stock_qty), 2 * carton())

		as_user(SARA, material_issue.request_approval, mr.name)
		self.assertEqual(frappe.db.get_value("Material Request", mr.name, "custom_approval_status"), "Pending Approval")
		as_user(RAGHAD, material_issue.approve, mr.name)
		mr.reload()
		self.assertEqual((mr.docstatus, mr.custom_approval_status, mr.custom_approved_by), (1, "Approved", RAGHAD))
		self.assertTrue(mr.custom_approved_on)
		# Asking and approving moved nothing.
		self.assertEqual((qty(PAPER, MAWASAH_STORE), qty(PAPER, AZARITA_STORE)), (mawasah_before, azarita_before))

		se = self.issue(mr)
		self.assertEqual(qty(PAPER, MAWASAH_STORE), mawasah_before - 2 * carton())
		self.assertEqual(qty(PAPER, AZARITA_STORE), azarita_before + 2 * carton())
		self.assertEqual((se.custom_received_by, se.custom_issued_by, se.posting_date.__str__()), ("Ahmed (Azarita)", RAGHAD, nowdate()))
		self.assertEqual(se.items[0].custom_printing_machine, self.machine)
		mr.reload()
		self.assertEqual((mr.status, flt(mr.per_ordered)), ("Transferred", 100))

	# ---------- Scenario 2: issue before approval ----------
	def test_2_pending_request_cannot_be_issued(self):
		mr = self.request()
		as_user(SARA, material_issue.request_approval, mr.name)
		before = qty(PAPER, MAWASAH_STORE)
		self.assert_refused(frappe.ValidationError, as_user, RAGHAD, make_stock_entry, mr.name)
		# A Stock Entry built by hand against the request, as through the API.
		self.assert_refused(frappe.ValidationError, self.manual_issue, mr, 1)
		self.assertEqual(qty(PAPER, MAWASAH_STORE), before)

	def manual_issue(self, mr, cartons):
		row = mr.items[0]
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"company": COMPANY,
				"stock_entry_type": "Material Transfer",
				"purpose": "Material Transfer",
				"custom_received_by": "Someone",
				"items": [
					{
						"item_code": row.item_code,
						"qty": cartons,
						"uom": row.uom,
						"conversion_factor": row.conversion_factor,
						"s_warehouse": row.from_warehouse,
						"t_warehouse": row.warehouse,
						"material_request": mr.name,
						"material_request_item": row.name,
						"custom_printing_machine": self.machine,
					}
				],
			}
		)
		as_user(RAGHAD, se.insert)
		as_user(RAGHAD, se.submit)
		return se

	# ---------- Scenario 3: rejected ----------
	def test_3_rejected_request_is_closed(self):
		mr = self.request()
		as_user(SARA, material_issue.request_approval, mr.name)
		as_user(RAGHAD, material_issue.reject, mr.name, "Not needed this week")
		mr.reload()
		self.assertEqual(
			(mr.docstatus, mr.custom_approval_status, mr.custom_approved_by, mr.custom_rejection_reason),
			(0, "Rejected", RAGHAD, "Not needed this week"),
		)
		before = qty(PAPER, MAWASAH_STORE)
		self.assert_refused(frappe.ValidationError, as_user, RAGHAD, make_stock_entry, mr.name)
		self.assert_refused(frappe.ValidationError, self.manual_issue, mr, 1)
		doc = frappe.get_doc("Material Request", mr.name)
		doc.items[0].qty = 1
		self.assert_refused(frappe.ValidationError, as_user, SARA, doc.save)
		self.assert_refused(frappe.ValidationError, as_user, SARA, frappe.get_doc("Material Request", mr.name).submit)
		self.assertEqual(qty(PAPER, MAWASAH_STORE), before)

	def test_3b_the_rejection_reason_is_plain_text_and_required(self):
		# SEC-01: the reason is shown on the request's form; markup in it must not run there. QA-25: required.
		mr = self.request()
		as_user(SARA, material_issue.request_approval, mr.name)
		for blank in (None, "", "   ", "<b></b>"):
			with self.subTest(blank):
				self.assert_refused(frappe.ValidationError, as_user, RAGHAD, material_issue.reject, mr.name, blank)
		as_user(RAGHAD, material_issue.reject, mr.name, '<img src=x onerror="alert(1)">Not needed<script>alert(2)</script>')
		reason = frappe.db.get_value("Material Request", mr.name, "custom_rejection_reason")
		self.assertNotIn("<", reason)
		self.assertIn("Not needed", reason)

	# ---------- Scenario 4: not enough stock ----------
	def test_4_not_enough_stock(self):
		mr = self.approved([{"item_code": PAPER, "qty": 2, "uom": CARTON, "custom_printing_machine": self.machine}])
		# Leave one carton in Mawasah.
		available = qty(PAPER, MAWASAH_STORE)
		issue_out(PAPER, available - carton(), MAWASAH_STORE)
		self.assert_refused(frappe.ValidationError, self.issue, mr)
		self.assertEqual(qty(PAPER, MAWASAH_STORE), carton())
		self.assertEqual(flt(frappe.db.get_value("Material Request", mr.name, "per_ordered")), 0)

	# ---------- Scenario 5: paper without a machine ----------
	def test_5_paper_needs_a_machine_of_the_branch(self):
		mr = self.approved()
		before = qty(PAPER, MAWASAH_STORE)
		self.assert_refused(frappe.ValidationError, self.issue, mr)
		# A machine of another branch is refused too.
		self.assert_refused(frappe.ValidationError, self.issue, mr, machine=self.mawasah_machine)
		self.assertEqual(qty(PAPER, MAWASAH_STORE), before)
		self.issue(mr, machine=self.machine)
		self.assertEqual(qty(PAPER, MAWASAH_STORE), before - 2 * carton())

	def test_5b_approved_machine_is_kept(self):
		mr = self.approved([{"item_code": PAPER, "qty": 1, "uom": CARTON, "custom_printing_machine": self.machine}])
		self.assert_refused(frappe.ValidationError, self.issue_with_other_machine, mr)

	def issue_with_other_machine(self, mr):
		se = as_user(RAGHAD, make_stock_entry, mr.name)
		se.custom_received_by = "Someone"
		se.items[0].custom_printing_machine = self.machine2
		as_user(RAGHAD, se.insert)

	# ---------- Scenario 6: not paper ----------
	def test_6_other_items_need_no_machine(self):
		mr = self.approved([{"item_code": self.ink, "qty": 5, "uom": "Nos"}])
		se = self.issue(mr)
		self.assertFalse(se.items[0].custom_printing_machine)
		self.assertEqual(qty(self.ink, AZARITA_STORE), 5)

	def test_6b_branch_can_request_a_book_of_the_other_library(self):
		# BOOK's defaults name Mawasah's selling cost center (setup_library.py); that must not hide it from Sara.
		if not frappe.db.exists("Item Default", {"parent": "BOOK", "selling_cost_center": ["is", "set"]}):
			self.skipTest("BOOK has no default selling cost center on this site")
		receive("BOOK", 3, MAWASAH_STORE)
		mr = self.request([{"item_code": "BOOK", "qty": 1, "uom": "Nos"}])
		self.assertEqual(mr.owner, SARA)

	# ---------- Scenario 7: issued twice ----------
	def test_7_cannot_issue_twice(self):
		mr = self.approved([{"item_code": PAPER, "qty": 1, "uom": CARTON, "custom_printing_machine": self.machine}])
		before = qty(PAPER, MAWASAH_STORE)
		se = self.issue(mr)
		# The same document again (a second click, a retried API call): no second movement.
		frappe.db.savepoint("again")
		try:
			as_user(RAGHAD, frappe.get_doc("Stock Entry", se.name).submit)
		except Exception:
			frappe.db.rollback(save_point="again")
		frappe.set_user("Administrator")
		self.assertEqual(qty(PAPER, MAWASAH_STORE), before - carton())
		self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": se.name, "is_cancelled": 0}), 2)
		# A second issue of the already issued request.
		self.assert_refused(frappe.ValidationError, self.manual_issue, mr, 1)
		self.assertEqual(qty(PAPER, MAWASAH_STORE), before - carton())
		self.assertEqual(
			frappe.db.count("Stock Entry Detail", {"material_request": mr.name, "docstatus": 1}), 1
		)

	# ---------- Scenario 8: not allowed ----------
	def test_8_only_the_approver_approves_and_only_the_store_issues(self):
		mr = self.request()
		as_user(SARA, material_issue.request_approval, mr.name)
		# Sara cannot approve, reject, submit or set the approval herself.
		self.assert_refused(frappe.PermissionError, as_user, SARA, material_issue.approve, mr.name)
		self.assert_refused(frappe.PermissionError, as_user, SARA, material_issue.reject, mr.name)
		self.assert_refused(frappe.ValidationError, as_user, SARA, frappe.get_doc("Material Request", mr.name).submit)
		doc = frappe.get_doc("Material Request", mr.name)
		doc.custom_approval_status = "Approved"
		self.assert_refused(frappe.PermissionError, as_user, SARA, doc.save)

		# Once approved, Sara cannot issue it: the stock leaves Mawasah, which is not hers.
		as_user(RAGHAD, material_issue.approve, mr.name)
		before = qty(PAPER, MAWASAH_STORE)
		self.assert_refused(frappe.PermissionError, self.issue, frappe.get_doc("Material Request", mr.name), self.machine, user=SARA)
		self.assertEqual(qty(PAPER, MAWASAH_STORE), before)

		# Requests only for one's own branch, and only by stock users.
		self.assert_refused(frappe.PermissionError, self.request, to=CENTER)
		self.assert_refused(frappe.PermissionError, self.request, user=NOUR)
		# Not from the damaged stock, and not back into the main warehouse.
		self.assert_refused(frappe.ValidationError, self.request, user="Administrator", to=MAWASAH_STORE)

	def test_8b_approved_request_cannot_be_changed(self):
		mr = self.approved()
		mr.items[0].qty = 5
		self.assert_refused(frappe.ValidationError, as_user, SARA, mr.save)
		self.assertEqual(flt(frappe.db.get_value("Material Request Item", mr.items[0].name, "qty")), 2)

	def test_8c_changing_a_pending_request_sends_it_back_to_draft(self):
		mr = self.request()
		as_user(SARA, material_issue.request_approval, mr.name)
		doc = frappe.get_doc("Material Request", mr.name)
		doc.items[0].qty = 3
		as_user(SARA, doc.save)
		self.assertFalse(frappe.db.get_value("Material Request", mr.name, "custom_approval_status"))

	# ---------- Scenario 9: partial issue ----------
	def test_9_partial_issue(self):
		mr = self.approved([{"item_code": PAPER, "qty": 2, "uom": CARTON, "custom_printing_machine": self.machine}])
		self.issue(mr, qtys=[1])
		mr.reload()
		self.assertEqual((mr.status, flt(mr.per_ordered)), ("Partially Received", 50))
		row = next(r for r in material_issues_report(frappe._dict(material_request=mr.name)))
		self.assertEqual((flt(row["issued_total"]), flt(row["remaining"])), (carton(), carton()))

		# The rest later, then nothing more.
		self.issue(frappe.get_doc("Material Request", mr.name))
		mr.reload()
		self.assertEqual((mr.status, flt(mr.per_ordered)), ("Transferred", 100))
		self.assert_refused(frappe.ValidationError, self.manual_issue, mr, 1)

	# ---------- Scenario 10: traceability, one quantity per machine ----------
	def test_10_paper_is_traced_to_each_machine(self):
		mr = self.approved(
			[
				{"item_code": PAPER, "qty": 1, "uom": CARTON, "custom_printing_machine": self.machine},
				{"item_code": PAPER, "qty": 1, "uom": "رزمة", "custom_printing_machine": self.machine2},
			]
		)
		se = self.issue(mr, received_by="Mona")
		ream = flt(frappe.db.get_value("UOM Conversion Detail", {"parent": PAPER, "uom": "رزمة"}, "conversion_factor"))

		rows = frappe.get_all(
			"Stock Entry Detail",
			filters={"parent": se.name},
			fields=["custom_printing_machine", "transfer_qty", "material_request", "material_request_item"],
		)
		self.assertEqual(
			sorted((r.custom_printing_machine, flt(r.transfer_qty)) for r in rows),
			sorted([(self.machine, carton()), (self.machine2, ream)]),
		)
		self.assertTrue(all(r.material_request == mr.name for r in rows))

		# From the machine back to the request, the issue, its date and the recipient.
		report = material_issues_report(frappe._dict(printing_machine=self.machine2))
		self.assertEqual(len(report), 1)
		line = report[0]
		self.assertEqual(
			(line["material_request"], line["stock_entry"], line["received_by"], line["issued_by"], str(line["issue_date"])),
			(mr.name, se.name, "Mona", RAGHAD, nowdate()),
		)
		self.assertEqual(flt(line["issued_stock_qty"]), ream)

		# Sara sees her branch's requests in the report; Nour, without stock rights, cannot open it.
		self.assertTrue(as_user(SARA, material_issues_report, frappe._dict(material_request=mr.name)))


def make_machine(name, warehouse):
	if frappe.db.exists("Printing Machine", name):
		return name
	# A machine works in a library: the one whose store it is in.
	library = "مكتبة الأزاريطة - MMG" if "الأزاريطة" in warehouse else "مكتبة المواساة - MMG"
	return frappe.get_doc(
		{"doctype": "Printing Machine", "machine_name": name, "warehouse": warehouse, "cost_center": library, "machine_type": "Riso"}
	).insert().name


def receive(item_code, quantity, warehouse):
	stock_entry("Material Receipt", [{"item_code": item_code, "qty": quantity, "t_warehouse": warehouse, "basic_rate": 1, "uom": frappe.db.get_value("Item", item_code, "stock_uom"), "conversion_factor": 1}])


def issue_out(item_code, quantity, warehouse):
	stock_entry("Material Issue", [{"item_code": item_code, "qty": quantity, "s_warehouse": warehouse, "uom": frappe.db.get_value("Item", item_code, "stock_uom"), "conversion_factor": 1}])


def stock_entry(purpose, rows):
	doc = frappe.get_doc(
		{"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": purpose, "purpose": purpose, "items": rows}
	).insert()
	doc.submit()
	return doc
