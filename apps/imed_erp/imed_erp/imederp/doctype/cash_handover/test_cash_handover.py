# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# The weekly cash hand-over (ACC-09, 22 Oct 2026): recorded by the branch, printed, signed on paper, confirmed by the
# named receiver with the scan attached; posted once, balanced, never income; in the day's close and the week's
# review; cancelled only with a reason and kept. Rolled back afterwards. The race of two hand-overs at once is in
# setup/concurrency_check.py (it needs two committed sessions).
#
#   bench --site frontend run-tests --doctype "Cash Handover"

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from imed_erp.imederp.doctype.cash_handover.cash_handover import cancel_handover, confirm_receipt
from imed_erp.imederp.testing import fund_cash_boxes

IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Account", "Cash Handover", "Cost Center", "Journal Entry", "Treasury Close", "User", "Weekly Cash Reconciliation", "File",
]

AZARITA, MAWASAH = "مكتبة الأزاريطة - MMG", "مكتبة المواساة - MMG"
AZARITA_BOX, MAWASAH_BOX = "خزينة مكتبة الأزاريطة - MMG", "خزينة مكتبة المواساة - MMG"
OWNER_CUSTODY, ACCOUNTANT_CUSTODY = "عهدة المالك النقدية - MMG", "عهدة المحاسب النقدية - MMG"
SARA, RAGHAD, OWNER, ACCOUNTANT = "sara@imed.local", "raghad@imed.local", "owner@imed.local", "accountant@imed.local"


def as_user(user, fn, *args, **kwargs):
	frappe.set_user(user)
	try:
		return fn(*args, **kwargs)
	finally:
		frappe.set_user("Administrator")


def balance(account):
	return flt(frappe.db.sql("select sum(debit - credit) from `tabGL Entry` where account = %s and is_cancelled = 0", account)[0][0], 2)


def handover(amount, receiver=OWNER, kind="Owner", user=SARA, branch=AZARITA, box=AZARITA_BOX, submit=True, date=None):
	def make():
		doc = frappe.get_doc(
			{
				"doctype": "Cash Handover", "branch": branch, "treasury": box, "amount": amount, "handover_date": date or today(),
				"handover_time": "20:00:00", "receiver_kind": kind, "receiver": receiver, "notes": "_Test week's cash",
			}
		).insert()
		if submit:
			doc.submit()
		return doc

	return as_user(user, make)


def scan_bytes(tag):
	"""A one-page PDF, as a scanner makes (Frappe reads an uploaded PDF, so it must be a real one); each scan its own
	(Frappe keeps one file for the same content)."""
	import io

	from pypdf import PdfWriter

	writer, out = PdfWriter(), io.BytesIO()
	writer.add_blank_page(width=420, height=595)
	writer.add_metadata({"/Title": tag})
	writer.write(out)
	return out.getvalue()


def attach(doc, name="signed.pdf", private=1, to=None, user=None):
	"""The scan of the signed receipt, attached to `to` (the hand-over itself by default)."""
	def make():
		f = frappe.get_doc(
			{
				"doctype": "File", "file_name": name, "is_private": private, "content": scan_bytes(f"{doc.name} {name} {frappe.generate_hash(length=6)}") if name.endswith(".pdf") else b"not a receipt",
				"attached_to_doctype": "Cash Handover", "attached_to_name": to or doc.name, "attached_to_field": "signed_receipt",
			}
		).insert(ignore_permissions=True)
		target = frappe.get_doc("Cash Handover", doc.name)
		target.signed_receipt = f.file_url
		target.save()
		return f

	return as_user(user or doc.receiver, make)


