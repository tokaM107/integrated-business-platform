# Audit fixes, 20 Oct 2026

What was done about the QA and security audit of 20 Oct 2026, on branch `fix/audit-2026-10-20` (110 commits; each
names its audit ID). The decisions the fixes took are in docs/known-issues.md, *QA and security audit*; production
steps are in docs/production-hardening.md.

**Verdict: NO-GO for 28 Oct as things stand, GO for a limited go-live once the five items under "Before go-live"
are done.** Every code defect and code-side security finding is fixed and tested; what remains is deployment,
backups off the server, one data clean-up, and the owner's sign-off on what goes live unbuilt.

## Tests

| | Before (audit) | After |
|---|---|---|
| Tests in the app | 439 | 492 |
| Passing | 430 | 492 (two full runs; the first found one test dating a payout in 2027, fixed) |
| New regression tests | | 53 |

How it was run: a backup copied out of the container first (`~/imed-backups`), the test-record leak guard
(`test_test_records`) before every run and gated on it, then `run-tests --app imed_erp`. Each new test was run
against the original code first and failed, except where the fix adds a new function (SEC-11's rate limit, the
Treasury Balances report).

The nine tests that failed in the audit now pass on any site: they read what the stores hold before they start
(QA-37), use the paper's own unit, and the reorder alerts are limited to the group's company (QA-23).

Not executed:

- **Two sessions at once** (QA-10, QA-11, QA-12, QA-26): fixed with row locks taken before the read; tests check
  the order (lock, then read) and a second screen of the same document. A true two-session run would commit
  records to the site, so it is in the manual checklist (docs/production-hardening.md, section 5).
- **Browser**: the UI fixes (QA-35, the home buttons, RTL tooltip and calendar, assistant microphone) are checked for
  syntax only.
- **Production**: nothing deployed; the production compose override was rendered with `docker compose config`.

## Fixed, with a regression test

| ID | Root cause | Fix |
|---|---|---|
| QA-01 | An entry naming an earlier term but dated after this term began was in neither the opening nor the term. | The opening goes by the period an entry names, then by date. |
| QA-02 | Only payouts and collections posted a journal entry. | Charges, adjustments and accruals by hand post one, and cancel it with them. |
| QA-03 | "Already charged" was checked for the current term only. | Copies are charged once per edition; copies charged and sold since get a draft credit. |
| QA-04 | Nothing checked credit notes. | Returns need the owner or the accountant, and a reason. |
| QA-05 | A count ignored paper waiting in a draft issue. | The count treats it as gone and leaves room for the draft. |
| QA-06, QA-18 | Cards added up all time; revenue read sales invoices only. | Dated cards from the ledger; revenue by business from income accounts; unpaid bookings from invoice outstanding. |
| QA-07, QA-17 | Checks ran only on drafts; the date was not checked. | Checked on submit; the date must be in the course's term. |
| QA-08, QA-10 | Receiving box not checked; status read without a lock. | The receiver's own box or a wallet; the status re-read under a lock. |
| QA-09 | A bill paid early kept its due date. | It moves on to next month; no draft for a month already paid. |
| QA-11, QA-12 | Balance and count read without a lock. | The agreement and the course are locked first. |
| QA-13 | Prices used hours rounded to 2 decimals. | Priced from minutes; the invoice bills the same amount. |
| QA-14, QA-15 | 0 counted as missing; date and times not checked once invoiced. | 0 accepted once the lecturer is named; an invoiced booking keeps its day and times. |
| QA-19 | Two counts could post one shortage. | An earlier count is refused after a later one of the same store. |
| QA-20, QA-21, QA-26, QA-30 | Readings outside the day's screen; no reset; no lock; opening 0 accepted. | The day's screen for staff, one a day; Counter Reset for the accounts; lock; opening above 0. |
| QA-22 | A plain transfer skipped the request. | Between branches: the request, or the accounts with Received By and the machine. |
| QA-23, QA-27 | Alerts not limited to the company; decided on the ledger at the document's date. | The group's warehouses; decided on the stock now, on submit and on cancel. |
| QA-25, SEC-01 | Reason optional and saved without cleaning; shown as HTML. | Required, cleaned, escaped on the form. |
| QA-28 | Valued at today's paper cost. | At the reading date's cost. |
| QA-29 | Surplus in the damaged store needed a valuation rate (confirmed; audit had it suspected). | Posted at no value. |
| QA-31 | Country code without its plus only recognised on mobiles. | Also landlines and an extra 0; numbers valid before keep their key. |
| QA-32 | Report and P&L differ on shared premises. | The report says so and why. |
| QA-33 | A sale in a closed period was retried daily. | Reported once. |
| QA-34 | Tier label re-derived from today's schedule. | The tier is kept on the course when counted. |
| QA-36 | "0 days" of breakdowns. | Nothing shown. |
| SEC-02 | `frappe.set_user` replaced the web session. | `as_administrator()`. |
| SEC-03, SEC-09 | Any file URL accepted; forged approval fields saved. | The expense's own private upload, once; the request clears approval fields. |
| SEC-07, SEC-08 | No branch meant every branch; endpoints returned other branches. | Refused without a branch; read permission checked. |
| SEC-10 | Print formats printed values unescaped (confirmed; audit had it suspected). | Escaped. |
| SEC-11 | No rate limit; audio decoded before the size check. | 20 a minute per address; size checked first. |
| SEC-12 | Imported bookings and cancelled schedules and requests could be deleted. | Kept. Bookings with payments and courses with students were already kept by Frappe's link check. |
| SEC-13 | Any payment could name a booking. | Only Record Payment. |

Also fixed: the three untranslated strings and Arabic for every new message, screen-reader roles on the home
actions, RTL tooltip and calendar directions, the calendar's read-only users, the assistant's object URLs and
microphone loss.

## Partly fixed

| ID | Done | Not done |
|---|---|---|
| QA-06 | Every figure listed except one. | Integration status: no integration runs yet. |
| QA-16 | The fee posts on the app's cost center. | The subscription's own cost center field remains (who recorded it). |
| QA-24 | Expenses (staff), transfers, payouts, readings. | Collections into a treasury; negative cash boxes. |
| QA-35 | Display fixed. | Not seen in a browser. |
| QA-37 | The nine tests are site-independent. | The leaked `_Test` records are still on the development site: deleting them needs the owner's go-ahead. |
| SEC-04 | Production compose override (passwords required, 127.0.0.1 only), guide, README warning. | Not deployed. |
| SEC-05 | Backup script, tested here; login lockout settings written down. | No remote chosen, not scheduled, no restore tried. |
| SEC-06 | CSP written in the guide. | Needs the TLS proxy. |
| ACC-03 | Treasury Balances report. | The daily close: how and who approves is undecided. |

## Not built: Must items waiting for a decision

HR (HRMS not installed), tasks (TSK), the daily close (ACC-03), the hand-over account (ACC-09), and the
integrations (INT-02..13: files and access from the other teams). Each blocker is in docs/known-issues.md.

## Before go-live

1. Production: docs/production-hardening.md, sections 1 to 3 (passwords, 127.0.0.1 behind TLS, developer mode and
   tests off, scheduler on, login settings), on a clean site.
2. Backups: choose where the copy goes, schedule the script, restore one backup once.
3. The manual two-session and role checks (guide, section 5).
4. The accountant confirms the accounting choices (known-issues, audit table, rows 1 to 4 and 9).
5. The owner signs off on going live without HR, tasks, integrations, the daily close and the hand-over account.
