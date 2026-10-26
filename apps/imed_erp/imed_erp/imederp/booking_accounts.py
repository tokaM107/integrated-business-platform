# A booking's money, through ERPNext's own documents (STU-03, ACC-04, HAL-12). Nothing is written to the ledger
# by hand: each document posts itself, and is cancelled (reversed) the usual way (ACC-07).
#
#   deposit / payment   a Payment Entry from the customer into the booking's business's cash box (the halls' into
#                       خزينة سنتر Imed, the studio's into خزينة X Studio, imederp/treasuries.py), or into one of
#                       the group's wallets. Before the invoice it is an advance of the customer; after it, a payment
#                       of the invoice. Each names its booking (Payment Entry > Booking).
#                       A hall takes no deposit (requirements 4.9, question 2): a hall is paid after its invoice.
#   completed           Completed makes the booking's Sales Invoice, once: the booking's lines, at the prices kept on
#                       the booking, into the business's income account, with the booking's deposits taken off it
#                       as advances. ERPNext then shows what is still owed on the invoice.
#   revenue share       Completed records what was collected from the attendees: one Journal Entry, into the
#                       halls' cash box, the center's share to إيراد القاعات and the lecturer's to
#                       مستحقات للمحاضرين (owed to the lecturer, a supplier); neither an expense nor the center's
#                       income. The extras, if any, are invoiced to the customer as above.
#
# Amount Paid on a booking is what its Payment Entries brought in, kept up to date by their submit and cancel.
# Imported bookings keep the booking system's amounts and post nothing (where their money is taken is open,
# requirements question 11).
#
# Posted in the system's name (imederp/system_user.py), after the booking's own checks: a branch manager records
# the payments of their business's bookings, not entries on any account.

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt, getdate, today

from imed_erp.imederp.booking_pricing import ONCE, PIECE_PER_HOUR, REVENUE_SHARE, revenue_share
from imed_erp.imederp.system_user import as_administrator
from imed_erp.imederp.treasuries import BUSINESS_TREASURY, WALLETS, plain

# Business (cost center) -> its income account, without the company abbreviation (setup_coa.py).
BUSINESS_INCOME = {
	"قاعات Imed": "إيراد القاعات",
	"استوديو X": "إيراد X Studio",
}
LECTURERS_PAYABLE = "مستحقات للمحاضرين"

CUSTOM_FIELDS = {
	"Payment Entry": [
		{
			"fieldname": "custom_booking",
			"fieldtype": "Link",
			"label": "Booking",
			"options": "Booking",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "party_name",
			"description": "The booking this deposit or payment is for (ACC-04).",
		},
		{
			"fieldname": "custom_booking_request",
			"fieldtype": "Data",
			"label": "Booking Payment Request",
			"hidden": 1,
			"read_only": 1,
			"no_copy": 1,
			"unique": 1,
			"insert_after": "custom_booking",
			"description": "One payment per click: the same request sent twice records it once.",
		},
	],
	"Sales Invoice": [
		{
			"fieldname": "custom_booking",
			"fieldtype": "Link",
			"label": "Booking",
			"options": "Booking",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "customer",
		},
	],
	"Journal Entry": [
		{
			"fieldname": "custom_booking",
			"fieldtype": "Link",
			"label": "Booking",
			"options": "Booking",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "voucher_type",
		},
	],
}


def make_custom_fields():
	"""after_install / after_migrate hook."""
	create_custom_fields(CUSTOM_FIELDS, update=True)


def company_of(cost_center):
	return frappe.db.get_value("Cost Center", cost_center, "company")


def full_name(name, company):
	return f"{name} - {frappe.get_cached_value('Company', company, 'abbr')}"


def business_account(mapping, cost_center, what):
	company = company_of(cost_center)
	name = mapping.get(plain(cost_center, frappe.get_cached_value("Company", company, "abbr")))
	account = name and full_name(name, company)
	if not account or not frappe.db.exists("Account", account):
		frappe.throw(
			_("{0} has no {1} set (imederp/{2}). Ask the accountant.").format(
				cost_center, what, "treasuries.py" if mapping is BUSINESS_TREASURY else "booking_accounts.py"
			),
			title=_("Missing Account"),
		)
	return account


