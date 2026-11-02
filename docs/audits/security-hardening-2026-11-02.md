# Post-refactoring security hardening, concurrency fixes and independent validation, 2 Nov 2026

Branch `feature/assistant-chats`, commits `0d75207`..`5d675a7` on top of the refactor (`c616ab7`..`daff751`).
Nothing pushed, merged or deployed. No production access was used: a read-only production check had been refused
by the sandbox, and none was attempted again.

Facts are marked **verified** (shown by a test or a run in this pass), **code reading** (seen in the code, not
executed) or **unverified** (an assumption about another environment).

## A. Executive summary

- Before this pass, a user with Company restrictions who could open the assistant could read other companies'
  data through reports, dashboard cards and the owner's band. A default company the user may not read was also
  accepted. **Verified:** 5 of 10 attacks succeed on the previous code, 0 of 11 on the new code.
- The assistant is still reachable by Super Admin and System Manager only (`assistant/api.py`).
- Two real races were reproduced with two committed sessions, then fixed:
  - Running the daily doctor accrual twice posted the doctor's amount twice.
  - Two printing sales on the last paper refused the second sale.
- Three fixes from the earlier pass were shown to be needed: weekly review, edition sold count, purchase into the
  damaged store. One was shown to be unnecessary as a race fix: the subscription double was already stopped by a
  database deadlock.
- On the database version in use, MariaDB 11.8 with snapshot isolation on, most lost updates turn into a
  "try again" refusal instead of silent corruption. The fixes make correctness independent of that setting.
- The two recovery permission gaps are confirmed and left unchanged. They are owner decisions.

## B. Security findings

| # | Severity | Where | Exploit | Root cause | Fix | Evidence |
|---|---|---|---|---|---|---|
| S1 | High | `assistant/core/context.py` `build_context` | A user sets their own default company to one they may not read; every scoped read then uses it | The default was taken without a check | The company must be in the user's readable companies (`get_list("Company")`, user permissions apply); otherwise the site default, the only readable one, or refusal | `test_the_request_s_company_is_one_the_user_may_read`, `test_no_readable_company_no_assistant` (both fail before) |
| S2 | High | `assistant/tools/reports.py` | `run_report` on any app report (none takes a company filter, verified by reading all 22) returns every company's rows; a company filter sent by the model was not checked | No company constraint on reports | A report that declares a company filter has it forced to the request's company; any other report only for a user who may read every company | `test_a_report_runs_for_the_request_s_company_or_not_at_all` (fails before) |
| S3 | High | `assistant/tools/dashboard.py`, `businesses/imed.py` `OwnerBandTool` | The cards and the band read the group's figures with no company limit | Same | Offered and run only for a user who may read every company | `test_the_dashboard_and_the_owner_s_band_...` (fails before) |
| S4 | Medium | `assistant/tools/records.py` `scoped` | A DocType without a company field (Booking) was read across companies; with no company resolved, nothing was scoped | Scoping only on a `company` field | Restricted users: cost-center scoping; no company: refused | `test_records_and_counts_...` |
| S5 | Medium | `assistant/tools/ledger.py` | With no company resolved, any readable account's balance | Check skipped when company empty | Always checked (company always resolved) | `test_an_other_company_s_account_balance_is_refused_even_to_the_owner` |
| S6 | Medium | `assistant/memory/chat_memory.py` | A chat with no company (saved before the field existed) usable in any company | Empty company skipped the check | Bound to the first company it is used in, then refused elsewhere | `test_a_chat_is_never_reused_in_another_company` (fails before) |
| S7 | Low | `assistant/tools/base.py` `read_only` | A read could queue a background job that runs later outside the guard | Guard covered SQL only | `frappe.enqueue` refused inside a read | `test_a_read_can_neither_stack_a_write_nor_queue_a_job` |
| S8 | Info | read-only guard | Stacked statements (`select 1; delete ...`) | — | Already refused by the connection (error 1064), now pinned by a test | same test |

Write protection, rechecked:
- **Raw SQL (code reading):** on MariaDB every query goes through `Database.execute_query`, which the guard
  replaces. DDL commits first, and a commit is refused inside a tool.
- **Driver cursor (code reading):** reaching the driver cursor directly would bypass the guard. No tool does.
- **Prompt injection (verified):** a ledger row's text told the model to read company B. The model obeyed in
  the test, and every resulting read was refused by the server, so nothing of B reached the answer. Injection can
  still change an answer's wording. It cannot widen what is read.

## C. Concurrency findings

The script `setup/concurrency_check_integrity.py` runs two committed sessions at once on the throwaway
`restore-test` site. It refuses the main site. Each scenario ran twice:
- with snapshot isolation as configured, which is ON on 11.8.9;
- with it switched OFF for the two test sessions, which is how MariaDB before 11.6 behaves.

| Race | Before | After | Root cause and fix |
|---|---|---|---|
| Daily doctor accrual run twice | OFF: 2 ledger entries, 2 journal entries | 1 and 1 in both modes | Check-then-insert unlocked; invoice locked, lines read with a locking read (`doctor_accrual.accrue`) |
| Two printing sales, paper for one | OFF: second sale refused (NegativeStockError) | both stand, one issue submitted, one draft; ON: second refused as retryable 1020 | Unlocked stock read; Bin locked, sheets never above what the store holds now (`paper_use.on_hand`) |
| One week reviewed twice | OFF: 2 reviews | 1 | Fixed in the previous pass (lock); shown needed here |
| Two sales of one edition | OFF: 2 sales, sold count 1 | sold 2 | Fixed in the previous pass (locking reads); shown needed |
| Same student twice | 1 kept (deadlock) | 1 kept, clear message | Previous fix not needed for integrity; it turns a deadlock into a validation error |
| Deadlock inside a run | the missing savepoint's error replaced the real one | the real error | `doctor_accrual.catch_up`, `xstudio.sync.find_missing` |

