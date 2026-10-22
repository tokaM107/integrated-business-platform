# Production readiness, 21 Oct 2026 (updated 22 Oct)

Follows the audit fixes of 20 Oct (docs/audit-fixes-2026-10-20.md) on branch `fix/audit-2026-10-20` (158 commits,
not pushed, not merged, nothing deployed). Today: the owner's confirmed policies on unsold books and dates, real
concurrency tests, browser tests by role, a restore test, the scheduler, four Must requirements, and (afternoon)
the owner's rules for cash: boxes never below zero, the daily close, discrepancies and the weekly review. Decisions still open are in docs/known-issues.md, section *QA and security audit*.

## Decision (updated 22 Oct 2026)

**Not production-ready yet. Limited launch: NO-GO today; GO once every action under "Before a limited launch" is
done.** The code for it is built and tested, including the owner's rules of 22 Oct (BA Plus payments, counters read
twice, prepaid studio hours, the weekly cash hand-over, surplus causes, manual doctor adjustments). What is missing
is outside the code: a server, off-server backups, opening cash, a few accounting decisions. Passing tests prove the
code, not the server, its backups, its data or its users' access.

**Full requirements coverage: NO-GO.** See *Missing features*.

### 1. Completed and verified

- Every audit defect (QA-01..37, SEC-01..13) fixed or partly fixed as listed under *Every audit issue*.
- The owner's rules of 21 Oct: unsold books (DOC-18/22), dates, free lectures, demo data apart; the daily cash close,
  discrepancies, four-eyes recovery (blocked by policy), reopening, the weekly review Saturday to Thursday, cash boxes
  never below zero.
- The owner's rules of 22 Oct (docs/requirements/v1.3-amendments.md; README):
  - BA Plus payments in cash (into the collecting branch's box, in its close) or electronically (bank or wallet, with
    its reference, matched with the statement), held for the doctor, never revenue, never twice (App Payment).
  - Counters read morning and evening, the gap since the last closing with its reason; printed, sold, paper issued
    and damaged shown apart; counters move no stock.
  - Prepaid studio hours: exact hours drawn per session, given back when moved or cancelled, with a history; never
    below zero; extra hours only on the accountant's or owner's decision; the package billed once.
  - ACC-09 weekly hand-over: recorded by the branch, printed Arabic receipt signed on paper, confirmed only by the named
    receiver with the scan attached; posted once to their custody account; in the day's close and the week's review;
    cancelled only with a reason and kept.
  - Surpluses settled by their verified cause, never assumed revenue; unknown ones stay open.
  - Manual doctor adjustments: reason, basis and account, approval either way, reversal by an approver with a reason.
