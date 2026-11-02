# Copyright (c) 2026, toka mohamed and contributors
# License information in license.txt

"""What test runs left on a site (read-only): records whose name starts with `_Test`, and the users of the test
fixtures. ERPNext's test records (companies, accounts, items, warehouses) land on the development site when a
test module lacks its IGNORE_TEST_RECORD_DEPENDENCIES entry (docs/known-issues.md); a copy of the development
site carries them to production unless they are removed or the owner accepts them.

    bench --site <site> execute imed_erp.setup.list_test_records.run
"""

import frappe

DOCTYPES = (
	"Company", "Account", "Cost Center", "Warehouse", "Item", "Item Group", "Customer", "Customer Group", "Supplier",
	"Supplier Group", "Price List", "Item Price", "Territory", "Department", "Employee", "Project", "Sales Taxes and Charges Template",
	"Fiscal Year", "Mode of Payment", "Booking Resource", "Booking", "Doctor Agreement", "Book Edition",
)
TEST_USERS_LIKE = ("test%@example.com", "%@abc.com", "testdelete@%", "testpassword@%", "testperm@%")


def run():
	out = {}
	for doctype in DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		count = frappe.db.count(doctype, {"name": ("like", "_Test%")})
		if count:
			out[doctype] = count
	users = []
	for pattern in TEST_USERS_LIKE:
		users += frappe.get_all("User", filters={"name": ("like", pattern), "enabled": 1}, pluck="name")
	out["enabled test users"] = sorted(set(users))
	out["companies"] = frappe.get_all("Company", pluck="name")
	return out
