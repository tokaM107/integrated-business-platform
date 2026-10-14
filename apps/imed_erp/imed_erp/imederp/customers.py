# One customer record per person (CRM-01, CRM-02, CRM-04).
#
# Requirements v1.2:
#   CRM-01  the customer's name, phone, college, year (الفرقة) and category (student / doctor).
#   CRM-02  the customer's full history across the businesses: one record, so every sale, payment and booking
#           points at it (ERPNext's Customer > Connections lists them).
#   CRM-04  no second customer record with the same phone number.
#
# The phone is ERPNext's own: the customer's primary contact holds it, and Customer > Mobile No shows it. It is
# kept as it was typed; next to it, custom_phone_key holds one spelling of the same number (+201012345678 for
# 01012345678, +20 10 1234 5678, 00201012345678, ٠١٠١٢٣٤٥٦٧٨ ...). That column is unique in the database, so two
# people saving the same number at the same moment cannot both succeed; the check in validate only gives the
# clearer message, naming the customer the number belongs to.
#
# A customer may be saved without a phone (walk-in buyers, مشتري التالف): no policy says otherwise, so a blank
# number is allowed and is never a duplicate. See docs/known-issues.md, "Customers".
#
# hooks.py runs:
#   Customer validate   set_phone_key      the new or changed number is checked and keyed
#   Contact validate    check_contact_phone  a number changed on the customer's contact is checked too
#   Contact on_update   sync_contact_phone   ... and reaches the customer, which then shows it
# Customers saved before this existed get their key from setup/setup_customer_phones.py, which reports the
# duplicates already there instead of merging them.

import re

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cstr, escape_html

PHONE_KEY = "custom_phone_key"
EGYPT = "20"
# Mobile numbers: 010, 011, 012 and 015, then 8 digits. Landlines: an area code (2 for Cairo, 3 for Alexandria,
# two digits elsewhere) and the number, 8 or 9 digits without the leading 0.
EGYPT_MOBILE = re.compile(r"1[0125]\d{8}")
EGYPT_LANDLINE = re.compile(r"[2-9]\d{7,8}")
# Arabic-Indic and Persian digits, as typed on an Arabic keyboard.
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

CUSTOM_FIELDS = {
	"Customer": [
		{
			"fieldname": "custom_college",
			"fieldtype": "Data",
			"label": "College",
			"insert_after": "customer_group",
		},
		{
			"fieldname": "custom_academic_year",
			"fieldtype": "Data",
			"label": "Academic Year",
			"insert_after": "custom_college",
		},
		{
			"fieldname": PHONE_KEY,
			"fieldtype": "Data",
			"label": "Phone Key",
			"description": "The mobile number in one spelling (+20...), so the same number cannot be on two customers.",
			"insert_after": "mobile_no",
			"unique": 1,
			"read_only": 1,
			"hidden": 1,
			"no_copy": 1,
			"print_hide": 1,
		},
	],
}


def make_custom_fields():
	"""after_install / after_migrate hook."""
	create_custom_fields(CUSTOM_FIELDS, update=True)


def normalize_phone(value):
	"""The phone number in one spelling, '+20' and the national number for Egypt; None when blank.
	Refuses what cannot be a phone number, rather than keying it wrongly."""
	raw = cstr(value).translate(DIGITS).strip()
	if not raw:
		return None
	if re.search(r"[^\d\s+\-().]", raw) or "+" in raw[1:]:
		invalid_phone(value)

	digits = re.sub(r"\D", "", raw)
	international = raw.startswith("+")
	if digits.startswith("00"):
		international, digits = True, digits[2:]

	if international and not digits.startswith(EGYPT):
		# Another country's number: kept as dialled, with its country code.
		if not 8 <= len(digits) <= 15:
			invalid_phone(value)
		return "+" + digits

	if international:
		national = digits[len(EGYPT) :]
	elif re.fullmatch(EGYPT + EGYPT_MOBILE.pattern, digits):
		# 201012345678: the country code typed without its plus.
		national = digits[len(EGYPT) :]
	else:
		national = digits
	if national.startswith("0"):
		# The trunk 0 of a local number, also when typed after +20 (+20 010...).
		national = national[1:]
	if not (EGYPT_MOBILE.fullmatch(national) or EGYPT_LANDLINE.fullmatch(national)):
		invalid_phone(value)
	return "+" + EGYPT + national


