# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The weekly hand-over of a branch's cash (ACC-09; owner, 22 Oct 2026). At the end of the week, or whenever cash is
# needed, the branch manager hands cash from her box to the owner or the accountant, who signs a paper receipt.
# No electronic signature: the signed paper is scanned or photographed and kept here.
#
#   1. The branch manager records it and submits: Pending Receipt. Nothing is posted; the amount must be in the box
#      (its ledger balance, less the hand-overs still pending), checked under a lock on the box, so two hand-overs at
#      once cannot take the same cash. Part of the cash may be handed over.
#   2. She prints the receipt (Cash Handover Receipt: Arabic, the amount in figures and in words, a space to sign).
#   3. The receiver counts the cash, signs, attaches the scan to this hand-over and confirms (confirm_receipt below).
#      Only the person named as receiver confirms, never the person who handed it over; the amount counted must be the
#      amount recorded; the scan must be this hand-over's own private file, a PDF or a photo. Confirming twice posts
#      nothing more.
#   4. Confirmed: one Journal Entry, Dr the receiver's custody account / Cr the branch's box, dated the hand-over day.
#      The cash is still the group's (Cash Close Settings names the custody accounts): no revenue, no expense.
#
# The daily close counts a hand-over on its day, pending or confirmed (treasury_close.py, Handed Over): the cash left
# the box that day. The confirmation's entry is therefore left out of the close's movements, and does not mark the
# closed day for review. A hand-over is a separate step from the close: closing the day hands nothing over.
#
# Cancelling keeps the record, with who cancelled it, when and why: a pending one by whoever recorded it or the
# accountant; a confirmed one by the accountant or the owner only, which reverses its entry. Either marks the closes
# that counted it for review. A confirmed hand-over's receipt and amounts cannot be changed, nor its scan deleted.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, now_datetime, today

from imed_erp.imederp.branches import check_has_branch
from imed_erp.imederp.doctype.cash_close_settings.cash_close_settings import OWNER_ROLE
from imed_erp.imederp.sales_cancellation import clean_reason
from imed_erp.imederp.treasuries import check_treasury

