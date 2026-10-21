# Production readiness, 21 Oct 2026

Follows the audit fixes of 20 Oct (docs/audit-fixes-2026-10-20.md) on branch `fix/audit-2026-10-20` (158 commits,
not pushed, not merged, nothing deployed). Today: the owner's confirmed policies on unsold books and dates, real
concurrency tests, browser tests by role, a restore test, the scheduler, the daily cash close, and four Must
requirements. Decisions still open are in docs/known-issues.md, section *QA and security audit*.

## Decision

- **Limited go-live (libraries, expenses, doctors' accounts, bookings, app subscriptions, with data typed by hand):
  GO once the five steps under "Before go-live" are done.** The code is ready for it: every audit defect is fixed,
  the confirmed policies are in, 507 automated tests, 5 two-session races and 116 browser checks pass.
- **Full requirements coverage: NO-GO.** HR and payroll, tasks, the integrations (library sales, studio bookings,
  the BA+ app), the owner hand-over account (ACC-09) and the AI model are not built; each waits for a decision or for
  files and access from another team.

### Before go-live

1. The production server set up per docs/production-hardening.md: passwords, 127.0.0.1 behind TLS, developer mode and
   tests off, the session and login settings, the scheduler on, built from a clean site.
2. The backup's off-server destination chosen, the nightly job scheduled, one restore tried there.
3. The accountant's answers on the cash close (who approves; what a difference does; reopening) and on whether a
   cash box may go below zero. Until then the close is a record only.
4. The historical records listed by `setup/check_doctor_accounts.py` reviewed (one waiting charge to reject, three
   demo entries without journal entries).
5. The owner signs off on going live without the modules listed above.

## Business rules

### Confirmed (owner, 21 Oct 2026) and built

| Rule | How it works |
|---|---|
| Unsold copies, curriculum unchanged | They stay in the store, are carried forward to the next period and sold there; the doctor earns his amount on each copy as it sells. Closing a term or module charges nobody and posts nothing. |
| Unsold copies, curriculum changed | Cancel: Curriculum Changed marks the edition obsolete, charging nothing. Dispose as Scrap makes a Damaged Stock Entry naming the edition for its copies left; submitted, their cost is a loss on the library (الهالك والتالف, the library's cost center) and they wait in the damaged store. A Damaged Stock Sale records the kilograms, the price a kilogram and the money (إيراد بيع التالف بالوزن). The edition shows the copies as Disposed Qty. |
| The doctor's loss | None. No Unsold Copies Charge is saved or submitted. Charges recorded before are rejected (draft) or cancelled (submitted), never applied. A books doctor goes below zero only through an approved deduction by hand. |
| Free lectures and 0% shares | Accepted once the lecturer is named; a booking with no lecturer and no share is still refused; paid bookings unchanged. |
| Future dates | No completed transaction is dated after today, for anyone; plans (bookings, monthly bills' next dates, rules and schedules, periods) keep their future dates. A date must be in one of the company's own fiscal years. |
| Demonstration data | The `_Test` records stay on the development site for looking at the screens; they do not reach the group's figures and the tests do not depend on them. Production starts from a clean site. |

The requirements document (v1.2) still says, in DOC-18, that the doctor pays for his unsold copies on cancellation;
v1.3 should replace it with the rule above, and drop DOC-22's approval of such charges.

### Still to decide

| Question | Who | Where it is in the code |
|---|---|---|
| A minus books adjustment by hand credits حصة الأطباء; or another account? | Accountant | `doctor_ledger_entry.post_by_hand` |
| The daily close: who approves it, what a difference posts (فروقات الخزينة?), reopening a closed day | Accountant / Owner | `doctype/treasury_close` records only |
| May a cash box go below zero? | Owner / Accountant | not checked |
| ACC-09: the owner's custody account and the bank | Owner | not built |
| PRN-01: is the closing counter reading enough, or one at the start of the day too? | Owner | closing only |
| The studio's opening hours (for occupancy, STU-15) | Owner | not built |

## Tests

| Kind | Run | Result |
|---|---|---|
| Integration tests, `run-tests --app imed_erp` behind the leak guard, after a backup | 21 Oct, 140 s | **507 passed, 0 failed, 0 skipped.** No `_Test` record leaked (counts unchanged). |
| New today | 24 tests; 9 tests of the superseded DOC-18 policy replaced by tests of the confirmed one | each new one failed on the code before its fix |
| Two sessions at once (`setup/concurrency_check.py`, two database connections at a barrier, on the copy site) | QA-10 transfer confirmed twice, QA-11 two payouts, QA-12 two subscriptions, QA-26 two day screens, two bookings of one hour | **5 of 5**: one receipt, one payout (balance 200), consistent counts and fees, one screen, one booking. The losing session is refused by the database and rolled back. |
| Browser, roles and security (`tests/e2e/roles.js`, Chromium) | 7 roles | **57 of 57**: login and logout, Arabic and right to left, pages and server calls refused, branch isolation, returns, cancellations and journal entries refused, phone width, home page accessibility |
| Browser, screens (`screens.js`) | 47 list and new-form screens over 5 roles | **47 of 47** open with no script error or failed request |
| Browser, workflows (`workflows.js`, `close.js`) | expense request to posting; transfer sent and confirmed; obsolete edition scrapped (48 copies, loss 3,360 on the library, doctor's balance unchanged); doctor statement; studio booking (1.5 h, 150); app subscription (fee 250); daily cash close | **12 of 12** on their first run on fresh data; re-runs meet their own earlier records, as expected (the booking slot taken, the edition already scrapped) |
| Private files over HTTP | a receipt fetched by its owner, another branch's manager, a guest | 200 / 403 / 403 |
| Restore into a separate site | today's backup into `restore-test` | every record count and the ledger, stock and doctor totals identical; a private file deleted and restored with the same checksum; retention removes sets older than 30 days |
| Scheduled jobs (copy site) | both daily jobs run twice | idempotent: one draft for a bill due today, nothing on the second run, no error log |

### Found by the browser and fixed

- Count cards on the owner's page read "EGP NaN": a card gets the system currency unless told otherwise.
- Every page requested `/undefined`: Frappe draws a menu item without an icon as a broken image (ERPNext's
  "Organization" ships none).
- A library manager's new Stock Entry form failed: she could not read Stock Settings, whose default warehouse is not
  hers.
- An app subscription showed a fee of 0 after it was submitted, until the page was reloaded.
- "Dispose as Scrap" was in English.

### Not tested

- On the production server: it is not set up.
- Integrations: none is built.
- Screen readers and keyboard-only use beyond the home page's quick actions; layouts other than desktop and a
  390 px phone.
- A load test.

## Every audit issue

| Status | Issues |
|---|---|
| Fixed and tested | QA-01, QA-02, QA-03 (confirmed policy), QA-04, QA-05, QA-06, QA-07, QA-08, QA-09, QA-10, QA-11, QA-12, QA-13, QA-14, QA-15, QA-17, QA-18, QA-19, QA-20, QA-21, QA-22, QA-23, QA-24 (confirmed policy), QA-25, QA-26, QA-27, QA-28, QA-29, QA-30, QA-31, QA-32, QA-33, QA-34, QA-36; SEC-01, SEC-02, SEC-03, SEC-07, SEC-08, SEC-09, SEC-10, SEC-11, SEC-12, SEC-13 |
| Fixed, partly | QA-16 (the fee posts on the app; the subscription's own cost center still names who recorded it); QA-35 (seen in the browser, not by a test); QA-37 (isolated and kept, as asked; not deleted) |
| Ready, not deployed | SEC-04, SEC-05, SEC-06 (production compose file validated; backup script tested here; the guide's settings) |

Per issue, the root cause and fix are in docs/audit-fixes-2026-10-20.md and in the commit that names its ID.

## Requirements (v1.2: 183 IDs)

| | |
|---|---|
| Completed and verified today | ACC-03 (balances and the close, recorded), CORE-07, PRN-04, HAL-06, CRM-01 (student category) |
| Partly built | ACC-03 (approval and posting of a difference), ACC-04, ACC-05, ACC-08, ACC-09, CORE-04, CORE-06, LIB-01, LIB-07, PRN-01, PRN-03, PRN-09, STU-06, STU-09, STU-10, APP-10, DOC-12, DOC-26, INT-01, INT-04, INT-06, INT-08, INT-14, RPT-01, RPT-02, RPT-05, RPT-11, SEC-02, SEC-06 |
| Missing, specified enough to build next | CRM-03 call log (Should) |
| Waiting for a business decision | ACC-09, ACC-10, DOC-18's text (superseded), HAL-05 and RPT-04 (marked Open), PRN-01, STU-15, APP-09, RPT-09, HR-01..07 (HRMS to be installed), TSK-01..05 |
| Waiting for other teams, files or credentials | LIB-11, STU-07, STU-11..13, HAL-09, APP-13, INT-02..13, AI-01..10 (no model connected), SEC-09 |

The rest were built before 20 Oct and are listed in the audit's coverage table.

## Environment notes

- The development site (`frontend`) was changed only by configuration: the owner dashboard's cards, Stock Settings'
  default warehouse no longer hiding the settings from branch managers, and two new doctypes and fields from this
  branch. No business record was changed or deleted. Its scheduler is still off.
- `restore-test` is a throwaway copy made from today's backup, used for the restore test, the concurrency checks and
  the browser tests; its staff accounts have a test password. Drop it when no longer needed
  (`bench drop-site restore-test`), which needs your go-ahead.
- Backups of today are in `~/imed-backups/` (database only) and `~/imed-backups/sets/` (database, files and site
  configuration; the configuration holds the database password, so the folder is readable by its owner only).
