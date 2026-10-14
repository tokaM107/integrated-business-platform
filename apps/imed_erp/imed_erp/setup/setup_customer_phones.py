# Phone keys of the customers saved before CRM-04 (imederp/customers.py): one customer per phone number.
#
# Run from bench console, after `bench migrate` has added the Phone Key field:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_customer_phones.py").read(), {"frappe": frappe})
#
# Every customer saved from now on gets its key on save. This gives one to those saved before, so a new customer
# with the same number is refused. It never changes a phone number and never merges or disables a customer:
#   - a number that is not a valid phone number is listed and left without a key;
#   - a number on several customers is listed; only the oldest of them gets the key. The others can still be
#     edited, but their number cannot be changed to another taken one, until someone decides which record
#     stays (ERPNext's Rename with "Merge with existing").
# Set FILL = False to only print the report. Idempotent.

import frappe

from imed_erp.imederp.customers import PHONE_KEY, normalize_phone

FILL = True


def run():
	if not frappe.get_meta("Customer").has_field(PHONE_KEY):
		print(f"STOP   Customer has no {PHONE_KEY} field yet; run bench migrate first.")
		return

	customers = frappe.get_all(
		"Customer", fields=["name", "customer_name", "mobile_no", PHONE_KEY, "creation"], order_by="creation"
	)
	by_key, invalid = {}, []
	for c in customers:
		if not (c.mobile_no or "").strip():
			continue
		try:
			key = normalize_phone(c.mobile_no)
		except frappe.ValidationError:
			frappe.clear_messages()
			invalid.append(c)
			continue
		by_key.setdefault(key, []).append(c)

	filled = 0
	for key, same in by_key.items():
		keep = same[0]
		if keep.get(PHONE_KEY) != key:
			filled += 1
			if FILL:
				frappe.db.set_value("Customer", keep.name, PHONE_KEY, key, update_modified=False)
	if FILL:
		frappe.db.commit()

	duplicates = {key: same for key, same in by_key.items() if len(same) > 1}
	print(f"{len(customers)} customers, {sum(len(s) for s in by_key.values())} with a phone number.")
	print(f"{'Keyed' if FILL else 'Would key'} {filled} customer(s).")
	if invalid:
		print(f"\n{len(invalid)} number(s) are not valid phone numbers (left without a key, nothing changed):")
		for c in invalid:
			print(f"  - {c.name} ({c.customer_name}): {c.mobile_no!r}")
	if duplicates:
		print(f"\n{len(duplicates)} number(s) are on more than one customer (nothing merged; the first keeps the key):")
		for key, same in duplicates.items():
			print(f"  - {key}: " + ", ".join(f"{c.name} ({c.mobile_no})" for c in same))
	if not invalid and not duplicates:
		print("No duplicate or invalid phone numbers.")
	print("DONE")


run()
