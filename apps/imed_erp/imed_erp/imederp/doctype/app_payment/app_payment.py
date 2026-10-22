# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# What a student pays BA Plus for a course (22 Oct 2026): in cash at a branch, or electronically (a bank transfer,
# InstaPay, Vodafone Cash). This changes requirements v1.2, under which no course money passed through the group
# (APP-05); the course is still the doctor's, so the money is held for the doctor and never becomes the group's
# revenue. The group's income from the app stays the platform fee (platform_fee_posting.py).
#
# Submitting posts one Journal Entry:
#   Dr the account the money reached   cash: the collecting branch's own cash box; electronic: the bank or wallet
#   Cr مقبوضات الطلبة لحساب الأطباء — التطبيق   held for the doctor
# A cash payment is then one of the box's collections, in its daily close and its weekly review (treasury_close.py);
# an electronic one never touches a cash box, and is matched with the bank's or wallet's statement (ERPNext's Bank
# Clearance, on the entry's reference number; the App Payments report shows what is cleared).
#
# Never twice: one entry per payment (journal_entry, under a lock); an electronic reference number once per account
# (reference_key, unique); a payment imported from BA Plus once per its id there, even after it is cancelled
# (import_key, unique; import_payment below). Cancelling is the accountant's, with a reason, and reverses the entry.
# How the money held reaches the doctor (paid out, or set against his platform fees) is not decided yet
# (docs/requirements/v1.3-amendments.md).

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from imed_erp.imederp.branches import check_has_branch
from imed_erp.imederp.sales_cancellation import clean_reason
from imed_erp.imederp.treasuries import BUSINESS_TREASURY, abbr_of, check_treasury, plain

CASH = "Cash"
HELD_ACCOUNT = "مقبوضات الطلبة لحساب الأطباء — التطبيق"
CANCEL_ROLES = ("Accounts Manager", "System Manager")
IMPORT_ROLES = ("Accounts Manager", "System Manager")
MANUAL, IMPORTED = "Manual", "Imported"


def is_cash(method):
	return method == CASH


def branch_cash_box(branch):
	"""The branch's own cash box (treasuries.py), or None: a business without one (the app) takes no cash."""
	abbr = abbr_of(branch)
	name = BUSINESS_TREASURY.get(plain(branch, abbr))
	box = f"{name} - {abbr}" if name else None
	return box if box and frappe.db.get_value("Account", box, "account_type") == CASH else None


def clean_reference(value):
	return " ".join((value or "").split()).upper() or None