CASH = "Cash"
PENDING, RECEIVED, CANCELLED = "Pending Receipt", "Received", "Cancelled"
ACCOUNTS_ROLES = ("Accounts Manager", "System Manager")
RECEIVER_ROLE = {"Owner": OWNER_ROLE, "Accountant": "Accountant"}
CUSTODY_FIELD = {"Owner": "owner_custody_account", "Accountant": "accountant_custody_account"}
RECEIPT_TYPES = (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic")


def amount_in_words(amount):
	from num2words import num2words

	return f"{num2words(flt(amount, 2), lang='ar', to='currency', currency='EGP')} فقط لا غير"


class CashHandover(Document):
	def validate(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("The amount must be greater than zero."))
		self.amount = flt(self.amount, 2)
		self.amount_in_words = amount_in_words(self.amount)
		self.check_box()
		if self.docstatus == 0:
			self.status = "Draft"
			self.handed_over_by = frappe.session.user
		self.check_receiver()

	def check_box(self):
		if frappe.db.get_value("Cost Center", self.branch, "is_group"):
			frappe.throw(_("Cost Center {0} is a group. Choose a business under it.").format(self.branch))
		allowed = frappe.get_all("User Permission", filters={"user": frappe.session.user, "allow": "Cost Center"}, pluck="for_value")
		check_has_branch(allowed)
		if allowed and self.branch not in allowed:
			frappe.throw(_("{0} is not your branch.").format(self.branch), frappe.PermissionError, title=_("Not Your Branch"))
		account = frappe.db.get_value("Account", self.treasury, ["account_type", "is_group"], as_dict=True)
		if not account or account.is_group or account.account_type != CASH:
			frappe.throw(_("{0} is not a cash box. Cash is handed over from a branch's cash box.").format(self.treasury), title=_("Wrong Treasury"))
		check_treasury(self.branch, self.treasury)

	def check_receiver(self):
		role = RECEIVER_ROLE.get(self.receiver_kind)
		if not role:
			frappe.throw(_("Choose who receives the cash: the owner or the accountant."))
		if not frappe.db.get_value("User", self.receiver, "enabled") or role not in frappe.get_roles(self.receiver):
			frappe.throw(_("{0} is not the {1}.").format(self.receiver, _(self.receiver_kind).lower()), title=_("Wrong Receiver"))
		if self.receiver == (self.handed_over_by or frappe.session.user):
			frappe.throw(_("Cash is handed over to someone else: the receiver cannot be the person handing it over."), title=_("Wrong Receiver"))

	def before_submit(self):
		self.check_available()
		self.check_closed_day()
		self.status = PENDING

	def check_available(self):
		"""The box holds it: its ledger balance, less the hand-overs still waiting. Locked first, so a second hand-over
		from the same box at the same moment waits for this one and sees it."""
		frappe.db.get_value("Account", self.treasury, "name", for_update=True)
		balance = flt(
			frappe.db.sql(
				"select sum(debit - credit) from `tabGL Entry` where account = %s and is_cancelled = 0 and posting_date <= %s for update",
				(self.treasury, today()),
			)[0][0]
		)
		pending = flt(
			frappe.db.sql(
				"""select sum(amount) from `tabCash Handover`
				where treasury = %s and docstatus = 1 and status = %s and name != %s for update""",
				(self.treasury, PENDING, self.name),
			)[0][0]
		)
		available = flt(balance - pending, 2)
		if self.amount > available:
			frappe.throw(
				_("{0} holds {1} that is not already being handed over; {2} cannot be handed over.").format(
					self.treasury,
					frappe.format_value(available, {"fieldtype": "Currency"}),
					frappe.format_value(self.amount, {"fieldtype": "Currency"}),
				),
				title=_("Not Enough Cash"),
			)

	def check_closed_day(self):
		"""Dated into a day already closed: the close did not count it. Refused to a branch manager; the accountant's
		marks those closes for review."""
		from imed_erp.imederp.doctype.treasury_close.treasury_close import REOPEN_ROLES, mark_for_review

		closed = frappe.db.get_value(
			"Treasury Close", {"treasury": self.treasury, "close_date": (">=", self.handover_date), "docstatus": 1}, "name"
		)
		if not closed:
			return
		if not set(REOPEN_ROLES) & set(frappe.get_roles()):
			frappe.throw(
				_("{0} is already closed for {1} ({2}). Date the hand-over today, or ask the accountant.").format(
					self.treasury, frappe.format_value(self.handover_date, {"fieldtype": "Date"}), closed
				),
				title=_("Day Already Closed"),
			)
		mark_for_review(
			self.treasury,
			self.handover_date,
			_("Cash Handover {0} was recorded by {1} on a closed day.").format(self.name, frappe.session.user),
		)

	def before_update_after_submit(self):
		before = self.get_doc_before_save()
		if before and before.status != PENDING and (
			self.signed_receipt != before.signed_receipt or flt(self.received_amount) != flt(before.received_amount)
		):
			frappe.throw(_("{0} is {1}: its receipt and amounts stay as confirmed.").format(self.name, _(before.status)), title=_("Already Confirmed"))

	def before_cancel(self):
		if not clean_reason(self.cancel_reason):
			frappe.throw(_("Cancelling a hand-over needs a reason."), title=_("Reason Needed"))
		status = frappe.db.get_value("Cash Handover", self.name, "status", for_update=True)
		accounts = bool(set(ACCOUNTS_ROLES) & set(frappe.get_roles()))
		if status == RECEIVED and not accounts:
			frappe.throw(_("A confirmed hand-over is cancelled by the accountant or the owner only."), frappe.PermissionError)
		if status == PENDING and not accounts and frappe.session.user != self.handed_over_by:
			frappe.throw(_("Only the person who recorded it, or the accountant, cancels a pending hand-over."), frappe.PermissionError)

	def on_cancel(self):
		from imed_erp.imederp.doctype.treasury_close.treasury_close import mark_for_review

		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
			entry = frappe.get_doc("Journal Entry", self.journal_entry)
			entry.flags.ignore_permissions = True
			entry.flags.from_cash_handover = True
			entry.cancel()
		self.db_set({"status": CANCELLED, "cancelled_by": frappe.session.user, "cancelled_on": now_datetime()})
		if frappe.db.exists("Treasury Close", {"treasury": self.treasury, "close_date": (">=", self.handover_date), "docstatus": 1}):
			mark_for_review(
				self.treasury,
				self.handover_date,
				_("Cash Handover {0} was cancelled by {1}: {2}").format(self.name, frappe.session.user, self.cancel_reason),
			)


def check_signed_receipt(doc):
	"""The scan is this hand-over's own private file, a PDF or a photo, uploaded after it was recorded."""
	if not doc.signed_receipt:
		frappe.throw(_("Attach the signed paper receipt (a scan or a photo) before confirming."), title=_("Signed Receipt Needed"))
	files = frappe.get_all(
		"File",
		filters={"file_url": doc.signed_receipt, "attached_to_doctype": "Cash Handover", "attached_to_name": doc.name},
		fields=["name", "is_private", "file_size", "creation", "file_name", "content_hash"],
	)
	if not files:
		frappe.throw(_("The signed receipt must be a file attached to {0} itself.").format(doc.name), title=_("Wrong Attachment"))
	file = files[0]
	if not file.is_private:
		frappe.throw(_("The signed receipt must be a private file."), title=_("Wrong Attachment"))
	if not (file.file_name or doc.signed_receipt).lower().endswith(RECEIPT_TYPES):
		frappe.throw(_("The signed receipt must be a PDF or a photo."), title=_("Wrong Attachment"))
	if get_datetime(file.creation) < get_datetime(doc.creation):
		frappe.throw(_("The signed receipt was uploaded before {0} was recorded.").format(doc.name), title=_("Wrong Attachment"))
	# One signed paper for one hand-over: the same scan on another hand-over is not this one's receipt.
	others = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Cash Handover",
			"attached_to_name": ("!=", doc.name),
			"content_hash": file.content_hash or "-",
		},
		pluck="attached_to_name",
	)
	used = [h for h in others if frappe.db.get_value("Cash Handover", h, "docstatus") == 1]
	if used:
		frappe.throw(
			_("This scan is already the receipt of {0}. Each hand-over has its own signed receipt.").format(", ".join(sorted(set(used)))),
			title=_("Wrong Attachment"),
		)


