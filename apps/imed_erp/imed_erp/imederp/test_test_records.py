# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# A doctype test whose doctype links to a doctype that is missing from its IGNORE_TEST_RECORD_DEPENDENCIES makes
# Frappe build ERPNext's own "_Test ..." records for it and COMMIT them to the real site (4 Oct and 14 Oct 2026:
# test companies, accounts, items and fiscal years left on the site). This test fails as soon as one is missing,
# naming it, so the omission is caught before the change is merged.
#
# Run:
#   bench --site frontend run-tests --module imed_erp.imederp.test_test_records

import ast
import json
import os
import re

import frappe
from frappe.tests import IntegrationTestCase

DOCTYPES = frappe.get_app_path("imed_erp", "imederp", "doctype")


def doctypes():
	"""{doctype name: (folder, definition)} of the app's doctypes."""
	found = {}
	for folder in os.listdir(DOCTYPES):
		path = os.path.join(DOCTYPES, folder, f"{folder}.json")
		if os.path.exists(path):
			definition = json.load(open(path))
			found[definition["name"]] = (folder, definition)
	return found


def linked(definition, by_name, seen=None):
	"""Every doctype a document links to, its child tables' links included."""
	seen = seen or set()
	targets = set()
	for field in definition["fields"]:
		if field["fieldtype"] == "Link":
			targets.add(field["options"])
		elif field["fieldtype"] in ("Table", "Table MultiSelect") and field["options"] in by_name and field["options"] not in seen:
			seen.add(field["options"])
			targets |= linked(by_name[field["options"]][1], by_name, seen)
	return targets


class IntegrationTestTestRecords(IntegrationTestCase):
	def test_every_doctype_test_ignores_what_its_doctype_links_to(self):
		by_name = doctypes()
		for name, (folder, definition) in sorted(by_name.items()):
			test = os.path.join(DOCTYPES, folder, f"test_{folder}.py")
			if not os.path.exists(test):
				continue
			found = re.search(r"^IGNORE_TEST_RECORD_DEPENDENCIES\s*=\s*(\[.*?\])", open(test).read(), re.M | re.S)
			ignored = set(ast.literal_eval(found.group(1))) if found else set()
			with self.subTest(name):
				self.assertEqual(sorted(linked(definition, by_name) - ignored), [], f"add these to IGNORE_TEST_RECORD_DEPENDENCIES in {test}")