class AppPayment(Document):
	def validate(self):
		self.check_source()
		self.set_from_subscription()
		if flt(self.amount) <= 0:
			frappe.throw(_("The amount must be greater than zero."))
		self.amount = flt(self.amount, 2)
		self.check_branch()
		self.check_treasury()
		self.check_reference()

	def before_submit(self):
		# Read again under the locks: another session may have recorded the same reference since this was saved.
		self.check_reference()

	def check_source(self):
		if self.flags.from_import:
			self.source = IMPORTED
			if not self.external_id:
				frappe.throw(_("A payment imported from BA Plus needs its id there."))
			self.import_key = f"BA Plus:{self.external_id}"
			return
		before = self.get_doc_before_save()
		if before and before.source == IMPORTED:
			for field in ("source", "external_id", "import_key"):
				self.set(field, before.get(field))
			return
		self.source, self.external_id, self.import_key = MANUAL, None, None

	def set_from_subscription(self):
		subscription = frappe.db.get_value(
			"App Subscription", self.subscription, ["student", "course", "doctor", "agreement", "docstatus"], as_dict=True
		)
		if not subscription or subscription.docstatus != 1:
			frappe.throw(_("Subscription {0} is not submitted. A payment is for a submitted subscription.").format(self.subscription))
		self.student, self.course, self.doctor, self.agreement = (
			subscription.student,
			subscription.course,
			subscription.doctor,
			subscription.agreement,
		)

	def check_branch(self):
		if frappe.db.get_value("Cost Center", self.branch, "is_group"):
			frappe.throw(_("Cost Center {0} is a group. Choose a business under it.").format(self.branch))
		allowed = frappe.get_all("User Permission", filters={"user": frappe.session.user, "allow": "Cost Center"}, pluck="for_value")
		check_has_branch(allowed)
		if allowed and self.branch not in allowed:
			frappe.throw(_("{0} is not your branch.").format(self.branch), frappe.PermissionError, title=_("Not Your Branch"))

	def check_treasury(self):
		account = frappe.db.get_value("Account", self.treasury, ["account_type", "is_group"], as_dict=True)
		if not account or account.is_group:
			frappe.throw(_("{0} is not a treasury.").format(self.treasury))
		if is_cash(self.payment_method):
			# Cash is in the branch's own box, whoever records it.
			box = branch_cash_box(self.branch)
			if not box:
				frappe.throw(
					_("{0} has no cash box. A cash payment is taken at a branch, into its own cash box.").format(self.branch),
					title=_("No Cash Box"),
				)
			if self.treasury != box:
				frappe.throw(
					_("Cash paid at {0} goes into its cash box, {1}.").format(self.branch, box), title=_("Wrong Treasury")
				)
			return
		if account.account_type != "Bank":
			frappe.throw(
				_("An electronic payment reaches a bank account or a wallet, not a cash box: {0} is not one.").format(self.treasury),
				title=_("Wrong Treasury"),
			)
		check_treasury(self.branch, self.treasury)

	def check_reference(self):
		self.reference_no = clean_reference(self.reference_no)
		if not is_cash(self.payment_method) and not self.reference_no:
			frappe.throw(_("An electronic payment needs its reference number."), title=_("Reference Needed"))
		self.reference_key = f"{self.treasury}|{self.reference_no}" if self.reference_no else None
		if not self.reference_key:
			return
		# Locked first, so two people recording the same transfer at once wait for each other and the second sees it.
		frappe.db.get_value("Account", self.treasury, "name", for_update=True)
		other = frappe.db.get_value(
			"App Payment", {"reference_key": self.reference_key, "name": ("!=", self.name or "")}, "name", for_update=True
		)
		if other:
			frappe.throw(
				_("Reference {0} into {1} is already recorded: {2}.").format(self.reference_no, self.treasury, other),
				title=_("Already Recorded"),
			)

	def on_submit(self):
		frappe.db.get_value("App Payment", self.name, "name", for_update=True)
		if frappe.db.get_value("App Payment", self.name, "journal_entry"):
			return
		self.db_set("journal_entry", self.post())

	def post(self):
		company = frappe.db.get_value("Account", self.treasury, "company")
		abbr = frappe.get_cached_value("Company", company, "abbr")
		electronic = not is_cash(self.payment_method)
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Bank Entry" if electronic else "Cash Entry",
				"company": company,
				"posting_date": self.posting_date,
				"cheque_no": self.reference_no if electronic else None,
				"cheque_date": self.posting_date if electronic else None,
				"user_remark": _("{0}: {1} paid {2} for {3} ({4}), held for {5}.").format(
					self.name, self.student, _(self.payment_method), self.course, self.subscription, self.doctor
				),
				"accounts": [
					{"account": self.treasury, "debit_in_account_currency": self.amount, "cost_center": self.branch},
					{"account": f"{HELD_ACCOUNT} - {abbr}", "credit_in_account_currency": self.amount, "cost_center": self.branch},
				],
			}
		)
		# The payment is the gate: whoever may submit it posts its entry (its treasury is checked above and again by
		# the entry's own hooks, treasuries.check_entry_treasuries).
		entry.flags.ignore_permissions = True
		entry.flags.from_app_payment = True
		entry.insert()
		entry.submit()
		return entry.name

	def before_cancel(self):
		frappe.only_for(CANCEL_ROLES)
		if not clean_reason(self.cancel_reason):
			frappe.throw(_("Cancelling a payment needs a reason."), title=_("Reason Needed"))

	def on_cancel(self):
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
			entry = frappe.get_doc("Journal Entry", self.journal_entry)
			entry.flags.ignore_permissions = True
			entry.flags.from_app_payment = True
			entry.cancel()
		# The reference may be recorded again, corrected (an amendment); an imported id never: BA Plus would send it
		# again on the next import.
		self.db_set("reference_key", None)


@frappe.whitelist(methods=["POST"])
def cancel_payment(name, reason):
	"""Cancel a submitted payment: the accountant, with a reason; its entry is reversed and both stay on record."""
	frappe.only_for(CANCEL_ROLES)
	reason = clean_reason(reason)
	if not reason:
		frappe.throw(_("Cancelling a payment needs a reason."), title=_("Reason Needed"))
	doc = frappe.get_doc("App Payment", name)
	doc.check_permission("cancel")
	doc.cancel_reason = reason
	doc.cancel()
	return doc.name


@frappe.whitelist(methods=["POST"])
def import_payment(data):
	"""A payment from BA Plus (INT-05, once the app's interface is agreed): created and submitted once per its id there.
	Sent again, the payment already recorded is returned and nothing is posted twice. Returns (name, created)."""
	frappe.only_for(IMPORT_ROLES)
	data = frappe._dict(frappe.parse_json(data))
	if not data.external_id:
		frappe.throw(_("A payment imported from BA Plus needs its id there."))
	key = f"BA Plus:{data.external_id}"
	existing = frappe.db.get_value("App Payment", {"import_key": key}, "name")
	if existing:
		return existing, False
	doc = frappe.get_doc(
		{
			"doctype": "App Payment",
			**{f: data.get(f) for f in ("subscription", "posting_date", "branch", "payment_method", "treasury", "amount", "reference_no", "remarks")},
			"external_id": data.external_id,
		}
	)
	doc.flags.from_import = True
	frappe.db.savepoint("app_payment_import")
	try:
		doc.insert()
	except frappe.UniqueValidationError:
		# The same id sent twice at once: the other request recorded it.
		frappe.db.rollback(save_point="app_payment_import")
		return frappe.db.get_value("App Payment", {"import_key": key}, "name"), False
	doc.submit()
	return doc.name, True


def block_cancel_of_payment_entry(doc, method=None):
	"""Journal Entry before_cancel hook: a payment's entry is reversed only by cancelling the payment."""
	if doc.flags.from_app_payment:
		return
	payment = frappe.db.get_value("App Payment", {"journal_entry": doc.name, "docstatus": 1}, "name")
	if payment:
		frappe.throw(_("{0} was posted by App Payment {1}. Cancel the payment instead.").format(doc.name, payment))
