# Owner Dashboard — integration and data-accuracy audit, 1 November 2026

Scope: every component of the Owner Dashboard workspace in the live IMED ERP (https://erpmohamedmamdouh.tech), traced
to its code, its data source and its value, read-only on production. Fixes on branch `audit/owner-dashboard-2026-11-01`
(from `production`), not pushed, not deployed.

## 1. What is actually deployed

| Item | Finding |
|---|---|
| Running image | `imed-erp:coolify`, built 29 Oct 2026 15:05 UTC; containers up since then; `bench version`: frappe 16.35.0, erpnext 16.36.0, imed_erp 0.0.1 |
| Code in the image | Every dashboard file (owner_figures.py, owner_yesterday.py, owner_dashboard.py, business_figures.py, imed_owner_dashboard.js, setup_dashboard.py, hooks.py, imed_theme.css) hashes identically to commit **e44661a**, the head of `production`. No drift. |
| Site | `frontend`, time zone Africa/Cairo (site clock 11:41 local = 09:41 UTC, verified), `developer_mode 0`, `allow_tests 0`, scheduler enabled |
| Dashboard definitions in the database | 15 Number Cards, 4 Dashboard Charts, 6 shortcuts, workspace roles = Super Admin; all created 25 Oct 2026 by `setup_dashboard.py`; the card methods match the code |
| Who sees it | `owner@imed.local` only (Super Admin; default workspace = Owner Dashboard). Accountant: workspace hidden, money endpoints allowed, band refused (PermissionError). Branch managers (raghad, sara): every endpoint refused. Verified by calling each endpoint as each user. |
| XStudio sync | cron every 10 minutes, last run 11:32; health **Degraded** for a week: 239 of the last 251 runs "Completed with Errors", the same 1 failed row each time |
| Paused jobs | `doctor_accrual.run_daily` and `recurring_expense.run_daily` are `stopped = 1` (on purpose, cutover decision) |

**The most important fact of this audit**: the production site holds **no accounting data at all**. Counts on 1 Nov 2026:
GL Entry 0 (every company), Sales Invoice 0, Purchase Invoice 0, Journal Entry 0, Payment Entry 0, Treasury Close 0,
Cash Discrepancy 0, Daily Counter Reading 0, Doctor Ledger Entry 0, App Subscription 0, Expense 0, Data Import 0.
What exists: 133 XStudio bookings (101 "confirmed/unpaid" in XStudio, 32 cancelled; **none completed or paid in XStudio**),
52 customers, 38 items, 3 doctor agreements, 7 studio Booking Resources (none of type Hall), 12 recurring expenses,
and ERPNext's `_Test` companies with 2 test stock entries (value 2,000) in `_Test Warehouse`.

So every money card is a genuine zero today, and the dashboard could not say so: a zero looked like a result.

## 2. Component inventory and verification

Expected values were recomputed independently (ERPNext's `get_balance_on`, separate SQL on GL Entry / Booking /
Doctor Ledger Entry / Cash Discrepancy / Bin, Frappe's own count API) and compared with what the endpoints return to
the owner and what the browser draws (Playwright, local site; production figures by read-only console).

| # | Dashboard component | Data source | Expected | Displayed | Status | Issue / evidence |
|---|---|---|---|---|---|---|
| 1 | Card: Cash in the Cash Boxes | GL Entry, Cash/Bank accounts of MMG (`owner_figures.cash_in_boxes`) | 0.00 (10 accounts, each 0 by `get_balance_on`) | EGP 0.00 | PASS (value) / FAIL (link) | Click opened `List/Treasury`: no such DocType → empty "not found" page. Fixed: opens the Cash Box Balances report. |
| 2 | Card: Revenue This Month | GL Entry, Income accounts, whole calendar month | 0.00 | EGP 0.00 | PASS (value) / FAIL (rule) | Did not exclude opening entries or Period Closing Vouchers, unlike business_figures.ledger and the reports: on the day the year is closed the card would read 0. Fixed + test. |
| 3 | Card: Expenses This Month | same, Expense accounts | 0.00 | EGP 0.00 | PASS / same rule fix | |
| 4 | Card: Net This Month | 2 − 3 | 0.00 | EGP 0.00 | PASS | |
| 5 | Card: Owed to Us | GL, Receivable accounts (3) | 0.00 | EGP 0.00 | PASS | Deposits taken reduce it (documented). Link: unpaid Sales Invoices, correct. |
| 6 | Card: We Owe | GL, leaf accounts under الذمم الدائنة (5) | 0.00 | EGP 0.00 | PASS (note) | Account `سلف الموظفين` is typed Payable but sits outside the group: left out on purpose (it is an advance to staff). |
| 7 | Card: Platform Fees This Month | GL, account إيراد رسوم المنصة, month to date | 0.00 | EGP 0.00 | PASS | Uses the global default company = MMG (verified). |
| 8 | Card: Collected from Doctors This Month | Doctor Ledger Entry, Collection, submitted, MTD | 0.00 (0 entries exist) | EGP 0.00 | PASS (note) | Counts collections of book and app agreements alike; the band's "Collected today" is app-only. Wording decision for the owner. |
| 9 | Card: Cash Shortages This Month | Cash Discrepancy, Shortage, not Withdrawn, close_date MTD | 0.00 (0 records) | EGP 0.00 | PASS | |
| 10 | Card: Open Cash Discrepancies | Cash Discrepancy, status in OPEN | 0 | 0 | PASS | |
| 11 | Card: Studio Bookings This Month | Booking, cost center استوديو X, held statuses, whole month | 5 (all Tentative, 1–4 Nov, from XStudio) | 5 | PASS | Includes bookings still to come (documented, owner's wish of 25 Oct). Click-through filters by resource_type, the card by cost center: equal today. |
| 12 | Card: Studio Hours This Month | same, sum of hours | 15.0 | 15 | PASS | |
| 13 | Card: Hall Bookings This Month | Booking, cost center قاعات Imed | 0 | 0 | NOT CONNECTED (data) | No hall Booking Resource exists in production; 0 is "not set up", indistinguishable from 0 bookings. |
| 14 | Card: Unpaid on Bookings | Booking (Confirmed with Deposit / Completed, dated ≤ today) + invoice outstanding | 0.00 | EGP 0.00 | PASS | No XStudio booking ever reaches these statuses in production (see 27). |
| 15 | Card: Due on Studio Bookings (XStudio) | Booking, xstudio_amount_due − xstudio_amount_paid, held, this month | 2,000.00 (400+400+800+0+400) | EGP 2,000.00 | PASS | |
| 16 | Shortcuts ×6 (Expenses, Editions, Transfers, Doctor charges, Discrepancies, Recoveries) | Frappe list counts with the stored filters | 0,1,0,0,0,0 | 0,1,0,0,0,0 | PASS | Pills verified against `get_count` with the same filters. |
| 17 | Chart: Cash by Cash Box | Cash Box Balances report (same function as card 1) | 10 bars, all 0 | drawn | PASS | |
| 18 | Chart: Sales Trend | Sales Invoice grand_total, weekly, last quarter, docstatus 1, **no company filter** | nothing (0 invoices) | "No data" | INCOMPLETE | Would include `_Test` companies' invoices. Fixed in setup_dashboard.py (company filter); takes effect when the script is re-run on the site. |
| 19 | Chart: Revenue by Business | GL income by cost center, MTD (custom source) | empty | empty | PASS | Same company; no PCV exclusion but MTD only. |
| 20 | Chart: Stock Value by Warehouse | Bin.stock_value grouped by warehouse, **no company filter** | MMG: 1 warehouse, 0 | **`_Test Warehouse` EGP 2,000** shown on the owner's dashboard (reproduced locally, screenshot) | FAIL | Test data of another company displayed as the group's stock. Fixed in setup_dashboard.py (warehouse like `% - MMG`), verified locally after re-running the script; needs the script re-run on production. |
| 21 | Band: money table (7 businesses) | business_figures.ledger for the day | all 0 (0 GL rows) | all 0 | PASS (value) / FAIL (meaning) | Nothing distinguished "nothing posted" from "no money". Fixed: the band now says so when the day has no ledger entry. |
| 22 | Band: X Studio line | mirrored XStudio bookings of the day | XStudio bills **400** (BOOK-00137); BOOK-00136 is 5 h on prepaid package SHP-2026-00016, price 1,000, due 0 | **revenue 1,400**, due 400 | **FAIL (money)** | List price was counted as the day's value: package hours (paid when the package was bought) double-counted. All-time: 29 such bookings, 14,600 of price with 0 due. Fixed: value = XStudio's amount due; package bookings and hours shown apart; test added. |
| 23 | Band: Halls/Studio counts (held, completed, cancelled, no-show) | Booking by booking_date | studio held 2, others 0 | 2 / 0 | PASS | |
| 24 | Band: Studio hours booked / delivered | Booking hours | 7.0 / 0 | 7 h / 0 h | PASS (value) / FAIL (format) | 2.5 h was shown as "2 h" (half hours rounded away; seen in the local dynamic test). Fixed. |
| 25 | Band: Booked today (any date) | Booking.creation ≥ today 00:00 Cairo | 4 | 4 | PASS | Time zone verified. |
| 26 | Band: Due / Paid in XStudio | xstudio_amount_due / paid of the day | due 400 (total owed, not remaining) / 0 | 400 / 0 | FAIL (definition) | "Due" meant total owed here but "due − paid" on card 15. Fixed: both are due − paid. |
| 27 | Band: Studio "Completed", "delivered", "Paid in XStudio" | XStudio status/payments | always 0 | 0 | NOT CONNECTED (upstream) | XStudio staff never mark bookings completed or paid: 96 past bookings still "confirmed/unpaid". The figures are wired correctly and will stay at zero until XStudio is used for it. Decision needed. |
| 28 | Band: "still open" warning | manual bookings in open statuses | 0 | none | PASS (link fixed) | The link's filter lacked status "Confirmed" that the server counts. Fixed. |
| 29 | Band: IMED halls card (today, next 7 days, active halls, occupied, month, fixed rents, revenue shares, past open, no share) | Booking resource_type Hall, Booking Resource | all 0 (no hall resources) | 0 | NOT CONNECTED (data) | Correctly wired (verified locally with hall tests); production has no hall master data. |
| 30 | Band: Platform fees (charged, collected, owed, new students) | Doctor Ledger Entry (App agreements), receivable account, App Subscription | 0 / 0 / 0.00 / 0 | same | PASS | 1 app agreement exists so the card is "ok", not "not configured". |
| 31 | Band: Paper and counters | Daily Counter Reading, Printing Machine | 7 machines, 0 readings → two warnings | warnings shown | PASS (value) / FAIL (links) | "Sheets printed/sold/difference" opened Printer Reading (0 records) and Sales Invoice; fixed to open the day's Daily Counter Reading. |
| 32 | Band: XStudio bookings (system) | XStudio Settings + last Integration Import Log | Degraded, 1 failed | "Needs attention — 161 read, 0 inserted, 0 updated, 116 unchanged, 0 to look at, 1 failed" | PASS (state) / INCOMPLETE (detail) | Reflects the real log, not just scheduler success. But: which row fails and why was not shown (the log holds it: one walk-in booking with no customer, every run for a week); 8 "Incomplete historical usage" notes on packages were invisible; 161 ≠ 116 + 1 (the sync's counters do not add up: 44 rows unaccounted). Fixed: the band names the first failure and the number of notes. Counter arithmetic is a sync issue, reported, not changed. |
| 33 | Band: File imports | Data Import | none | "Unknown — no file imported yet" | PASS | Honest state. |
| 34 | Band: "Daily job: sync" | Scheduled Job Type xstudio.sync.run_scheduled (cron */10) | ok | "Daily job: sync — Working" | FAIL (label) | A 10-minute cron labelled a daily job named "sync"; its link opened Error Log. Fixed: "Scheduled job: XStudio sync", link to Scheduled Job Log. |
| 35 | Band: Daily job: Doctors' share / Monthly bills reminder | Scheduled Job Type stopped = 1 | paused | "Failed — The scheduler is off: the job does not run." | FAIL (message) | The scheduler is on; the jobs are paused on purpose. Fixed: "Needs attention — paused (Stopped)"; scheduler-off still an error; test added. |
| 36 | Band: AI assistant | provider | not connected | "Not configured" | PASS | |
| 37 | Band: Outgoing e-mail | Email Account enable_outgoing | one exists | "Working" | PASS | |
| 38 | Band header "Today, as of" + report links (Revenue by Period, Profit Before/After Shared Costs, Outstanding Receivables) | — | — | open the reports | PASS | All three open and run. |
| 39 | Welcome band / approvals note | counts of the 6 shortcuts | 1 waiting | "1 waiting for your approval" | PASS | |
| 40 | Every link (8 card links, 29 band figures, 7 system links, 3 reports, 6 shortcuts) | — | correct list + filters | 53 routes recorded with their filters | PASS after fixes | Full log in the browser run (tests/e2e/owner_dashboard.js). |
| 41 | Phone width (390 px) | — | no horizontal overflow | 0 px | PASS | Screenshot. |
| 42 | Refresh / cache | band refetched after 30 s; cards by Frappe's card refresh | — | — | PASS | Verified in the dynamic test: a draft booking appeared on reload and disappeared after deletion. |
| 43 | Side effects of dashboard actions | — | none | none | PASS | Every endpoint is read-only (no insert/submit in the code paths; console runs rolled back). |

Totals: 43 components audited. PASS 27, FAIL 9 (all fixed locally), INCOMPLETE 2, NOT CONNECTED 4 (data or upstream),
NOT TESTABLE 1 (production browser rendering: no owner credentials were used; rendering verified on the local site
with the same code).

## 3. Cross-module consistency

- IMED hall bookings and XStudio bookings are kept apart by `resource_type` (Hall vs Studio Service); XStudio's rooms
  are Studio Service resources. No hall data exists in production.
- Cancelled XStudio bookings (32) are excluded from every count and amount; verified by the status cross-tab.
- Revenue is ledger-based (submitted documents); XStudio money is shown but never posted (owner's rule), now at what
  XStudio bills rather than list price.
- Cash, receivables, payables: ledger balances equal ERPNext's `get_balance_on` per account.
- Stock: the owner's chart showed another company's test stock (fixed).

## 4. Dynamic update proof

Local site, controlled record: Studio Bookings This Month 0 → 1, Studio Hours 0 → 2.50, band "Studio held" 0 → 1 and
"Studio hours booked" 0 → 2.5 h after inserting one draft booking; all back to 0 after deleting it. Server-side paths are
covered by the rolled-back integration tests (journal entries, bookings, counter readings, import logs, job types).

## 5. Tests

- Added: `test_xstudio_line_is_what_xstudio_bills_not_the_list_price`, `test_a_paused_job_is_said_to_be_paused_not_a_scheduler_failure`,
  `test_the_xstudio_card_names_the_first_failure` (test_owner_reports.py);
  `test_the_month_s_revenue_leaves_out_the_year_s_closing_and_opening_entries` (test_owner_dashboard.py);
  browser audit `tests/e2e/owner_dashboard.js` (cards vs server, shortcuts vs counts, charts, band vs server, every link, phone width, dynamic step).
- Run: test_owner_reports 37 OK, test_owner_dashboard 5 OK, test_booking 23 OK, test_hall_bookings 33 OK (1 skipped),
  test_xstudio_sync 37 OK. Browser audit: 100 checks pass; 1 known console error (frappe-charts redraw race on
  layout shift, `removeChild` in the chart library, cosmetic).
- Gaps: no automated test of the Number Card/Chart definitions stored in the database (they live outside git); no
  production browser session; charts' Arabic labels (known issue) not re-tested.

## 6. Decisions needed from the owner

1. XStudio completion and payments: studio staff never mark bookings completed or paid in XStudio, so "delivered hours",
   "Completed" and "Paid in XStudio" stay at zero. Either the studio uses those XStudio functions, or these figures
   should be removed from the band.
2. The walk-in booking `b9f026fd…` fails every sync (no customer in XStudio): give it a customer in XStudio, or accept the
   permanent "Degraded" health.
3. IMED halls: no Booking Resource of type Hall exists in production; the hall figures are zeros until the 7 halls are
   created (capacities still awaited).
4. "Collected from Doctors This Month" counts book and app collections together; keep, or make it app-only like the band.
5. Re-run `setup_dashboard.py` on production (after deploy) so the two chart filters take effect; it recreates the
   cards, charts and workspace (same as on 25 Oct).

## 7. Remaining work by business impact

1. Deploy the branch (review → merge to `production` → Coolify redeploy → `setup_dashboard.py`), with the owner's approval.
2. Decisions 1–3 above (they decide whether half the band means anything in production).
3. XStudio sync counters: rows read ≠ unchanged + inserted + updated + failed (44 rows unaccounted per run) — sync.py.
4. Replace "0" by an explicit "not set up" state on the cards whose source has no records (halls, counters), as the band now does.
5. Known issue: Arabic labels in frappe-charts.

## 8. Reliability score

**58 / 100** for the deployed version (e44661a): the wiring is real and read-only, permissions hold, 27 of 43 components
verified correct, but one money figure was wrong (X Studio line), test data of another company was drawn as the group's
stock, two navigation targets were broken, three system messages were misleading, and the dashboard could not tell an
empty ledger from a zero result. With the branch deployed and the setup script re-run: **82 / 100**; the rest depends
on the three data decisions above.
