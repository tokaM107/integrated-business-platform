# Checking two doctor statements by hand

Before the doctors' balances are trusted, the team checks two real statements: the system's figures against a
calculation made by hand from the source documents (the sales receipts, the edition's approved amount per copy,
the payout and collection receipts). The template is
[`doctor_statement_reconciliation.csv`](doctor_statement_reconciliation.csv): seven lines for each of the two
statements, all empty. **No statement has been checked yet**; the template is filled only from real documents.

| Column | Filled from |
|---|---|
| `statement` | 1 or 2. |
| `doctor`, `agreement`, `agreement_type` | The doctor and the agreement checked (one agreement per statement: agreements are never mixed, DOC-08). |
| `period_from`, `period_to` | The period checked. |
| `line` | Opening balance, the movements by kind, the closing balance. *Platform fees* is for an App agreement only. |
| `system_amount` | The **Doctor Statement** report (DOC-08) for the agreement and period: balance brought forward, each movement, balance at the end. **Doctor Receivables** gives the same figures per agreement (Opening, Accrued, Adjustments, Unsold Copies Charges, Paid, Outstanding), and its Entries link opens each movement. |
| `manual_amount` | The hand calculation: copies sold × the edition's Doctor's Amount per Copy, the payouts on their receipts, and so on. |
| `variance` | `system_amount − manual_amount`. Zero when they agree. |
| `explanation` | For every variance that is not zero: what causes it (a sale not in the system, a payout recorded on another date, ...). A variance is never closed without one. |
| `source_document` | The receipts, invoices or vouchers used for the manual figure. |
| `checked_by`, `checked_on` | Who checked and when. |

A statement is reconciled when every line's variance is zero or explained, and the explanation has been agreed
with the accountant.