def treasury_of(cost_center):
	"""The business's own cash box (ACC-04)."""
	return business_account(BUSINESS_TREASURY, cost_center, _("cash box"))


def income_account_of(cost_center):
	return business_account(BUSINESS_INCOME, cost_center, _("income account"))


def allowed_accounts(cost_center):
	company = company_of(cost_center)
	return [treasury_of(cost_center)] + [
		full_name(w, company) for w in WALLETS if frappe.db.exists("Account", full_name(w, company))
	]


def mode_account(mode_of_payment, company):
	return frappe.db.get_value(
		"Mode of Payment Account", {"parent": mode_of_payment, "company": company}, "default_account"
	)


def default_mode_of_payment(cost_center):
	"""The payment method whose account is the business's cash box (نقدي — استوديو X...)."""
	company, treasury = company_of(cost_center), treasury_of(cost_center)
	modes = frappe.get_all(
		"Mode of Payment Account", filters={"company": company, "default_account": treasury}, pluck="parent"
	)
	modes = [m for m in modes if frappe.db.get_value("Mode of Payment", m, "enabled")]
	if not modes:
		frappe.throw(
			_(
				"No payment method puts money into {0}. Ask the accountant to set one (Mode of Payment > Accounts)."
			).format(treasury),
			title=_("Missing Payment Method"),
		)
	return sorted(modes)[0]


def check_payment_account(cost_center, mode_of_payment):
	"""The account a payment goes into: the booking's business's cash box or a group wallet, never another
	business's cash box (a studio deposit into the halls' cash box)."""
	account = mode_account(mode_of_payment, company_of(cost_center))
	if not account:
		frappe.throw(
			_("{0} has no account for the company. Ask the accountant.").format(mode_of_payment),
			title=_("Missing Account"),
		)
	allowed = allowed_accounts(cost_center)
	if account not in allowed:
		frappe.throw(
			_("{0} puts money into {1}, which is not {2}'s cash box. Use: {3}.").format(
				mode_of_payment, account, cost_center, ", ".join(allowed)
			),
			title=_("Wrong Cash Box"),
		)
	return account


# ---------- What was paid ----------


def payments_total(booking):
	"""What the booking's submitted Payment Entries brought in (money paid back out counts against it)."""
	value = frappe.db.sql(
		"""select coalesce(sum(case when payment_type = 'Receive' then paid_amount else -paid_amount end), 0)
		from `tabPayment Entry` where custom_booking = %s and docstatus = 1""",
		booking,
	)[0][0]
	return flt(value, 2)


def posted(doctype, booking):
	return frappe.db.get_value(doctype, {"custom_booking": booking, "docstatus": 1}, "name")


def refresh_booking(name):
	"""Amount Paid, Remaining and the posted documents of a booking, from the documents themselves."""
	booking = frappe.db.get_value(
		"Booking", name, ["source", "status", "total_amount", "resource_type", "rental_model"], as_dict=True
	)
	if not booking or booking.source == "Imported":
		return
	paid = payments_total(name)
	values = {
		"paid_amount": paid,
		"outstanding_amount": flt(flt(booking.total_amount) - paid, 2),
		"sales_invoice": posted("Sales Invoice", name),
		"journal_entry": posted("Journal Entry", name),
	}
	# A deposit makes a booking "confirmed with a deposit" (STU-08); without any left it is tentative again.
	if booking.status == "Tentative" and paid > 0 and not values["sales_invoice"]:
		values["status"] = "Confirmed with Deposit"
	elif booking.status == "Confirmed with Deposit" and paid <= 0:
		values["status"] = "Tentative"
	frappe.db.set_value("Booking", name, values, update_modified=False)


def on_posted_change(doc, method=None):
	"""on_submit / on_cancel of Payment Entry, Sales Invoice and Journal Entry: a booking's figures follow its
	documents, whoever submits or cancels them."""
	if doc.get("custom_booking"):
		refresh_booking(doc.custom_booking)


