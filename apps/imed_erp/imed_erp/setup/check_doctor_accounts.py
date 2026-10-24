# Read-only. Do the doctors' ledgers and the general ledger agree (QA-02)? Changes nothing.
#
# Run from bench console:
#   exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/check_doctor_accounts.py").read(), {"frappe": frappe})
#
# For every submitted Doctor Ledger Entry:
#   - it has a journal entry, submitted, for its own amount (a sale's accrual shares its invoice's journal entry,
#     which carries one pair of lines per invoice line: its amount is checked against its own pair);
#   - an entry with no journal entry is listed: it moved the doctor's balance but not the accounts. Entries made
#     before 20 Oct 2026 by hand (adjustments, accruals, charges) have none; each needs a journal entry by hand,
#     or cancelling and entering again, decided by the accountant. This script does neither.
# Then, for each agreement, the balance worked out from its entries against the stored Balance.
# And every charge for unsold copies is listed: the doctor is never charged for them (owner, 21 Oct 2026); a
# draft is rejected, a submitted one cancelled, by an approver.

import frappe
from frappe.utils import flt

LEDGER = "Doctor Ledger Entry"
problems = []


def report(kind, row, detail):
	problems.append(kind)
	print(f"{kind:<22} {row.name}  {row.agreement}  {row.entry_type} {flt(row.amount):,.2f}  {detail}")


entries = frappe.get_all(
	LEDGER,
	filters={"docstatus": 1},
	fields=["name", "agreement", "entry_type", "amount", "journal_entry", "sales_invoice", "entry_date"],
	order_by="entry_date, creation",
)
for row in entries:
	if not row.journal_entry:
		report("NO JOURNAL ENTRY", row, f"dated {row.entry_date}")
		continue
	if frappe.db.get_value("Journal Entry", row.journal_entry, "docstatus") != 1:
		report("JOURNAL NOT POSTED", row, row.journal_entry)
		continue
	if not row.sales_invoice:
		moved = flt(
			frappe.db.sql(
				"select sum(debit) from `tabGL Entry` where voucher_no = %s and is_cancelled = 0", row.journal_entry
			)[0][0]
		)
		if abs(moved - abs(flt(row.amount))) > 0.01:
			report("AMOUNT DIFFERS", row, f"{row.journal_entry} moves {moved:,.2f}")

from imed_erp.imederp.doctype.doctor_agreement.doctor_agreement import get_balance

for agreement in frappe.get_all("Doctor Agreement", filters={"docstatus": 1}, fields=["name", "balance"]):
	worked_out = flt(get_balance(agreement.name), 2)
	if abs(worked_out - flt(agreement.balance)) > 0.01:
		problems.append("BALANCE")
		print(f"{'BALANCE DIFFERS':<22} {agreement.name}: stored {flt(agreement.balance):,.2f}, entries {worked_out:,.2f}")

for row in frappe.get_all(
	LEDGER,
	filters={"entry_type": "Unsold Copies Charge", "docstatus": ("<", 2)},
	fields=["name", "agreement", "entry_type", "amount", "docstatus", "approval_status"],
):
	report("UNSOLD COPIES CHARGE", row, f"docstatus {row.docstatus}, {row.approval_status or ''}: reject or cancel (owner, 21 Oct 2026)")

print(f"\n{len(entries)} submitted entries checked; {len(problems)} to look at.")