def invalid_phone(value):
	frappe.throw(
		_("{0} is not a valid phone number. Type an Egyptian number such as 01012345678, or a foreign one with its country code, such as +966...").format(
			frappe.bold(escape_html(cstr(value)))
		),
		title=_("Invalid Phone Number"),
	)


def phone_key_or_none(value):
	"""normalize_phone, or None for a number that is not valid, without a message to the user."""
	try:
		return normalize_phone(value)
	except frappe.ValidationError:
		frappe.clear_last_message()
		return None


def customer_with_phone(key, exclude=None):
	if not key:
		return None
	filters = {PHONE_KEY: key}
	if exclude:
		filters["name"] = ["!=", exclude]
	return frappe.db.get_value("Customer", filters, ["name", "customer_name"], as_dict=True)


def refuse_duplicate(value, key, exclude=None):
	other = customer_with_phone(key, exclude)
	if other:
		frappe.throw(
			_("The phone number {0} already belongs to customer {1}. Choose that customer instead of adding another one.").format(
				frappe.bold(escape_html(cstr(value))),
				frappe.utils.get_link_to_form("Customer", other.name, escape_html(cstr(other.customer_name))),
			),
			title=_("Customer Already Exists"),
			exc=frappe.DuplicateEntryError,
		)


def set_phone_key(doc, method=None):
	"""Customer validate hook."""
	if not cstr(doc.get("mobile_no")).strip():
		# Spaces only: no number (ERPNext would otherwise make the contact an empty phone row and refuse it).
		doc.mobile_no = None
	if not doc.is_new() and not doc.has_value_changed("mobile_no"):
		# The number is as it was. A customer saved before CRM-04 may have an invalid number or one another
		# customer has; that is no reason to refuse an edit of its name or address (setup_customer_phones.py
		# lists those for a decision). It gets its key once the number is valid and free.
		if not doc.get(PHONE_KEY):
			key = phone_key_or_none(doc.get("mobile_no"))
			if key and not customer_with_phone(key, exclude=doc.name):
				doc.set(PHONE_KEY, key)
		return
	key = normalize_phone(doc.get("mobile_no"))
	refuse_duplicate(doc.get("mobile_no"), key, exclude=None if doc.is_new() else doc.name)
	doc.set(PHONE_KEY, key)


def customers_of(contact):
	"""The customers this contact is the primary contact of: the ones whose Mobile No it gives."""
	names = [link.link_name for link in contact.get("links") or [] if link.link_doctype == "Customer"]
	if not names:
		return []
	return frappe.get_all(
		"Customer", filters={"name": ["in", names], "customer_primary_contact": contact.name}, pluck="name"
	)


def check_contact_phone(doc, method=None):
	"""Contact validate hook: a number changed on a customer's own contact is checked like one typed on the
	customer, before it is saved."""
	if doc.is_new() or not doc.has_value_changed("mobile_no"):
		# A new contact is made for a new customer, which was checked already; an unchanged number is not
		# checked again.
		return
	customers = customers_of(doc)
	if not customers:
		# Not a customer's own contact (a supplier's, a user's...): no rule on its number here.
		return
	key = normalize_phone(doc.get("mobile_no"))
	for customer in customers:
		refuse_duplicate(doc.get("mobile_no"), key, exclude=customer)


def sync_contact_phone(doc, method=None):
	"""Contact on_update hook: the customer shows its primary contact's number (ERPNext fetches it only when the
	customer itself is saved). The unique key refuses a number another customer took meanwhile."""
	customers = customers_of(doc)
	if not customers:
		return
	key = phone_key_or_none(doc.get("mobile_no"))
	for customer in customers:
		current = frappe.db.get_value("Customer", customer, ["mobile_no", PHONE_KEY], as_dict=True)
		if cstr(current.mobile_no) != cstr(doc.mobile_no) or current.get(PHONE_KEY) != key:
			frappe.db.set_value("Customer", customer, {"mobile_no": doc.mobile_no, PHONE_KEY: key})
