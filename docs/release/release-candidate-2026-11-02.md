# Release candidate `feature/assistant-chats`, 2 Nov 2026

Status words:
- **Verified:** run here, with the result given.
- **UNVERIFIED:** production, which is not reachable from here.
- **Proposed:** waits for the owner.

Nothing was pushed, merged or deployed, and no production system was touched.

Where the work ran:
- **Feature work:** the worktree `../ibp-feature`. The shared checkout was left detached at the same commit, so
  another process cannot switch the branch under it.
- **Trial merge:** the worktree `../ibp-trial`, on the local branch `trial/merge-origin-production`.

## 1. Owner decisions

No approval of decisions 1 to 3 was found: not in the repository, the docs or the recorded owner decisions. The
owner's earlier rules (four eyes on recoveries, recovery blocked until a written policy) neither settle nor
contradict them. **So none was implemented.** The exact changes, ready to apply once approved:

| # | Proposal | Code to change | Tests to change or add | Effect on data |
|---|---|---|---|---|
| 1 | Only the owner withdraws an owner-approved recovery | `cash_discrepancy.withdraw_recovery`: `frappe.only_for(OWNER_ROLE)` before `get_for_action`; `cash_discrepancy.js`: its button under the owner's group | `test_action_permissions.MATRIX["Withdraw an approved recovery"]` becomes `{OWNER}`; a test that the accountant's direct call is refused and the owner's works | none |
| 2 | No write-off while the owner's decision is pending | `cash_discrepancy.write_off`: drop "Recovery Recommended" from the statuses it accepts; `cash_discrepancy.js`: no Write Off button in that status | a test that write-off of a recommended shortage is refused, and allowed again after the owner returns it | none |
| 3 | A printing sale without enough paper is refused | `paper_use.issue_paper_used` (Sales Invoice `on_submit`): when `on_hand(...) < sheets`, `frappe.throw` instead of saving a draft (the throw rolls back the sale: no revenue, no draft); the lock added on 2 Nov stays, so two sales at once leave the second refused | `test_a_sale_beyond_the_paper_in_store_waits_for_the_accountant` and `..._left_as_draft_goes_with_the_sale` become refusal tests; QA-05's draft handling in stock counts stays for old drafts | existing drafts are settled by section 3's procedure, never rewritten |
| 4 | Assistant stays with its privileged roles | none (`ALLOWED_ROLES` unchanged, isolation kept) | already covered (`test_the_roles_without_the_assistant_are_refused_at_the_door`, browser check below) | none |

## 2. Tests

| Run | Code | Result |
|---|---|---|
| Full app suite | feature (`e5e9858`) | 834 OK, 1 skipped (earlier today) |
| Full app suite | feature merged with `origin/production` (`aec8ceb`) | **834 OK, 1 skipped** |
| Assistant + isolation | feature, on the migrated `restore-test` | 40 OK (after `bde46d4`) + 13 OK |
| Assistant | feature, on `frontend` | 40 OK |

New in this round:
- **`bde46d4`:** an assistant test assumed an empty cash box. The behaviour was right; the test now reads only the
  user's cost centre.
- **Paper drafts diagnostic:** `setup/paper_drafts_report.py`, read-only.
- **Fixtures:** `setup/e2e_fixtures.py`, throwaway site only.
- **Browser suite:** `tests/e2e/chats_and_tiers.js`.

## 3. Paper drafts (read-only diagnostic)

`bench --site <site> execute imed_erp.setup.paper_drafts_report.run`

| Site | Completed sales waiting for paper | Orphan drafts |
|---|---|---|
| `frontend` (local) | 0 | 0 |
| `demo` (local) | 0 | 0 |
| `restore-test` (throwaway) | 2, both made by the concurrency script | 0 |
| production | UNVERIFIED (on 1 Nov it held no invoices) | UNVERIFIED |

If production lists any, the accountant settles each one. Nothing is automated:
1. Receive the missing paper, or correct the store's count, so the store holds the sheets.
2. Submit the draft issue as it is. It is dated the day it is submitted.
3. If the sale was wrong, cancel the sale with its reason; its draft goes with it.

Never back-date a draft, submit it without stock, or delete one.

## 4. Browser validation

Run on the migrated throwaway `restore-test`, after `setup/e2e_fixtures.py`: Sara's sale, the obsolete edition's
copies, the studio-hour price, today's Azarita close, the halls and a tier for قاعة 1.