class IntegrationTestCashHandover(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("cash_handover_test")
		fund_cash_boxes(5000)
		frappe.db.set_single_value("Cash Close Settings", {"owner_custody_account": OWNER_CUSTODY, "accountant_custody_account": ACCOUNTANT_CUSTODY})

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="cash_handover_test")

	# 1, 16
	def test_the_branch_records_it_and_nothing_is_posted_yet(self):
		before = balance(AZARITA_BOX)
		doc = handover(1500)
		self.assertEqual((doc.status, doc.handed_over_by, doc.journal_entry), ("Pending Receipt", SARA, None))
		self.assertIn("ألف و خمسمائة جنيه", doc.amount_in_words)
		self.assertEqual(balance(AZARITA_BOX), before)
		self.assertFalse(frappe.db.exists("GL Entry", {"remarks": ("like", f"%{doc.name}%")}))

	# 2, 3, 12
	def test_the_owner_confirms_with_the_signed_receipt(self):
		doc = handover(1500)
		self.assertRaises(frappe.PermissionError, as_user, SARA, confirm_receipt, doc.name, 1500)
		attach(doc)
		box, custody = balance(AZARITA_BOX), balance(OWNER_CUSTODY)
		entry = as_user(OWNER, confirm_receipt, doc.name, 1500)
		doc.reload()
		self.assertEqual((doc.status, doc.received_by, doc.custody_account, doc.journal_entry), ("Received", OWNER, OWNER_CUSTODY, entry))
		self.assertEqual((balance(AZARITA_BOX), balance(OWNER_CUSTODY)), (box - 1500, custody + 1500))
		rows = frappe.get_all("GL Entry", filters={"voucher_no": entry, "is_cancelled": 0}, fields=["account", "debit", "credit"])
		self.assertEqual(sum(flt(r.debit) for r in rows), sum(flt(r.credit) for r in rows))
		# Cash moved, not earned or spent.
		self.assertEqual({r.account for r in rows}, {AZARITA_BOX, OWNER_CUSTODY})

	# 4
	def test_the_accountant_confirms_with_the_signed_receipt(self):
		doc = handover(700, receiver=ACCOUNTANT, kind="Accountant")
		attach(doc)
		as_user(ACCOUNTANT, confirm_receipt, doc.name, 700)
		self.assertEqual(frappe.db.get_value("Cash Handover", doc.name, "custody_account"), ACCOUNTANT_CUSTODY)

	# 5
	def test_no_confirmation_without_the_signed_receipt(self):
		doc = handover(500)
		self.assertRaisesRegex(frappe.ValidationError, "Attach the signed paper receipt", as_user, OWNER, confirm_receipt, doc.name, 500)

	# 6
	def test_a_wrong_attachment_is_refused(self):
		doc, other = handover(500), handover(400)
		# Another hand-over's scan.
		f = attach(other)
		frappe.db.set_value("Cash Handover", doc.name, "signed_receipt", f.file_url)
		self.assertRaisesRegex(frappe.ValidationError, "attached to", as_user, OWNER, confirm_receipt, doc.name, 500)
		# A public file, and a file that is not a PDF or a photo.
		attach(doc, "public.pdf", private=0)
		self.assertRaisesRegex(frappe.ValidationError, "private", as_user, OWNER, confirm_receipt, doc.name, 500)
		attach(doc, "notes.txt")
		self.assertRaisesRegex(frappe.ValidationError, "PDF or a photo", as_user, OWNER, confirm_receipt, doc.name, 500)
		# A link to somewhere else.
		frappe.db.set_value("Cash Handover", doc.name, "signed_receipt", "https://example.com/receipt.pdf")
		self.assertRaisesRegex(frappe.ValidationError, "attached to", as_user, OWNER, confirm_receipt, doc.name, 500)

	# 7
	def test_only_the_named_receiver_confirms(self):
		doc = handover(500)
		attach(doc)
		self.assertRaises(frappe.PermissionError, as_user, ACCOUNTANT, confirm_receipt, doc.name, 500)
		self.assertRaises(frappe.PermissionError, as_user, RAGHAD, confirm_receipt, doc.name, 500)
		# The receiver must be the owner, or the accountant, as named.
		self.assertRaisesRegex(frappe.ValidationError, "is not the", handover, 100, receiver=RAGHAD)
		self.assertRaisesRegex(frappe.ValidationError, "is not the", handover, 100, receiver=ACCOUNTANT, kind="Owner")

	# 8, 9
	def test_part_of_the_cash_and_never_more_than_is_there(self):
		held = balance(AZARITA_BOX)
		first = handover(flt(held / 2, 2))
		# What is pending is not available again.
		self.assertRaisesRegex(frappe.ValidationError, "cannot be handed over", handover, flt(held / 2, 2) + 1)
		second = handover(flt(held - flt(held / 2, 2), 2))
		self.assertEqual(flt(first.amount + second.amount, 2), held)
		self.assertRaises(frappe.ValidationError, handover, 1)

	# 10
	def test_confirming_twice_posts_once(self):
		doc = handover(300)
		attach(doc)
		as_user(OWNER, confirm_receipt, doc.name, 300)
		self.assertRaisesRegex(frappe.ValidationError, "Only a pending", as_user, OWNER, confirm_receipt, doc.name, 300)
		self.assertEqual(frappe.db.count("Journal Entry", {"user_remark": ("like", f"{doc.name}:%"), "docstatus": 1}), 1)

	def test_the_cash_counted_must_be_the_amount(self):
		doc = handover(300)
		attach(doc)
		self.assertRaisesRegex(frappe.ValidationError, "Cancel this hand-over", as_user, OWNER, confirm_receipt, doc.name, 250)

	# 13
	def test_the_day_s_close_and_the_week_count_it_once(self):
		from imed_erp.imederp.doctype.treasury_close.treasury_close import movements
		from imed_erp.imederp.doctype.weekly_cash_reconciliation.test_weekly_cash_reconciliation import any_week

		any_week()
		doc = handover(800)
		pending = movements(AZARITA_BOX, today(), today())
		self.assertEqual(pending.handed_over, 800)
		attach(doc)
		as_user(OWNER, confirm_receipt, doc.name, 800)
		after = movements(AZARITA_BOX, today(), today())
		# Confirmed: still 800 handed over, not 800 more spent.
		self.assertEqual((after.handed_over, after.other_out, after.expenses_and_payouts), (800, pending.other_out, pending.expenses_and_payouts))
		week = frappe.get_doc({"doctype": "Weekly Cash Reconciliation", "week_start": add_days(today(), -6), "business": AZARITA}).insert()
		row = next(r for r in week.handovers if r.cash_handover == doc.name)
		self.assertEqual((row.amount, row.receiver, row.has_signed_receipt), (800, OWNER, 1))
		self.assertGreaterEqual(week.total_handed_over, 800)

	def test_a_pending_hand_over_shows_without_its_receipt_in_the_week(self):
		from imed_erp.imederp.doctype.weekly_cash_reconciliation.test_weekly_cash_reconciliation import any_week

		any_week()
		doc = handover(250)
		week = frappe.get_doc({"doctype": "Weekly Cash Reconciliation", "week_start": add_days(today(), -6), "business": AZARITA}).insert()
		row = next(r for r in week.handovers if r.cash_handover == doc.name)
		self.assertEqual(row.has_signed_receipt, 0)
		self.assertGreaterEqual(week.pending_handovers, 250)
		self.assertGreaterEqual(week.handovers_without_receipt, 1)

	def test_a_closed_day_takes_no_hand_over_from_the_branch(self):
		from imed_erp.imederp.doctype.weekly_cash_reconciliation.test_weekly_cash_reconciliation import closed

		closed(today(), 0)
		self.assertRaisesRegex(frappe.ValidationError, "already closed", handover, 100)

	def test_the_close_does_not_turn_short_when_cash_is_handed_over(self):
		from imed_erp.imederp.doctype.treasury_close.treasury_close import movements

		doc = handover(1000)
		close = as_user(
			SARA,
			lambda: frappe.get_doc({"doctype": "Treasury Close", "treasury": AZARITA_BOX, "business": AZARITA, "close_date": today(), "counted": 0}).insert(),
		)
		close.counted = close.expected
		as_user(SARA, close.submit)
		self.assertEqual((close.handed_over, close.difference), (1000, 0))
		attach(doc)
		as_user(OWNER, confirm_receipt, doc.name, 1000)
		# Confirmed after the close: the close was right, nothing to review.
		self.assertFalse(frappe.db.get_value("Treasury Close", close.name, "needs_review"))
		self.assertEqual(movements(AZARITA_BOX, today(), today()).handed_over, 1000)

	# 14
	def test_branches_are_kept_apart(self):
		doc = handover(200)
		attach(doc)
		self.assertFalse(frappe.has_permission("Cash Handover", "read", doc=doc.name, user=RAGHAD))
		self.assertTrue(frappe.has_permission("Cash Handover", "read", doc=doc.name, user=SARA))
		scan = frappe.get_doc("File", {"file_url": frappe.db.get_value("Cash Handover", doc.name, "signed_receipt")})
		self.assertFalse(frappe.has_permission("File", "read", doc=scan, user=RAGHAD))
		self.assertTrue(frappe.has_permission("File", "read", doc=scan, user=SARA))
		# Raghad hands over from her own box only.
		self.assertRaises(frappe.PermissionError, handover, 100, user=RAGHAD)
		self.assertTrue(handover(100, user=RAGHAD, branch=MAWASAH, box=MAWASAH_BOX).name)

	# 15
	def test_the_receipt_prints_in_arabic(self):
		doc = handover(2500)
		html = frappe.get_print("Cash Handover", doc.name, print_format="Cash Handover Receipt")
		names = [frappe.db.get_value("User", u, "full_name") for u in (SARA, OWNER)]
		for text in ("إيصال استلام نقدية", "ألفان و خمسمائة جنيه", "توقيع المستلم", doc.name, 'dir="rtl"', *names):
			self.assertIn(text, html)

	# 17
	def test_cancelling_keeps_the_record_and_reverses_the_entry(self):
		pending = handover(150)
		self.assertRaises(frappe.PermissionError, as_user, RAGHAD, cancel_handover, pending.name, "mistake")
		as_user(SARA, cancel_handover, pending.name, "counted wrong, recorded again")
		pending.reload()
		self.assertEqual((pending.docstatus, pending.status, pending.cancelled_by, pending.cancel_reason), (2, "Cancelled", SARA, "counted wrong, recorded again"))

		doc = handover(600)
		attach(doc)
		entry = as_user(OWNER, confirm_receipt, doc.name, 600)
		box = balance(AZARITA_BOX)
		# Its entry goes only with it, and only the accountant or the owner cancels a confirmed one, with a reason.
		self.assertRaises(frappe.ValidationError, frappe.get_doc("Journal Entry", entry).cancel)
		self.assertRaises(frappe.PermissionError, as_user, SARA, cancel_handover, doc.name, "mistake")
		self.assertRaises(frappe.ValidationError, as_user, ACCOUNTANT, cancel_handover, doc.name, " ")
		as_user(ACCOUNTANT, cancel_handover, doc.name, "the owner gave it back")
		doc.reload()
		self.assertEqual((doc.status, doc.cancelled_by, frappe.db.get_value("Journal Entry", entry, "docstatus")), ("Cancelled", ACCOUNTANT, 2))
		self.assertEqual(balance(AZARITA_BOX), box + 600)
		# The signed receipt stays.
		scan = frappe.get_doc("File", {"file_url": doc.signed_receipt, "attached_to_name": doc.name})
		self.assertRaises(frappe.ValidationError, scan.delete)

	def test_a_confirmed_receipt_is_not_changed(self):
		doc = handover(350)
		attach(doc)
		as_user(OWNER, confirm_receipt, doc.name, 350)
		self.assertRaises(frappe.ValidationError, attach, doc, "another.pdf")

	def test_the_receiver_is_someone_else(self):
		self.assertRaisesRegex(frappe.ValidationError, "someone else", handover, 100, receiver=ACCOUNTANT, kind="Accountant", user=ACCOUNTANT)

	def test_one_scan_for_one_hand_over(self):
		first, second = handover(100), handover(120)
		paper = scan_bytes("one signed paper")
		# The same scanned paper uploaded onto both hand-overs.
		for doc in (first, second):
			f = frappe.get_doc(
				{"doctype": "File", "file_name": "scan.pdf", "is_private": 1, "content": paper, "attached_to_doctype": "Cash Handover",
				 "attached_to_name": doc.name, "attached_to_field": "signed_receipt"}
			).insert(ignore_permissions=True)
			frappe.db.set_value("Cash Handover", doc.name, "signed_receipt", f.file_url)
		self.assertRaisesRegex(frappe.ValidationError, "already the receipt", as_user, OWNER, confirm_receipt, second.name, 120)
