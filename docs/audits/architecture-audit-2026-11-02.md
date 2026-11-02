# Repository-wide architecture audit and refactor, 2 Nov 2026

Branch `feature/assistant-chats`. Nothing pushed, merged or deployed; no production data read or changed (a
read-only check of production's default company was refused by the sandbox, so the 1 Nov audit's verification is
relied on). Every change below has a test that fails without it, unless the row says otherwise.

## Status by module

Status words: **Refactored** (code changed, tests added, suite green), **Audited only** (findings recorded, nothing
changed), **Blocked** (needs a decision or a browser check).

| Module | Status | Changed | Tests added | Remaining |
|---|---|---|---|---|
| AI assistant | Refactored (earlier commits 5a62d54, 9ec0970) | read-only connection guard, company binding of chats, company scoping of records, data delimiting | 40 assistant tests | see "Assistant readiness" |
| Bookings, halls, studio packages | Refactored (533817c, c616ab7) | one source of the booking vocabulary (`imederp/booking_rules.py`) in ten modules; imported packages never billed; package billed by its own business; availability answers for one's own business; hall report reads invoices once | 6 | JS copies of status colours (3 files); `booking_accounts` status flip without validation; studio package invoice inserted as the user |
| XStudio sync | Audited; one fix through bookings | the mirror of an imported package is now safe (an imported package cannot be invoiced here) | covered by package test | broad `except` blocks; per-row queries |
| Accounting, cash closing, dashboards | Refactored (a46bba0) | one company for the owner's figures; dashboard ledger totals leave out opening and closing entries like the other two computations; unpaid-on-bookings without N+1; discrepancy count and receiver search permission-checked; weekly review locked like the daily close; receivables Kind filter; role names in `imederp/roles.py` | 6 | five cash-balance computations; two closed-day checks; account names as Arabic constants; four-eyes gaps (owner decision) |
| Library, POS, printing, stock, doctors | Refactored (this pass) | purchases cannot fill the damaged store; sold quantities re-read with locking reads; doctor summary through `get_list`; three crashes on missing records; dead imports; comments contradicting the unsold-copies rule | 1 (+ existing suites) | library maps typed in four places; five per-sheet cost formulas; four signed-balance copies; paper use check-then-submit race; doctor accrual check-then-insert race |
| BA Plus | Refactored (this pass) | one subscription per student and course under concurrency (course locked first); re-import is POST-only and no longer reports files a dropped run rolled back; cancel button shown to every role the server allows | 2 | two import-key formats (changing them touches stored keys: decision); schedule submit re-posts every open course in one request; N+1 in the importer |
| Infrastructure (hooks, guards) | Refactored (this pass) | period lock list read from hooks.py; custom-field hooks listed once; App Payment, Cash Handover, Studio Hour Package in the delete-guard test; 200 lines of Frappe scaffolding removed (hook values verified identical) | guard test now covers 3 more doctypes | `*` doc_events on every submit; translator helpers copied in 3 JS files |
| Frontend JS | Audited only | one role check aligned (App Payment) | none (no JS test runner) | booking.js, stock_count.js, damaged stock forms recompute server values for display; role matrix copied in imed_form_standard.js (display only) |

## Business rules kept

No financial calculation, booking rule, inventory behaviour, cash reconciliation rule or synchronisation ownership
changed. Three changes make code obey a rule it was meant to obey:

- The dashboard's own ledger totals now leave out the year's closing voucher and opening entries, as the ledger
  cards and the owner's reports already did. Before, the month containing a year-end close would read differently
  on two cards of the same page.
- A purchase can no longer put stock into the damaged store, the rule already enforced on sales, stock entries and
  delivery notes.
- Outstanding Receivables shows only the kind asked for.

## Decisions for the owner (not changed)

- An accountant alone can withdraw a recovery the owner approved, and can write off a shortage awaiting the owner.
  Changing that changes who may do what.
- Two import-key formats for BA Plus records. Unifying them rewrites stored keys.
- Cash handover amount in words is fixed to EGP.

## Assistant readiness

| Risk | State |
|---|---|
| Cross-company memory | Closed: a saved chat is bound to its company and refused in another; tested. |
| Raw SQL writes bypassing the guard | Closed for every path through `frappe.db` (the guard sits on `execute_query`); tested with raw UPDATE, DELETE, query builder, `set_value`, insert and commit. Open: code that reaches the driver cursor directly would bypass it; no assistant tool does. |
| Prompt injection through retrieved records | Reduced, not eliminated: retrieved text is delimited as data and cannot close its block, and the model has no write tool. A record can still try to mislead the answer's wording. |
| Business and company isolation | Records with a company field are read for the request's company; reports run with Frappe's report permissions but are not forced to the request's company. |

The assistant is fit for the owner's read-only demo. It is not yet fit for users who must not see each other's
companies through reports.

## Tests

Full suite after the accounting pass: 809 OK, 1 skipped. After the library, BA Plus and infrastructure pass: 812 OK, 1 skipped.
