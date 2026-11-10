# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# What a user can do by sending a document straight to the server (REST insert, save or submit) instead of using the
# screen: a field the screen shows as read-only is not protected by that. Security audit, 10 Nov 2026
# (docs/security/FULL_SECURITY_AUDIT.md, findings D1..D7). Each test is the attack; it failed before the fix. Every
# document is made exactly as a REST call would make it: built from the caller's values, as the caller, then
# insert/save/submit with permissions applied. Rolled back.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.tests.test_security_server_fields

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from imed_erp.imederp.doctype.app_payment.test_app_payment import AZARITA_BOX as PAYMENT_BOX
from imed_erp.imederp.doctype.app_payment.test_app_payment import subscription
from imed_erp.imederp.doctype.cash_handover.cash_handover import cancel_handover
from imed_erp.imederp.doctype.treasury_close.test_treasury_close import DAY1, DAY2, close, move
from imed_erp.imederp.doctype.weekly_cash_reconciliation.test_weekly_cash_reconciliation import any_week, closed
from imed_erp.imederp.tests.testing import fund_cash_boxes

AZARITA, MAWASAH = "مكتبة الأزاريطة - MMG", "مكتبة المواساة - MMG"
AZARITA_BOX, MAWASAH_BOX = "خزينة مكتبة الأزاريطة - MMG", "خزينة مكتبة المواساة - MMG"
SARA, RAGHAD, OWNER, ACCOUNTANT = "sara@imed.local", "raghad@imed.local", "owner@imed.local", "accountant@imed.local"


def box_balance(box):
	return flt(frappe.db.sql("select sum(debit - credit) from `tabGL Entry` where account=%s and is_cancelled=0", box)[0][0], 2)


