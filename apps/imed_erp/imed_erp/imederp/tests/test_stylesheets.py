# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# The app's stylesheets are whole: every block that opens closes. A merge once dropped the "}" that closed an
# "@media (max-width: 991px)" block in imed_theme.css (10 Nov 2026), and every rule after it then held on phones
# only: the owner's page lost its look on a computer. Git reported no conflict, so this test is the guard.

import os
import re
import unittest

import imed_erp

CSS_DIR = os.path.join(os.path.dirname(imed_erp.__file__), "public", "css")


def unclosed(text):
	"""The line numbers of blocks opened and never closed, and of closings with nothing open (comments and strings
	set aside)."""
	text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
	text = re.sub(r"\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'", '""', text)
	opened, stray = [], []
	for number, line in enumerate(text.split("\n"), 1):
		for ch in line:
			if ch == "{":
				opened.append(number)
			elif ch == "}":
				if opened:
					opened.pop()
				else:
					stray.append(number)
	return opened, stray


class TestStylesheets(unittest.TestCase):
	def test_every_block_in_the_apps_stylesheets_closes(self):
		names = sorted(n for n in os.listdir(CSS_DIR) if n.endswith(".css"))
		self.assertTrue(names)
		for name in names:
			with open(os.path.join(CSS_DIR, name), encoding="utf-8") as f:
				opened, stray = unclosed(f.read())
			self.assertEqual((opened, stray), ([], []), f"{name}: blocks opened and not closed at lines {opened}, closings with nothing open at {stray}")
