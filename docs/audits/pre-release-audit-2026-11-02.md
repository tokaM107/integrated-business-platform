# Final pre-release audit and business-rule verification, 2 Nov 2026

Branch `feature/assistant-chats`, audited against `production` (`6a60cc1`) and the remote `origin/production`
(`4006bd8`). Nothing pushed, merged or deployed. No production access, credentials or writes.

Each fact is marked **verified** (a test or run in this audit), **code reading** (seen, not executed) or
**UNVERIFIED** (depends on an environment not reachable here).

## A. Verified fixes

| Fix | Files | Evidence |
|---|---|---|
| Assistant: company must be readable by the user; reports, cards and the band only within that company | `assistant/core/context.py`, `tools/*.py`, `businesses/imed.py`, `memory/chat_memory.py` | `test_assistant_isolation` 13 OK; 5 of 10 attacks succeeded on the old code |
| Assistant reports fail closed: company-scoped only if the screen declares the filter **and** the code reads it | `assistant/tools/reports.py` | Every such report run for a one-company user and a two-company user with the other company's marked rows; the test fails when forcing is removed (shown) |
| Legacy chats bound only by their own user | `memory/chat_memory.py` | `test_nobody_claims_another_user_s_legacy_chat` |
| Doctor accrual counted once under concurrency | `imederp/doctor_accrual.py` | Two-session run in both database modes: 1 ledger entry, 1 journal entry, equal amounts, linked |
| Printing sale not refused for paper under concurrency | `imederp/paper_use.py` | Two-session run in both modes; unit test for the lock |
| Weekly review, edition sold count, purchase into the damaged store | earlier pass | Two-session runs show the old code wrong (2 reviews; sold count 1 of 2) |
| XStudio: batched customer lookups; real error on a deadlock | `imederp/xstudio/sync.py` | 2 tests fail on the old code; sync 41 OK |
| Button visibility aligned with the server | 5 JS files | `test_action_permissions` (24 user-action checks, direct calls); browser check |

## B. Remaining defects