@frappe.whitelist(methods=["POST"])
def confirm_receipt(name, received_amount):
	"""The receiver confirms, after counting the cash and attaching the signed receipt. Posts the hand-over, once."""
	frappe.db.get_value("Cash Handover", name, "name", for_update=True)
	doc = frappe.get_doc("Cash Handover", name)
	if frappe.session.user != doc.receiver:
		frappe.throw(_("Only {0}, the receiver named on {1}, confirms it.").format(doc.receiver, name), frappe.PermissionError, title=_("Not the Receiver"))
	if frappe.session.user == doc.handed_over_by:
		frappe.throw(_("The person who handed the cash over cannot confirm it."), frappe.PermissionError)
	if doc.docstatus != 1 or doc.status != PENDING:
		frappe.throw(_("{0} is {1}. Only a pending hand-over is confirmed.").format(name, _(doc.status)), title=_("Already Confirmed"))
	if flt(received_amount, 2) != flt(doc.amount, 2):
		frappe.throw(
			_("The cash counted, {0}, is not the {1} recorded. Cancel this hand-over and record the amount actually handed over.").format(
				frappe.format_value(flt(received_amount), {"fieldtype": "Currency"}), frappe.format_value(doc.amount, {"fieldtype": "Currency"})
			),
			title=_("Amount Differs"),
		)
	check_signed_receipt(doc)
	custody = frappe.db.get_single_value("Cash Close Settings", CUSTODY_FIELD[doc.receiver_kind])
	if not custody or frappe.db.get_value("Account", custody, "account_type") != CASH:
		frappe.throw(
			_("Cash Close Settings has no {0} (a cash account). The accountant sets it first.").format(
				_(frappe.get_meta("Cash Close Settings").get_label(CUSTODY_FIELD[doc.receiver_kind]))
			),
			title=_("Custody Account Needed"),
		)
	entry = post(doc, custody)
	doc.db_set(
		{
			"status": RECEIVED,
			"received_amount": flt(received_amount, 2),
			"received_by": frappe.session.user,
			"received_on": now_datetime(),
			"custody_account": custody,
			"journal_entry": entry,
		}
	)
	doc.add_comment("Info", _("Received {0} and confirmed with the signed receipt.").format(frappe.format_value(doc.amount, {"fieldtype": "Currency"})))
	return entry