class IntegrationTestServerSetFields(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("server_fields")
		fund_cash_boxes(5000)
		any_week()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.clear_messages()
		frappe.db.rollback(save_point="server_fields")

	def as_user(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def handover_values(self, **values):
		return {
			"doctype": "Cash Handover", "branch": AZARITA, "treasury": AZARITA_BOX, "amount": 1, "handover_date": today(),
			"handover_time": "20:00:00", "receiver_kind": "Owner", "receiver": OWNER, "notes": "_Test", **values,
		}

	# D1
	def test_a_hand_over_cannot_be_used_to_cancel_someone_elses_journal_entry(self):
		victim = move(300, box=MAWASAH_BOX, business=MAWASAH)  # any posted entry, of another branch

		def attack():
			doc = frappe.get_doc(self.handover_values(journal_entry=victim.name)).insert()
			doc.journal_entry = victim.name  # again at submit, as a second request would
			doc.submit()
			cancel_handover(doc.name, "recorded by mistake")
			return doc.name

		name = self.as_user(SARA, attack)
		self.assertEqual(frappe.db.get_value("Journal Entry", victim.name, "docstatus"), 1, "the other branch's entry was cancelled")
		self.assertEqual(frappe.db.get_value("Cash Handover", name, "status"), "Cancelled")  # her own hand-over still cancels

	# D5
	def test_the_person_handing_over_is_the_one_who_submits_never_a_name_sent_with_the_document(self):
		def attack():
			# The accountant, alone: a hand-over "by Sara" to himself, which he could then confirm.
			values = self.handover_values(receiver_kind="Accountant", receiver=ACCOUNTANT, handed_over_by=SARA, docstatus=1)
			return frappe.get_doc(values).insert()

		frappe.db.savepoint("attack")
		try:
			doc = self.as_user(ACCOUNTANT, attack)
		except frappe.ValidationError:
			frappe.db.rollback(save_point="attack")
			return  # refused: he is the one handing over, so he cannot be the receiver
		self.assertEqual(doc.handed_over_by, ACCOUNTANT)
		self.fail("the accountant recorded a hand-over to himself in another person's name")

	def test_the_server_set_fields_of_a_hand_over_are_empty_until_it_is_confirmed(self):
		custody = frappe.db.get_single_value("Cash Close Settings", "owner_custody_account")
		values = self.handover_values(received_by=OWNER, received_on=today(), custody_account=custody, cancelled_by=OWNER, status="Received")
		doc = self.as_user(SARA, lambda: frappe.get_doc(values).insert())
		doc.reload()
		self.assertEqual((doc.status, doc.received_by, doc.custody_account, doc.cancelled_by, doc.handed_over_by), ("Draft", None, None, None, SARA))

	# D2
	def test_a_payment_always_posts_its_own_entry(self):
		sub = subscription()
		other = move(50)
		before = box_balance(PAYMENT_BOX)

		def attack():
			values = {
				"doctype": "App Payment", "subscription": sub, "posting_date": today(), "branch": AZARITA, "payment_method": "Cash",
				"treasury": PAYMENT_BOX, "amount": 500, "journal_entry": other.name,
			}
			doc = frappe.get_doc(values).insert()
			doc.journal_entry = other.name
			doc.submit()
			return doc.name

		name = self.as_user(SARA, attack)
		entry = frappe.db.get_value("App Payment", name, "journal_entry")
		self.assertNotEqual(entry, other.name, "the payment took another entry as its own and posted nothing")
		self.assertEqual(box_balance(PAYMENT_BOX), before + 500)

	# D3
	def test_a_discrepancys_decision_is_changed_only_by_its_actions(self):
		doc = frappe.get_doc("Cash Discrepancy", closed(DAY1, -100).cash_discrepancy)

		def attack():
			forged = frappe.get_doc("Cash Discrepancy", doc.name)
			forged.update(
				{
					"status": "Recovery Approved", "payroll_status": "Ready for Payroll Review", "approved_by": OWNER,
					"approved_on": today(), "recommended_by": OWNER, "recovery_total": 100, "amount": 0, "kind": "Surplus",
					"adjustment_entry": None, "treasury": MAWASAH_BOX,
				}
			)
			forged.investigation_notes = "an ordinary edit, which is still allowed"
			forged.save()

		self.as_user(ACCOUNTANT, attack)
		after = frappe.get_doc("Cash Discrepancy", doc.name)
		self.assertEqual(
			(after.status, after.payroll_status or None, after.approved_by, after.recommended_by, flt(after.recovery_total), flt(after.amount), after.kind, after.treasury),
			("Pending Investigation", None, None, None, 0, 100, "Shortage", AZARITA_BOX),
		)
		self.assertEqual(after.investigation_notes, "an ordinary edit, which is still allowed")

	# D7
	def test_a_close_never_takes_a_discrepancy_named_by_the_caller(self):
		other = closed(DAY1, -100).cash_discrepancy

		def attack():
			doc = close(0, DAY2, cash_discrepancy=other)
			doc.counted = doc.expected  # no difference: the close opens no discrepancy of its own
			doc.cash_discrepancy = other
			doc.submit()
			return doc.name

		name = self.as_user(SARA, attack)
		self.assertIsNone(frappe.db.get_value("Treasury Close", name, "cash_discrepancy"))

	def test_withdrawing_touches_only_the_closes_own_discrepancy(self):
		from imed_erp.imederp.doctype.cash_discrepancy.cash_discrepancy import withdraw

		first = closed(DAY1, -100)
		self.assertRaises(frappe.ValidationError, withdraw, first.cash_discrepancy, "TRC-SOME-OTHER-CLOSE")
		self.assertEqual(frappe.db.get_value("Cash Discrepancy", first.cash_discrepancy, "status"), "Pending Investigation")

	# D4
	def test_another_branchs_draft_cannot_be_taken_over_by_rewriting_its_branch(self):
		theirs = close(0, DAY1, treasury=MAWASAH_BOX, business=MAWASAH)  # Mawasah's draft close

		def attack():
			doc = frappe.get_doc("Treasury Close", theirs.name)
			doc.treasury, doc.business = AZARITA_BOX, AZARITA  # now it "is" Sara's branch's
			doc.save()

		frappe.db.savepoint("attack")
		with self.assertRaises(frappe.PermissionError):
			self.as_user(SARA, attack)
		frappe.db.rollback(save_point="attack")
		self.assertEqual(frappe.db.get_value("Treasury Close", theirs.name, "business"), MAWASAH)

	def test_a_user_still_saves_her_own_draft(self):
		mine = self.as_user(SARA, close, 0, DAY1)

		def edit():
			doc = frappe.get_doc("Treasury Close", mine.name)
			doc.note = "counted twice"
			doc.save()

		self.as_user(SARA, edit)
		self.assertEqual(frappe.db.get_value("Treasury Close", mine.name, "note"), "counted twice")