def guard_booking_link(doc, method=None):
	"""Payment Entry validate (SEC-13): a payment names a booking only through record_payment, which checks the
	booking (not imported, cancelled or a no-show; not more than is owed; its business's cash box). One made
	through the API or the form with the field set would skip all of that and still count on the booking."""
	if not doc.get("custom_booking") or doc.flags.from_booking:
		return
	before = doc.get_doc_before_save()
	if doc.is_new() or not before or before.get("custom_booking") != doc.custom_booking:
		frappe.throw(
			_("A booking's payment is recorded from the booking (Record Payment), not by naming it on a payment."),
			title=_("Not Allowed"),
		)


# ---------- Recording a payment ----------


@frappe.whitelist()
def record_payment(booking, amount, mode_of_payment=None, request_id=None, reference_no=None):
	"""A deposit or payment of a booking, into its business's cash box or a group wallet. A wallet or bank payment
	names its transaction (reference_no), as ERPNext requires. Returns the Payment Entry."""
	from imed_erp.imederp.doctype.booking.booking import check_own_business

	doc = frappe.get_doc("Booking", booking)
	doc.check_permission("write")
	check_own_business(doc.cost_center)
	if request_id and frappe.db.exists("Payment Entry", {"custom_booking_request": request_id}):
		return frappe.db.get_value("Payment Entry", {"custom_booking_request": request_id}, "name")
	if doc.source == "Imported":
		frappe.throw(_("{0} was imported: its payments are recorded in the booking system.").format(doc.name))
	if doc.resource_type == "Hall" and doc.rental_model == "Not Billable":
		frappe.throw(_("{0} is not billable: nothing is paid on it.").format(doc.name), title=_("Not Billable"))
	if doc.status in ("Cancelled", "No Show"):
		frappe.throw(_("{0} is {1}: it takes no payment.").format(doc.name, _(doc.status)))
	amount = flt(amount, 2)
	if amount <= 0:
		frappe.throw(_("Enter the amount paid, more than zero."), title=_("Missing Amount"))

	# Two payments of the same booking at once: the second waits here. The first writes the booking (its Amount
	# Paid), so MariaDB refuses the second's locking read (innodb_snapshot_isolation, as for overlaps, booking.py)
	# and it is sent again: it then sees the first, and is not more than what is left. The same request sent again
	# returns the payment already recorded; the unique request id is the last guard against a second one.
	frappe.db.get_value("Booking", doc.name, "name", for_update=True)
	if request_id and frappe.db.exists("Payment Entry", {"custom_booking_request": request_id}):
		return frappe.db.get_value("Payment Entry", {"custom_booking_request": request_id}, "name")
	invoice = posted("Sales Invoice", doc.name)
	if not invoice and doc.resource_type == "Hall":
		frappe.throw(
			_("A hall booking takes no deposit. It is paid after it is completed, against its invoice."),
			title=_("No Deposit for Halls"),
		)
	outstanding = flt(flt(doc.total_amount) - payments_total(doc.name), 2)
	if amount > outstanding:
		frappe.throw(
			_("{0} is more than what is left to pay on {1}: {2}.").format(amount, doc.name, outstanding),
			title=_("More Than Owed"),
		)
	mode_of_payment = mode_of_payment or default_mode_of_payment(doc.cost_center)
	account = check_payment_account(doc.cost_center, mode_of_payment)
	company = company_of(doc.cost_center)
	bank = frappe.db.get_value("Mode of Payment", mode_of_payment, "type") == "Bank"
	if bank and not (reference_no or "").strip():
		frappe.throw(
			_("Enter the transaction number of the {0} payment.").format(mode_of_payment),
			title=_("Missing Value"),
		)

	with as_administrator():
		if invoice:
			from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

			payment = get_payment_entry("Sales Invoice", invoice, party_amount=amount)
			payment.references[0].allocated_amount = amount
		else:
			from erpnext.accounts.party import get_party_account

			payment = frappe.get_doc(
				{
					"doctype": "Payment Entry",
					"payment_type": "Receive",
					"company": company,
					"party_type": "Customer",
					"party": doc.customer,
					"paid_from": get_party_account("Customer", doc.customer, company),
				}
			)
		payment.update(
			{
				"posting_date": today(),
				"mode_of_payment": mode_of_payment,
				"paid_to": account,
				"paid_to_account_currency": frappe.db.get_value("Account", account, "account_currency"),
				"paid_amount": amount,
				"received_amount": amount,
				"cost_center": doc.cost_center,
				"custom_booking": doc.name,
				"custom_booking_request": request_id or None,
				"reference_no": (reference_no or "").strip() or None,
				"reference_date": today() if bank else None,
				"remarks": _("Booking {0}: {1}").format(doc.name, _("payment") if invoice else _("deposit")),
			}
		)
		payment.setup_party_account_field()
		payment.set_missing_values()
		payment.flags.from_booking = True
		payment.insert()
		payment.submit()
	return payment.name