def post(doc, custody):
	company = frappe.db.get_value("Account", doc.treasury, "company")
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Cash Entry",
			"company": company,
			"posting_date": doc.handover_date,
			"user_remark": _("{0}: cash handed over from {1} by {2} to {3}.").format(doc.name, doc.treasury, doc.handed_over_by, doc.receiver),
			"accounts": [
				{"account": custody, "debit_in_account_currency": doc.amount, "cost_center": doc.branch},
				{"account": doc.treasury, "credit_in_account_currency": doc.amount, "cost_center": doc.branch},
			],
		}
	)
	entry.flags.ignore_permissions = True
	entry.flags.from_cash_handover = True
	entry.insert()
	entry.submit()
	return entry.name


@frappe.whitelist(methods=["POST"])
def cancel_handover(name, reason):
	reason = clean_reason(reason)
	if not reason:
		frappe.throw(_("Cancelling a hand-over needs a reason."), title=_("Reason Needed"))
	doc = frappe.get_doc("Cash Handover", name)
	doc.check_permission("read")
	doc.cancel_reason = reason
	# The roles are checked in before_cancel: the branch manager who recorded a pending one may cancel it.
	doc.flags.ignore_permissions = True
	doc.cancel()
	return doc.name


def block_cancel_of_handover_entry(doc, method=None):
	"""Journal Entry before_cancel hook: a hand-over's entry is reversed only by cancelling the hand-over."""
	if doc.flags.from_cash_handover:
		return
	handover = frappe.db.get_value("Cash Handover", {"journal_entry": doc.name, "docstatus": 1}, "name")
	if handover:
		frappe.throw(_("{0} was posted by Cash Handover {1}. Cancel the hand-over instead.").format(doc.name, handover))


def keep_signed_receipt(doc, method=None):
	"""File on_trash hook: a confirmed hand-over's signed receipt stays."""
	if doc.attached_to_doctype != "Cash Handover" or not doc.attached_to_name:
		return
	status, receipt = frappe.db.get_value("Cash Handover", doc.attached_to_name, ["status", "signed_receipt"]) or (None, None)
	if status in (RECEIVED, CANCELLED) and receipt == doc.file_url:
		frappe.throw(_("{0} is the signed receipt of {1}. It is kept.").format(doc.file_name, doc.attached_to_name), title=_("Signed Receipt"))


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def receivers(doctype, txt, searchfield, start, page_len, filters):
	"""For the Receiver field: the enabled users who are the owner, or the accountant."""
	role = RECEIVER_ROLE.get((filters or {}).get("receiver_kind"))
	if not role:
		return []
	return frappe.db.sql(
		"""select u.name, u.full_name from `tabUser` u join `tabHas Role` r on r.parent = u.name and r.parenttype = 'User'
		where r.role = %(role)s and u.enabled = 1 and u.name not in ('Administrator', 'Guest')
		and (u.name like %(txt)s or u.full_name like %(txt)s) order by u.full_name limit %(start)s, %(page_len)s""",
		{"role": role, "txt": f"%{txt}%", "start": start, "page_len": page_len},
	)