**Platform behaviour (verified locally, unverified in production):** with snapshot isolation on, two documents of
the same naming series saved at the same moment cause one refusal with error 1020. Frappe shows it as a deadlock
(HTTP 508) and the user retries. This is Frappe on MariaDB 11.8, not this app. Production's compose file uses
`mariadb:11.8`, but its live setting was not read.

**Cash balances:** five readings, one formula (debit less credit, cancelled rows left out). They differ only in
date window and locking, and each matches its use. A test shows they agree on the same rows. They were not merged.

## D. Regression results

Full app suite (guarded runner, MariaDB 11.8.9, site `frontend`): **830 tests, 0 failures, 1 skipped** (the same skip as before this pass). Before this pass: 812. Targeted runs in this pass:

| Suite | Result |
|---|---|
| assistant | 40 OK |
| assistant isolation (new) | 11 OK |
| doctor accrual | 16 OK |
| paper use | 13 OK |
| cash balance | 7 OK |
| XStudio sync | 40 OK |
| booking | 28 OK |
| edition sales | 17 OK |
| doctor statement | 15 OK |
| damaged stock | 16 OK |

Browser check on the throwaway site: `tests/e2e/booking_status.js` passed 5 of 5. Concurrency scenarios: 5 of 5
pass in both modes after the fixes.

Not executed:
- The other browser suites (roles, screens, workflows, close). They need every test user's password on the
  throwaway copy.
- Any test against production.

## E. Business rule preservation

| Changed path | Why the rule is unchanged |
|---|---|
| Doctor accrual | Same entries and amounts; only locking added; second run still adds nothing (existing tests) |
| Paper use | Same rule (a sale is never refused for paper; short paper waits as a draft); the comparison also takes the store's current quantity, which ERPNext's own negative-stock check already enforces |
| XStudio sync | Same reads, same matching, same window (lookback 30, lookahead 60 days by default), still GET only and nothing posted (`test_money_is_read_as_it_is_and_never_posted`) |
| Booking screens | Same colours and statuses, now sent by the server |
| Client role checks | Buttons now shown to the roles the server already allowed; no server permission changed |
| Assistant | Only narrows what a restricted user reads; the owner's reads unchanged (all owner tests pass) |

## F. Outstanding owner decisions (not changed)

| Issue | Current behaviour (code reading, `cash_discrepancy.py`) | Risk | Recommended policy |
|---|---|---|---|
| Withdrawing an approved recovery | `withdraw_recovery` needs Accounts Manager or System Manager only; no owner check | The accountant alone undoes the owner's decision; the employee is no longer charged | Owner only, or owner informed and confirms |
| Writing off a pending shortage | `write_off` accepts "Recovery Recommended" (waiting for the owner) | The accountant settles a case the owner was asked to decide; the company bears the loss | Refuse write-off while a recommendation waits, unless the owner returns it |
| BA Plus import keys | two formats | Unifying rewrites stored keys | Keep; document |
| Hand-over words in EGP | fixed currency | Only if another currency is used | Keep |

## G. Production readiness

| Area | Status | Blocker |
|---|---|---|
| Core ERP | CONDITIONAL | Nothing of this branch is deployed; the full suite must pass on the deployed image; production's default company and snapshot isolation setting are unverified |
| Accounting and cash | CONDITIONAL | The two recovery permissions wait for the owner |
| Library and inventory | CONDITIONAL | Paper and accrual fixes need deploying; the remaining hand-typed library maps work but are debt |
| Bookings and packages | READY on this branch, not deployed | — |
| XStudio integration | CONDITIONAL | Paused jobs in production (earlier memory) and the one walk-in booking that fails every sync remain |
| AI assistant, owner only | CONDITIONAL | Ready on this branch; production needs the provider settings and this branch deployed |
| AI assistant, restricted users | BLOCKED | Isolation is enforced server-side, but restricted roles cannot reach the assistant by policy (`ALLOWED_ROLES`). Opening it to them is a policy change, and its report surface would mostly be refused. That needs a decision and a review of each report. |

## Configuration check (UNVERIFIED in production)

An authorised operator can read both values without changing anything:

```
docker exec <backend-container> bench --site frontend execute frappe.defaults.get_global_default --args '["company"]'
docker exec <backend-container> bench --site frontend execute frappe.db.sql --args '["select @@innodb_snapshot_isolation, @@version"]'
```

If the default is not "Mohamed Mamdouh group", the owner's figures still read the group (they name it). The
assistant then uses the owner's own default, or the only company they may read.

## H. Git summary

Branch `feature/assistant-chats`. New local commits: `0d75207` (assistant isolation), `ad0fad7` (concurrency), `ff63509` (cash readings test), `bab3b59` (frontend), `5d675a7` (XStudio), and this report. Nothing pushed, merged or deployed. On the throwaway `restore-test` site only: `_Conc` test records were committed by the concurrency script, and the owner's test password was set for the browser check.