| Severity | Defect | Evidence | Action |
|---|---|---|---|
| Medium | With snapshot isolation on (MariaDB 11.8), two documents of one naming series saved at the same moment refuse one with error 1020 ("try again") | Two-session runs | Frappe platform behaviour; inform users; verify production setting |
| Low | `cash_handover.cancel_handover` loads the document before any role check, so a user without access learns whether a name exists | Code reading | Optional: check read permission first |
| Low | The XStudio walk-in booking fails every run and keeps the integration health "Degraded" | Local logs: 17 runs | Fix at source (owner's earlier direction); see section C |
| Info | Browser suites need fixtures the throwaway site lacks | Runs in section E | Fund boxes and add a sale on the throwaway copy before a run |

## C. Business-rule changes

**Paper use: changed in two edge cases.** Verified by running both versions of the check on the same data.

| Case | Before | After |
|---|---|---|
| Enough paper | issue submitted with the sale | same |
| Not enough paper at the sale's time | sale stands, issue saved as a draft for the accountant (since 12 Oct, in code and tests) | same |
| Two simultaneous sales, paper for one | second sale refused (negative stock) | second sale stands, its issue a draft |
| Back-dated sale, enough paper then, not now | sale refused (negative stock) | sale stands, issue a draft |

What follows from the draft rule (code reading, unchanged by this branch):
- Until the draft is submitted, the sale's revenue is posted but its paper cost and stock movement are not. Paper
  stock is shown higher and the cost lower until then.
- The draft is dated the day the accountant submits it, so the cost can land in a later month than the sale.
- The approvers are notified (`paper_issue_pending`), and a stock count treats the draft as gone (QA-05).
- Consumption cannot be recorded twice. The draft is the sale's only issue, it is cancelled with the sale, and a
  refused or retried sale rolls back with its draft.
- A draft that is never submitted stays a draft. Nothing escalates it after the first notice.

The draft rule itself has no recorded owner approval. Its extension to the two cases above needs one (decision 3).

**Doctor accrual:** amounts and entries unchanged. Only locking was added.
- **Retries:** a retried run adds nothing (existing tests).
- **Rollback:** a dropped transaction leaves nothing; the next run counts the sale.
- **Different branches:** each invoice is locked on its own, so sales of different branches don't wait on each
  other.

**XStudio:** contract unchanged. It makes GET calls only, posts nothing (`test_money_is_read_as_it_is_and_never_posted`),
looks back 30 days and ahead 60 by default, and makes up no customer.

The walk-in booking (`b9f026fd`, 26 Oct) fails because XStudio has no customer account for it. It holds a name
and no phone. The failure is missing data at the source:
- **Not mapping or time:** the error comes from the customer check, not from a field mapping or time conversion.
- **Other records unaffected:** 160 rows read and 116 unchanged per run; only this one fails (verified, local logs).
- **Retries are safe:** each run makes nothing for it and nothing twice (new test).
- **ERP-side fix not done:** importing it without a customer, or with an invented one, would change the
  integration contract.

## D. Owner decision register

| # | Decision | Current behaviour | Risk | Recommended | If changed |
|---|---|---|---|---|---|
| 1 | Accountant withdraws an owner-approved recovery | allowed (Accounts Manager) | owner's decision undone alone | owner only | one role check; employees' pending recoveries unaffected |
| 2 | Accountant writes off a shortage awaiting the owner | allowed | the company bears a loss the owner was asked to rule on | refused while a recommendation waits | one status removed from the allowed list |
| 3 | Deferred paper consumption, and its extension to simultaneous and back-dated sales | sale stands, issue a draft | cost and stock wrong until the draft is submitted | keep, with a weekly reminder of open drafts | reverting refuses the sale in those cases |
| 4 | Assistant for restricted users | Super Admin and System Manager only | restricted users would get only the 4 company-scoped reports | keep closed until reports take a company filter | open `ALLOWED_ROLES`; review each report |
| 5 | XStudio walk-in booking | fails every run | health stays "Degraded" | studio adds a customer or cancels it in XStudio | — |

BA Plus import keys and the hand-over receipt's EGP wording are kept as they are.

## E. Test results

| Run | Result |
|---|---|
| Full app suite, last run before this audit | 830 OK, 1 skipped |
| Full app suite, final run (this audit) | **834 OK, 0 failures, 1 skipped** (the same skip as in every run) |
| Assistant isolation | 13 OK |
| Assistant | 40 OK |
| Action permission matrix | 1 test, 24 checks OK |
| XStudio sync | 41 OK |
| Concurrency scenarios, throwaway site | 5 of 5 in each of the two database modes |

Browser suites on the throwaway site. The first run competed with the unit suite. For the second, the boxes were
funded on the throwaway site only, and nothing else was running.

| Suite | Result | Cause of each non-pass |
|---|---|---|
| `roles.js` | 55 of 56 | no sale of Sara's on the site to test a return (fixture) |
| `screens.js` | 47 of 47 (second run) | its timer printed TIMEOUT after the summary, once every check had run |
| `workflows.js` | 8 of 10 (second run), then its 8-minute timeout | the scrap step needs an obsolete edition with copies left (README); the studio booking is refused because the throwaway site has no studio-hour price (the rule: no fixed rent without a price) |
| `close.js` | not run | needs a submitted close of Azarita today |
| `booking_status.js` | 5 of 5 | — |

None of the non-passes points to a code defect. Each is a rule refusing a missing fixture, verified for the
expense approval by calling it.

Environment limits:
- `restore-test` is a 29 Oct copy, not migrated. It lacks Assistant Chat, Assistant Message and Hall Price Tier,
  so the assistant's saved chats and hall tiers can't be tested in a browser there.
- No test ran against production.

## F. Release checklist

**Before merge**
1. Owner decisions 1 to 3 recorded, whichever way they go.
2. Code review of `feature/assistant-chats` (27 commits since `production`).
3. Merge with `origin/production` (`4006bd8`, the sidebar and sign-in design work). A trial merge is
   conflict-free, and the merged `hooks.py` compiles (verified). Run the full suite on the merged tree.
4. Re-run the browser suites on a migrated throwaway copy with funded boxes and a sale of Sara's.

**Before deployment**
1. Fresh backup.
2. Read-only checks of production, below.
3. Plan for `bench migrate`: it creates the two chat tables and the unique index.

**After deployment**
1. `bench --site frontend migrate`.
2. Assistant settings (provider, model, key) set by the user. The key never goes in git.
3. The read-only checks again, the owner's dashboard against the ledger, and one assistant question as the owner.
4. Paused jobs: confirm the daily doctor accrual and recurring-expense jobs run in production. They were paused
   only on the local site, on 25 Oct, to keep the XStudio test controlled. Do not start them without the owner's
   word.

**Optional technical debt**
- Hand-typed library maps.
- Account names held as constants.
- Five cash readings: they agree (tested) and are kept apart.
- A permission check before loading the hand-over in cancel.
- A reminder for old paper drafts.

### Read-only checks for an authorised operator (all UNVERIFIED here)

```
B=$(docker ps --format '{{.Names}}' | grep -E 'backend' | head -1)
docker exec $B bench --site frontend execute frappe.defaults.get_global_default --args '["company"]'
docker exec $B bench --site frontend execute frappe.db.sql --args '["select @@version, @@innodb_snapshot_isolation, @@transaction_isolation"]'
docker exec $B bench --site frontend execute frappe.conf.get --args '["imed_assistant_provider"]'
docker exec $B bench --site frontend execute frappe.conf.get --args '["imed_assistant_model"]'
docker exec $B bench --site frontend execute frappe.db.sql --args '["select method, stopped from `tabScheduled Job Type` where stopped = 1"]'
docker exec $B bench --site frontend scheduler status
```

Never print `imed_assistant_api_key`. To check that one is set without showing it:

```
docker exec $B bench --site frontend execute frappe.conf.get --args '["imed_assistant_api_key"]' | wc -c
```

A result above 5 means a key is set.

## G. Go / No-Go

The four levels:
- **Code ready for review:** every module.
- **Code ready for merge:** after owner decisions 1 to 3 and the merged-tree run.
- **Code ready for deployment:** after the read-only checks and the migrate plan.
- **Verified production readiness:** none, because production was not reachable.

| Module | Status | Verified | Environment-dependent |
|---|---|---|---|
| Core ERP | NO-GO until merged and checked | suite, schema diff (2 new DocTypes, no patches, no scheduler change) | migrate, default company |
| Accounting and cash | CONDITIONAL | cash readings agree; permission matrix; receivables filter | decisions 1 and 2 |
| Library and inventory | CONDITIONAL | accrual and paper races; damaged-store guard | decision 3 |
| Bookings and packages | READY for merge | rules in one place; imported packages never billed; browser check | — |
| XStudio integration | CONDITIONAL | contract unchanged; walk-in isolated | walk-in at source; production jobs and health |
| Assistant, owner only | READY for merge | isolation, read-only guard, chats | provider settings in production |
| Assistant, restricted users | NO-GO | isolation enforced and tested | decision 4 |

## H. Git summary

Branch `feature/assistant-chats`, 27 commits ahead of local `production` (`6a60cc1`, unchanged since 1 Nov 18:14).

- **Commits of this audit:** `27fda58` (reports fail closed, legacy chats), `dbaaef0` (walk-in and permission-matrix
  tests), and this report.
- **Earlier today:** `0d75207`, `ad0fad7`, `ff63509`, `bab3b59`, `5d675a7`, `975fb26` (hardening) and `b79a1ca`..`daff751`
  (refactor).
- **Remote:** `origin/production` is at `4006bd8`, two merged design pull requests ahead. They came from automatic fetches
  at 12:08, 13:03 and 14:51, not from this task. A trial merge is clean.
- **Scope of changes:** 110 files differ from `production`. The schema change is two new DocTypes. There are no patches,
  no scheduler change and no committed secret (pattern scan of the diff).
- **The 14:07 switch:** the reflog shows only "checkout: moving from feature/assistant-chats to production" at 14:07.
  The working tree was clean, and I switched back at 14:12. Git records no actor, so the cause is not established.
  Automatic fetches run in this checkout, so another process uses it; future work belongs in its own worktree
  (`git worktree add ../ibp-feature feature/assistant-chats`).
- **Throwaway site only (`restore-test`):** `_Conc` records, test users' passwords and cash-box funding. Never `frontend`
  or production.