| Suite | Result | Each non-pass |
|---|---|---|
| `roles.js` | **57 of 57** | — (Sara's sale fixture added; it failed before) |
| `screens.js` | **47 of 47** | the script's own timer prints TIMEOUT after its summary |
| `booking_status.js` | **5 of 5** | — |
| `chats_and_tiers.js` (new) | **10 of 11** | one script error on the desk ("removeChild"), not reproduced in 6 more loads by two users: intermittent, unexplained; saved chats, their privacy and both tier prices pass |
| `workflows.js` | 8 of 11, then its timeout | the transfer is refused because today's close of Azarita (made by the fixture for `close.js`) locks the day, a rule working (fixture conflict); the receipt follows from it; the scrap passes for the loss and the doctor's balance, but the edition keeps 12 "remaining", because the 29 Oct copy records 60 copies of which only 48 ever existed in stock (stale data in the copy, predating today) |
| `close.js` | 6 passed, then 2 timeouts | reopen, the 15 short, Sara's refusals and the write-off offer pass; the weekly-review step timed out while the full unit suite ran in parallel; not re-run |

No non-pass points to a code defect. Two remain open: the intermittent desk error, and the close suite's last
steps, which need a run with nothing else in parallel.

Not covered:
- **`halls.js`:** targets the demo site with saved sessions, so it is outside the throwaway set.
- **The assistant with a real model:** no key exists on the throwaway site.
- **Accuracy of the model's answers:** not tested.

## 5. Staging migration

No copy of production data is available here, since production backups live on the server. The `imedprod` volumes
are the 27 Oct local rehearsal, not production data. **Migration against production data: INCOMPLETE.**

Verified on `restore-test`, a copy of the local site from 29 Oct, whose schema is older than production's:

| Check | Result |
|---|---|
| Backup before | `20261102_164406-restore-test-database.sql.gz` |
| `bench migrate` with this branch | exit 0, no traceback |
| New tables | Assistant Chat, Assistant Message (and Hall Price Tier, which production already has) |
| Unique index `unique_chat_seq` | present |
| Existing data | identical row counts in 13 tables (GL, invoices, bookings, customers, editions, expenses, import logs, stock ledger, journal entries, doctor ledger, users, roles, job types) |
| Permissions | 8 permission rows added: the two new DocTypes, Super Admin and System Manager only |
| Scheduled jobs | the same 3 app jobs before and after |
| Migrate again | identical state (idempotent) |
| Assistant after migrate | 40 + 13 tests OK on that site |
| Recovery | backup restored into the new site `rc-recovery`: identical to the pre-migration state; that copy migrated to the same result |

## 6. Trial merge

`origin/production` was fetched at 4006bd8: two merged design pull requests, sidebar and sign-in.

| Area | Finding |
|---|---|
| Conflicts | none |
| Overlap | `hooks.py`: the remote adds `imed_sidebar.js` and versions the sign-in CSS; merged with this branch's hooks without conflict |
| Permissions | the remote renames the owner's first name in `setup_users.py`; roles unchanged |
| Migrations | the remote has none; this branch adds the two chat DocTypes |
| JS and CSS | the remote: theme CSS, sidebar log-out, the owner dashboard's colours; this branch: booking scripts, five role checks |
| Scheduled jobs and doc events | unchanged by the remote |
| Financial and inventory | the remote has no Python change apart from the owner's name |
| Full suite on the merged code | 834 OK, 1 skipped |

Three more design commits ("Owner Dashboard: ...") sit on `origin/feature/colourful-design`, not on `production`.

## 7. XStudio

- **Booking `b9f026fd`** (26 Oct, Hall 6, 2 h, 500 due) has no customer account in XStudio, only a name. It fails in
  every run with that reason (local logs, 17 runs).
- **Other records are unaffected:** the other rows of each run sync (160 read, 116 unchanged). A new test shows
  that the walk-in makes nothing and that runs repeat safely.
- **Effect:** the integration's health stays "Degraded".
- **Fix in XStudio**, by the studio: give the booking a customer account (with a phone), or cancel it if it was
  never real. The next run then imports or cancels it. Nothing is fabricated here.

Paused scheduler jobs. These were paused on the local site on 25 Oct to keep the XStudio test controlled; their
state in production is UNVERIFIED:

| Job | Purpose | Before release |
|---|---|---|
| `doctor_accrual.run_daily` | counts the doctor's amount on sales the hooks missed (imports) | must run in production; confirm it is not stopped |
| `recurring_expense.run_daily` | drafts the month's recurring expenses and reminders | must run in production; confirm |
| `email_account.pull`, `notify_unreplied` | Frappe's mail | only if mail accounts are set |
| `xstudio.sync.run_scheduled` | every 10 minutes, if XStudio Settings say enabled | confirm enabled and healthy |

Review steps, read-only:
1. List the stopped jobs (section 8).
2. Compare them with this table.
3. Get the owner's word before starting any job.

## 8. Production preflight (all UNVERIFIED until an operator runs them)

```
B=$(docker ps --format '{{.Names}}' | grep -E 'backend' | head -1)
bench() { docker exec "$B" bench --site frontend "$@"; }
bench execute frappe.defaults.get_global_default --args '["company"]'           # expect: Mohamed Mamdouh group
bench execute frappe.db.sql --args '["select @@version, @@innodb_snapshot_isolation, @@transaction_isolation"]'
bench execute frappe.conf.get --args '["imed_assistant_provider"]'               # gemini / claude / empty
bench execute frappe.conf.get --args '["imed_assistant_model"]'
bench execute frappe.conf.get --args '["imed_assistant_api_key"]' | wc -c       # > 5 means set; never print it
bench scheduler status
bench execute frappe.db.sql --args '["select method, stopped from `tabScheduled Job Type` where stopped = 1"]'
bench execute frappe.db.sql --args '["select count(*) from `tabDocType` where name in (\"Assistant Chat\", \"Assistant Message\")"]'  # 0 before migrate
bench execute frappe.db.sql --args '["select count(*) from `tabSales Invoice` where docstatus = 1"]'
docker exec "$B" ls -t /home/frappe/frappe-bench/sites/frontend/private/backups | head -3   # a backup from today
```

Recovery readiness: the off-server restic copy and a restore rehearsal (`docs/deployment/production-hardening.md`).
UNVERIFIED for today's state.

## 9. Deployment runbook (not executed)

1. **Prerequisites:**
   - owner decisions 1 to 3 recorded;
   - this branch merged into `production` by the owner's developer, with a test run on the merged commit;
   - preflight (section 8) recorded;
   - a quiet hour, since Coolify's Redeploy restarts the containers (about 3 minutes).
2. **Backup:** `bench --site frontend backup --with-files`; `gzip -t` the database file, copy it off the server, note
   its name.
3. **Maintenance:** `bench --site frontend set-maintenance-mode on`. XStudio sync and the daily jobs wait; nothing is
   lost, since XStudio stays the source and the next run catches up.
4. **Deploy:** push `production` (the owner's approval), then Coolify, then Redeploy. The image rebuilds the assets.
   Auto-deploy is off.
5. **Migrate**, in the new backend container: `bench --site frontend migrate`. It must end with the after-migrate
   hooks and no traceback. Then `bench --site frontend clear-cache`.
6. **Workers:** `bench scheduler status` is enabled; the queue and scheduler containers are up (Coolify panel);
   `bench --site frontend set-maintenance-mode off`.
7. **Smoke tests:**
   - the owner's sign-in, the dashboard and the sidebar;
   - one booking list and calendar;
   - the Cash Box Balances report;
   - the assistant's status as the owner, and one question, if a key is set;
   - `get_status` refused to the accountant;
   - XStudio Settings' last run within 10 minutes;
   - the paper drafts report.
8. **Post-deployment verification:**
   - the preflight queries again;
   - the two chat tables and the unique index exist;
   - the stopped jobs match the owner's decision;
   - the owner dashboard's figures match the ledger, as in the 1 Nov audit.

**Failed migration:**
1. Keep maintenance on.
2. Read the traceback.
3. If a second migrate does not complete, restore the backup from step 2:
   `bench --site frontend restore <file> --with-private-files ... --with-public-files ...`, as rehearsed in section 5.
4. Redeploy the previous Coolify deployment.
5. Clear the cache and switch maintenance off.

**Rollback without a failed migration:** redeploy the previous deployment. Database compatibility:
- The new tables and permission rows stay; the old code never reads them.
- The two DocType records remain, so opening Assistant Chat in the desk shows an error until the branch returns.
- No column or data of an existing table changes, so no data restore is needed.

## 10. GO / NO-GO

| Item | Status | Blocker |
|---|---|---|
| Code ready for review | GO | — |
| Code ready for merge | NO-GO | owner decisions 1 to 3 (each changes what this branch should contain) |
| Code ready for deployment | NO-GO | merge; preflight (section 8); fresh backup |
| Verified production readiness | NOT VERIFIED | production not reachable; migration not tried on production data |
| Assistant, owner only | GO for merge | production provider settings |
| Assistant, restricted users | NO-GO | policy (decision 4: stays closed) |
| XStudio | CONDITIONAL | walk-in fixed in XStudio; production jobs and health checked |
