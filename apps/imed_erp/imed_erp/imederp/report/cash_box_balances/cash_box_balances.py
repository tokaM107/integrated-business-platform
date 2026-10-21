# Copyright (c) 2026, toka mohamed and contributors
# For license information, please see license.txt

# What is in each cash box and wallet now, from the ledger (imederp/owner_figures.py). On the Owner Dashboard as a
# chart, and opened as a table from the sidebar (Financial Reports).

from frappe import _

from imed_erp.imederp.owner_figures import cash_box_balances, check_reader

# Words that say what kind of account it is, not which one: left out under the chart's bars.
KIND_WORDS = ("الخزينة", "خزينة", "مكتبة", "محفظة", "تطبيق")


def short_name(account):
	"""خزينة مكتبة الأزاريطة - MMG -> الأزاريطة: the chart has room for about one word under each bar (the full
	name is in the table and on hover)."""
	name = account.rsplit(" - ", 1)[0]
	words = [w for w in name.split() if w not in KIND_WORDS]
	return " ".join(words) or name


def execute(filters=None):
	check_reader()
	columns = [
		{
			"fieldname": "account",
			"label": _("Cash Box"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 280,
		},
		{"fieldname": "balance", "label": _("Balance"), "fieldtype": "Currency", "width": 180},
	]
	rows = [{"account": account, "balance": value} for account, value in cash_box_balances()]
	chart = {
		"data": {
			"labels": [short_name(row["account"]) for row in rows],
			"datasets": [{"name": _("Balance"), "values": [row["balance"] for row in rows]}],
		},
		"type": "bar",
		"fieldtype": "Currency",
		"colors": ["#0f766e"],
	}
	return columns, rows, None, chart