- Tests (development site, 22 Oct, after a backup): **600 passed, 0 failed, 0 skipped**. The 545 of 21 Oct, all
  still passing (some updated where the owner's new rules changed what they expected), plus 55 new.
- Two-session races (restore-test site, committed): **11 of 11 passed**, 4 of them new (two hand-overs from one
  box, one hand-over confirmed twice, two sessions on a package's last hours, one transfer reference twice).
- Browser, demo site, by role: **22 of 22 passed** (14 new: payments, counters, prepaid hours, the hand-over, its
  receipt and its private scan; 8 from 21 Oct).
- The demo site keeps its data, with labelled sample records of every new feature (setup/seed_demo_22oct.py).

### 2. Remaining operational setup (docs/production-deployment-plan.md)

A server configured (passwords, TLS, firewall, login rules); off-server backups with one restore checked there;
a clean site with migrations, worker restart and cache clear; Cash Close Settings with the week and the custody
accounts; the scheduler on and its jobs checked after the first night; opening cash counted, signed and entered for
every box; smoke tests by role kept on record.

### 3. Outstanding business decisions

| Decision | Who | Until then |
|---|---|---|
| Where off-server backups go (a private cloud drive or an office disk) | Owner | blocks launch |
| How money held for doctors from BA Plus payments reaches them: paid out, or set against platform fees | Accountant, Owner | held and listed (App Payments) |
| The recovery policy for cash shortages | Lawyer or HR, then Owner | recovery blocked |
| Prepaid studio hours: income when sold (as built) or deferred as used | Accountant | income when invoiced |
| A no-show on prepaid hours: hours used, or given back (as built) | Owner | given back |
| A liability account for money held for a customer (surplus) | Accountant | named case by case |
| Handing cash to the bank (no bank account in the chart) | Owner | hand-overs go to the owner or the accountant only |
| Committing the requirements document to git, or keeping it outside | Owner | kept outside |

### 4. Missing features (not started; each needs an agreed scope)

HR and payroll (HR-01..07), tasks (TSK-01..05), the integrations with the library sales system, the studio booking
system and the BA+ app (INT-02..13; BA Plus payments have an idempotent import entry point, not connected), the AI
assistant's model (AI-01..10), the call log (CRM-03). No payroll deduction of any kind exists, by design.

### 5. Before a limited launch: exact actions

1. Production server set up and checked: plan, section A.
2. Off-server backup destination chosen; nightly job running; one backup restored on the server and compared:
   plan, section B.
3. Clean site, setup scripts (setup_coa.py makes the custody and held-for-doctors accounts), migrate, restart, clear
   cache, developer mode and tests off: plan, section C.
4. Cash Close Settings: week Saturday to Thursday; Recovery Policy Approved **off**; both custody accounts set.
5. Scheduler enabled; jobs checked after the first night; e-mail account tested: plan, section D.
6. Opening cash counted, signed and entered for every box before the first sale: plan, section E.
7. Smoke tests by role, including a hand-over printed, signed, scanned and confirmed, results kept: plan, section F.
8. The accountant decides how money held for doctors reaches them (or the owner accepts it is only held at first).
9. The owner signs off launching without the missing features.

## Business rules

### Confirmed (owner, 21 Oct 2026) and built

| Rule | How it works |
|---|---|
| Unsold copies, curriculum unchanged | They stay in the store, are carried forward to the next period and sold there; the doctor earns his amount on each copy as it sells. Closing a term or module charges nobody and posts nothing. |
| Unsold copies, curriculum changed | Cancel: Curriculum Changed marks the edition obsolete, charging nothing. Dispose as Scrap makes a Damaged Stock Entry naming the edition for its copies left; submitted, their cost is a loss on the library (الهالك والتالف, the library's cost center) and they wait in the damaged store. A Damaged Stock Sale records the kilograms, the price a kilogram and the money (إيراد بيع التالف بالوزن). The edition shows the copies as Disposed Qty. |
| The doctor's loss | None. No Unsold Copies Charge is saved or submitted. Charges recorded before are rejected (draft) or cancelled (submitted), never applied. A books doctor goes below zero only through an approved deduction by hand. |
| Free lectures and 0% shares | Accepted once the lecturer is named; a booking with no lecturer and no share is still refused; paid bookings unchanged. |
| Future dates | No completed transaction is dated after today, for anyone; plans (bookings, monthly bills' next dates, rules and schedules, periods) keep their future dates. A date must be in one of the company's own fiscal years. |
| Cash boxes (21 Oct) | A cash box never goes below zero: any payment of more than it holds is refused, on any day from its date to today, under a lock; cancelling cash that came in is checked too. Existing balances are not changed. |
| The daily close (21 Oct) | The branch manager closes her own box; no daily approval. Opening = last count; movements since by kind; Expected = Opening + in - out; Variance = Counted - Expected. Posts nothing. Once a day per box, in order. A cash entry dated into a closed day: refused to a branch manager, marked for review when the accountant makes it. |
| Discrepancies (21 Oct) | Every difference opens a Cash Discrepancy. Shortage: investigated; nobody responsible by default; no automatic split; a recovery only after the employee is told and heard, the law and contract checked, amounts typed; written off otherwise. Surplus: explained, never revenue by itself. The books are adjusted (فروقات الخزينة) only after the review. Nothing is deducted from a salary by the system: approved recoveries go to a payroll review report. |
| Reopening (21 Oct) | Owner and accountant only, with a reason; the original kept, cancelled, with who and why; a draft amends it; later closes and reviewed weeks marked for review; refused once its discrepancy is adjusted or a recovery approved. |
| Weekly review (21 Oct) | Weekly Cash Reconciliation by the accountant: the week's closes, shortages, surpluses, open discrepancies, responsible employees, days not closed; submitted = reviewed. |
| Demonstration data | The `_Test` records stay on the development site for looking at the screens; they do not reach the group's figures and the tests do not depend on them. Production starts from a clean site. |

The requirements document (v1.2) still says, in DOC-18, that the doctor pays for his unsold copies on cancellation;
v1.3 should replace it with the rule above, and drop DOC-22's approval of such charges.

### Still to decide

| Question | Who | Where it is in the code |
|---|---|---|
| A minus books adjustment by hand credits حصة الأطباء; or another account? | Accountant | `doctor_ledger_entry.post_by_hand` |
| The recovery policy: the labour law's limits on deductions, the contracts, how the employee is told and heard, appeals, how a recovery reaches payroll | Lawyer / HR, then the Owner | recovery blocked (Cash Close Settings); four eyes built: the accountant recommends, the owner approves |
| An explained surplus adjusted to فروقات الخزينة, or held to return to a customer? | Accountant | فروقات الخزينة, only after it is explained; an unexplained one stays under review |
| ~~The reporting week~~ decided: Saturday to Thursday, Friday off (owner, 21 Oct) | - | Cash Close Settings, set on the development and demo sites |
| Does the BA Plus app take cash? (its treasury is a bank account today) | Owner | no daily close, no check below zero |
| ACC-09: the owner's custody account and the bank | Owner | not built |
| PRN-01: is the closing counter reading enough, or one at the start of the day too? | Owner | closing only |
| The studio's opening hours (for occupancy, STU-15) | Owner | not built |

## Tests

| Kind | Run | Result |
|---|---|---|
| Integration tests, `run-tests --app imed_erp` behind the leak guard, after a backup | 21 Oct, evening, 168 s | **535 passed, 0 failed, 0 skipped.** No `_Test` record leaked (counts unchanged). |
| New in the afternoon | 6 cash-box tests; 16 close and reopening tests; 6 discrepancy tests; 5 weekly-review tests; 2 suites given opening cash | the cash-box tests fail without the hooks; the weekly test of a reopened close fails without its fix (seen first in the browser) |
| New today | 24 tests; 9 tests of the superseded DOC-18 policy replaced by tests of the confirmed one | each new one failed on the code before its fix |
| Two sessions at once (`setup/concurrency_check.py`, two database connections at a barrier, on the copy site) | QA-10 transfer confirmed twice, QA-11 two payouts, QA-12 two subscriptions, QA-26 two day screens, two bookings of one hour | **5 of 5**: one receipt, one payout (balance 200), consistent counts and fees, one screen, one booking. The losing session is refused by the database and rolled back. |
| Two sessions at once, afternoon | two payments of 300 from a box holding 500; two closes of one box for one day | **2 of 2**: box ends at 200, one close. The close race **failed first (two closes saved)**: the duplicate check read an old snapshot; fixed with a locking read. QA-26 could not run again today (each library already has today's screen). |
| Browser, roles and security (`tests/e2e/roles.js`, Chromium) | 7 roles | **57 of 57**: login and logout, Arabic and right to left, pages and server calls refused, branch isolation, returns, cancellations and journal entries refused, phone width, home page accessibility |
| Browser, screens (`screens.js`) | 47 list and new-form screens over 5 roles | **47 of 47** open with no script error or failed request |
| Browser, the close and its review (`close.js`, afternoon) | Sara sees her close in Arabic with no Reopen, her reopen and write-off calls refused (403); the accountant reopens with a reason, closes 15 short, writes it off, reviews the week | **7 of 7**. Found and fixed: a draft weekly review could not be saved once one of its closes was reopened. |
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
| Completed and verified today | ACC-03 (the close, discrepancies, the weekly review, reopening, boxes never below zero), CORE-07, PRN-04, HAL-06, CRM-01 (student category) |
| Partly built | ACC-04, ACC-05, ACC-08, ACC-09, CORE-04, CORE-06, LIB-01, LIB-07, PRN-01, PRN-03, PRN-09, STU-06, STU-09, STU-10, APP-10, DOC-12, DOC-26, INT-01, INT-04, INT-06, INT-08, INT-14, RPT-01, RPT-02, RPT-05, RPT-11, SEC-02, SEC-06 |
| Missing, specified enough to build next | CRM-03 call log (Should) |
| Waiting for a business decision | ACC-09, ACC-10, DOC-18's text (superseded), HAL-05 and RPT-04 (marked Open), PRN-01, STU-15, APP-09, RPT-09, HR-01..07 (HRMS to be installed), TSK-01..05 |
| Waiting for other teams, files or credentials | LIB-11, STU-07, STU-11..13, HAL-09, APP-13, INT-02..13, AI-01..10 (no model connected), SEC-09 |

The rest were built before 20 Oct and are listed in the audit's coverage table.

## Follow-up checks, 21 Oct evening

| Check | Result |
|---|---|
| Open shortages and surpluses through later closes and weeks | Not repeated and not hidden: the next close opens with the cash counted, so a difference is never counted again; each counts in its own week's totals; a later week lists the earlier ones still open apart (*Still Open from Earlier Weeks*) and needs a note while any is open. New: the carried list (it was missing: an open discrepancy of an earlier week appeared in no later review). |
| Mawasah at -936.50 | From the demo transactions of 18 Oct, entered with no opening cash: sales ACC-SINV-2026-00002 (1,800) and -00003 (605) in; payout ACC-JV-2026-00006 (400, Doctor Ledger Entry 5rc1gthld0), expense ACC-JV-2026-00007 (450, EXP-2026-00001), transfers ACC-JV-2026-00009 (1,500, IBT-2026-00001) and -00011 (1,000, IBT-2026-00002) out; scrap payment ACC-PAY-2026-00001 (8.50) in. No logic error. At the owner's request the group's transactions were then erased on the development site (docs/known-issues.md); no fake collection was made. |
| Four eyes | Built: Recommend Recovery (accountant) -> Approve Recovery or Return (owner only, never their own recommendation). No payroll deduction anywhere. |
| Unexplained surplus | Stays Pending Review, in the open counts and later weeks; no entry is posted until it is explained. |
| The reporting week | The requirements name no first day (RPT-01: "daily, weekly and monthly"). The owner then set Saturday to Thursday, Friday off: built as Cash Close Settings' first and last working days; a Friday close still shows in its week. |
| Recovery dependencies | Legal (deduction limits, notice, appeal), payroll (no HR module: recoveries leave as a report), authorization (owner approves; policy switch owner-only), accounting (adjustment account). Recovery blocked until the policy is approved. |
| Tests after these changes | Full suite on the cleaned development site: **543 passed, 0 failed**. 8 new tests (four eyes, policy block, owner returns, policy owner-only, unexplained surplus, carried discrepancy, week's first day, opening cash x2). 3 older suites relied on the erased demo data (cash in the main box, books in Mawasah's store, no paper below its level) and now make their own. Browser close and review: 7 of 7. |
| Opening cash | On the cleaned development site every cash box is mapped to its business, with no entries and a zero balance; BA Plus's treasury is a bank account. Instructions and a draft-only helper: docs/production-hardening.md, section 7. |

## Environment notes

- The development site (`frontend`): configuration (the owner dashboard, Stock Settings' default warehouse, the new
  doctypes and fields of this branch, Cash Close Settings' week Saturday to Thursday) and, on 21 Oct, **every
  transaction of the group erased** after a full backup (docs/known-issues.md). The owner wanted the demo
  transactions kept for previewing: they are now on the separate **demo** site, restored from that backup (not over
  the development site). Its scheduler is still off.
- `demo`: the backup of 21 Oct 16:58 restored and migrated, plus the sample cash records of
  `setup/seed_cash_demo.py`; http://127.0.0.1:8081 (container `imed-demo-web`); staff accounts with a demo-only
  password.
- `restore-test` is a throwaway copy made from today's backup, used for the restore test, the concurrency checks and
  the browser tests; its staff accounts have a test password. Drop it when no longer needed
  (`bench drop-site restore-test`), which needs your go-ahead.
- Backups of today are in `~/imed-backups/` (database only) and `~/imed-backups/sets/` (database, files and site
  configuration; the configuration holds the database password, so the folder is readable by its owner only).