# ---------- Completed: the invoice, or the revenue share ----------


def invoice_lines(doc):
	income, cost_center = income_account_of(doc.cost_center), doc.cost_center

	def line(item, qty, rate, amount=None):
		"""A line of the booking's amount. A part of an hour (1.5 hours) on an item counted in whole units (Nos)
		is one unit at the amount, the hours and price in its description: ERPNext refuses 1.5 Nos."""
		uom = frappe.get_cached_value("Item", item, "stock_uom")
		row = {
			"item_code": item,
			"qty": qty,
			"rate": rate,
			"uom": uom,
			"conversion_factor": 1,
			"income_account": income,
			"cost_center": cost_center,
		}
		if flt(qty) != int(flt(qty)) and frappe.get_cached_value("UOM", uom, "must_be_whole_number"):
			name = frappe.get_cached_value("Item", item, "item_name")
			row.update(
				{"qty": 1, "rate": flt(amount if amount is not None else qty * rate, 2), "description": f"{name}: {flt(qty, 2)} x {flt(rate, 2)}"}
			)
		return row

	# QA-13: an hourly line bills the amount the booking was priced at, from its exact length; the hours shown
	# are rounded, so the rate is the amount over them (40 minutes: 0.67 x 2,238.81 = 1,500).
	by_hours = lambda item, qty, amount: line(item, qty, rate_for(amount, qty), amount)
	lines = []
	if flt(doc.base_amount):
		if doc.get("hour_package"):
			# Only the hours beyond the prepaid package: the package's own invoice billed the rest.
			lines.append(by_hours(frappe.db.get_value("Booking Resource", doc.resource, "item"), flt(doc.extra_hours, 2), flt(doc.base_amount)))
		elif doc.package:
			package = frappe.get_doc("Booking Package", doc.package)
			lines.append(
				line(package.item, 1, flt(doc.base_amount))
				if package.charged == ONCE
				else by_hours(package.item, flt(doc.hours, 2), flt(doc.base_amount))
			)
		else:
			lines.append(by_hours(frappe.db.get_value("Booking Resource", doc.resource, "item"), flt(doc.hours, 2), flt(doc.base_amount)))
	for row in doc.extras:
		if row.charged == PIECE_PER_HOUR:
			lines.append(by_hours(row.item, row.quantity * flt(doc.hours, 2), flt(row.amount)))
		else:
			lines.append(line(row.item, row.quantity, flt(row.rate)))
	return lines


def rate_for(amount, qty):
	"""The rate, to the piastre, that bills `amount` for `qty`: the closest one whose qty x rate rounds to it."""
	if not flt(qty):
		return flt(amount, 2)
	rate = flt(amount / qty, 2)
	for step in (0, 0.01, -0.01, 0.02, -0.02):
		if flt(flt(rate + step, 2) * qty, 2) == flt(amount, 2):
			return flt(rate + step, 2)
	return rate


def advances(doc, total):
	"""The booking's deposits not yet used, taken off its invoice in the order they were paid."""
	rows, left = [], flt(total, 2)
	payments = frappe.get_all(
		"Payment Entry",
		filters={
			"custom_booking": doc.name,
			"docstatus": 1,
			"payment_type": "Receive",
			"unallocated_amount": [">", 0],
		},
		fields=["name", "unallocated_amount", "posting_date"],
		order_by="posting_date asc, creation asc",
	)
	for payment in payments:
		if left <= 0:
			break
		allocated = min(flt(payment.unallocated_amount, 2), left)
		rows.append(
			{
				"reference_type": "Payment Entry",
				"reference_name": payment.name,
				"advance_amount": flt(payment.unallocated_amount, 2),
				"allocated_amount": allocated,
				"remarks": _("Deposit of booking {0}").format(doc.name),
			}
		)
		left = flt(left - allocated, 2)
	return rows


