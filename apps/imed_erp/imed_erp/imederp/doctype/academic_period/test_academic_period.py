# Copyright (c) 2026, toka mohamed and Contributors
# See license.txt

# import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
# Linked records already exist on the site or are made by the tests; without this list Frappe builds
# ERPNext's "_Test ..." records and commits them to the site.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Academic Period"]



class IntegrationTestAcademicPeriod(IntegrationTestCase):
	"""
	Integration tests for AcademicPeriod.
	Use this class for testing interactions between multiple components.
	"""

	pass