def posting_date_of(doc):
	"""The day the service was given; a booking completed later is posted on its own day."""
	return min(getdate(doc.booking_date), getdate(today()))


def make_invoice(doc):
	lines = invoice_lines(doc)
	if not lines:
		return None
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company_of(doc.cost_center),
			"customer": doc.customer,
			"posting_date": posting_date_of(doc),
			"set_posting_time": 1,
			"due_date": posting_date_of(doc),
			"cost_center": doc.cost_center,
			"selling_price_list": doc.price_list,
			"ignore_pricing_rule": 1,
			"update_stock": 0,
			"custom_booking": doc.name,
			"remarks": _("Booking {0}").format(doc.name),
			"items": lines,
		}
	)
	invoice.set("advances", advances(doc, flt(doc.total_amount)))
	invoice.allocate_advances_automatically = 0
	invoice.flags.from_booking = True
	with as_administrator():
		invoice.insert()
		if flt(invoice.grand_total, 2) != flt(doc.total_amount, 2):
			frappe.throw(
				_("The invoice total {0} differs from the booking's {1}.").format(
					invoice.grand_total, doc.total_amount
				)
			)
		invoice.submit()
	return invoice.name


def make_revenue_share_entry(doc):
	if flt(doc.collected_amount) <= 0:
		return None
	company = company_of(doc.cost_center)
	lecturer_share, center_share = revenue_share(doc.collected_amount, doc.lecturer_share_percent)
	rows = [
		{"account": treasury_of(doc.cost_center), "debit_in_account_currency": flt(doc.collected_amount, 2)},
		{"account": income_account_of(doc.cost_center), "credit_in_account_currency": center_share},
	]
	if lecturer_share:
		rows.append(
			{
				"account": full_name(LECTURERS_PAYABLE, company),
				"credit_in_account_currency": lecturer_share,
				"party_type": "Supplier",
				"party": doc.lecturer,
			}
		)
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": company,
			"posting_date": posting_date_of(doc),
			"custom_booking": doc.name,
			"user_remark": _(
				"Booking {0}: {1} collected from {2} attendees; the lecturer's share {3}% ({4}), the center's {5}."
			).format(
				doc.name,
				flt(doc.collected_amount, 2),
				doc.attendees or 0,
				flt(doc.lecturer_share_percent),
				lecturer_share,
				center_share,
			),
			"accounts": [
				{**row, "cost_center": doc.cost_center}
				for row in rows
				if flt(row.get("debit_in_account_currency") or row.get("credit_in_account_currency"))
			],
		}
	)
	entry.flags.from_booking = True
	with as_administrator():
		entry.insert()
		entry.submit()
	return entry.name


def complete(doc):
	"""Post a completed booking, once: a booking that already has its invoice (or entry) gets no second one, however
	often it is saved as completed."""
	if doc.source == "Imported" or doc.status != "Completed":
		return
	if doc.resource_type == "Hall" and doc.rental_model == "Not Billable":
		# An internal use of the hall: no invoice, no entry; the course's or the app's own fees are posted elsewhere.
		refresh_booking(doc.name)
		return
	frappe.db.get_value("Booking", doc.name, "name", for_update=True)
	if (
		doc.resource_type == "Hall"
		and doc.rental_model == REVENUE_SHARE
		and not posted("Journal Entry", doc.name)
	):
		make_revenue_share_entry(doc)
	if not posted("Sales Invoice", doc.name):
		make_invoice(doc)
	refresh_booking(doc.name)


@frappe.whitelist()
def make_booking_invoice(booking):
	"""For a completed booking whose invoice was cancelled (to correct it): make it again."""
	from imed_erp.imederp.doctype.booking.booking import check_own_business

	doc = frappe.get_doc("Booking", booking)
	doc.check_permission("write")
	check_own_business(doc.cost_center)
	if doc.status != "Completed":
		frappe.throw(_("{0} is not completed yet.").format(doc.name))
	complete(doc)
	return frappe.db.get_value("Booking", doc.name, ["sales_invoice", "journal_entry"], as_dict=True)
