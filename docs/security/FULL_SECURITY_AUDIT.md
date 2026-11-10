# Full security audit and remediation, 10 Nov 2026

Branch `security/full-audit-2026-11-10`, made from `production` at `9fd3569`. Commits `04fa30e`, `8d2d7c6`,
`889c24c` and this report. Nothing was pushed, merged or deployed. No production system was contacted, with one
exception recorded in section I.

Each fact is marked **verified** (a test or a run in this audit showed it), **code reading** (seen in the code,
not executed) or **unverified** (depends on a system the audit could not reach).

This audit does not show the system is secure. It shows what was looked at, what was found, and what was fixed.

## A. Executive summary

**Posture.** The framework-level controls are sound: no endpoint is open to guests, passwords and CSRF are
Frappe's own, SQL is parameterised, and the assistant reads only what its user may read. The weak point was
inside the app's own documents: fields the screen shows as read-only were accepted from any request.

**Major vulnerabilities found (all reproduced, then fixed):**

- A branch manager could cancel any posted Journal Entry of any branch through a Cash Handover (D1).
- A branch manager could record a student's cash payment that posted nothing to the ledger, so the cash could be
  taken without a shortage showing (D2).
- The accountant could approve a salary recovery, or erase a shortage, with a plain save, without the owner (D3).
- A branch manager could take over another branch's draft by saving it with her own branch on it (D4).
- Sessions lasted 170 hours of inactivity with no total limit (S1).

**Most important risks that remain (need the owner or the server):**

- An old initial user password is in the public git history. Any account that never changed it is open (I1).
- Coolify's dashboard is reachable from the internet over plain HTTP (I2).
- Production still runs the code without these fixes until this branch is reviewed and deployed.
- The library connector's one shared key can write any library's mirrored documents (X2).

**Counts.** 0 Critical, 6 High, 18 Medium, 26 Low. 18 are fixed and verified, 4 fixed but not verified,
4 partially fixed, 24 open or waiting for approval.

**Release recommendation:** CONDITIONALLY READY (section K).

## B. Scope and coverage

| Area | What was done | Status |
|---|---|---|
| Custom app `apps/imed_erp` (29,000 lines of Python outside doctype folders, plus doctypes) | Every `@frappe.whitelist` function (78), every report (22), every doctype's permissions, hooks, scheduled jobs | Reviewed, with the gaps listed below |
| AI assistant | Endpoints, six tools, read-only guard, prompts, chat storage, browser rendering | Reviewed |
| XStudio sync, library sync, BA Plus import, App Payment import, notifications | Client, sync, mappers, settings, receiving endpoint, Windows connector | Reviewed |
| Authentication and sessions | Frappe 16.35.0 source (`auth.py`, `sessions.py`), local System Settings, live HTTP checks on the local site | Reviewed |
| Deployment files | `compose.coolify.yaml`, `deploy/`, `frappe_docker/`, `scripts/`, `.dockerignore`, `.gitignore` | Reviewed |
| Secrets | Tracked tree, full git history of every branch (1,323 commits), untracked `.env` (names only), `local/` | Reviewed with a manual pattern scan (gitleaks not installed) |
| Dependencies | `pip-audit` on the bench's 162 installed packages, `npm audit` on the browser tests, `bandit` on the app | Run |
| File upload and download | Frappe's own; the app adds one check (the signed receipt of a hand-over) | Reviewed by code reading only |

**Not inspected (unverified):**

- Live production: site configuration, user roles and User Permissions, Custom DocPerm, open ports, firewall,
  SSH, backups, Coolify settings, the proxy's headers.
- Frappe and ERPNext themselves, beyond the session and auth code. Their standard endpoints
  (`/api/resource`, file upload, reports) are trusted as shipped.
- Feature branches not merged into `production` (Sparkle halls, BA Plus scraping and others).
- The bodies of `edition_sales.py`, `booking_pricing.py` and the report
  `profit_before_and_after_shared_costs` (searched for queries and permission calls, not read line by line).
- `scripts/library_connector/collect_metadata.ps1`.
- XStudio's own server and the Cloudflare Worker relay in front of it.
- WebSocket (socket.io) traffic: Frappe's own, not reviewed.
- Tools not available and not run: gitleaks, trufflehog, semgrep, trivy.

## C. Vulnerability register

Status values: Fixed and Verified, Fixed but Not Verified, Partially Fixed, Open, Requires Approval.
Paths are under `apps/imed_erp/imed_erp/` unless they start with `deploy/`, `scripts/` or `compose`.

### High

| ID | Component | Location | Vulnerability | Impact | Status | Verification |
|---|---|---|---|---|---|---|
| D1 | Cash Handover | `imederp/doctype/cash_handover/cash_handover.py` | `journal_entry` accepted from the request; cancelling the hand-over cancelled the entry it named | A branch manager cancels any branch's posted entry, on closed days too | Fixed and Verified | `test_a_hand_over_cannot_be_used_to_cancel_someone_elses_journal_entry` (failed before) |
| D2 | App Payment | `imederp/doctype/app_payment/app_payment.py` | Sent with `journal_entry` set, it was submitted without posting | Cash taken with no shortage in the books | Fixed and Verified | `test_a_payment_always_posts_its_own_entry` (failed before) |
| D3 | Cash Discrepancy | `imederp/doctype/cash_discrepancy/cash_discrepancy.py` | Status, amount, approver and payroll fields writable by a plain save | The accountant approves a recovery without the owner, or erases a shortage | Fixed and Verified | `test_a_discrepancys_decision_is_changed_only_by_its_actions` (failed before) |
| I-backup | Image | `deploy/Containerfile`, `.dockerignore` | The nightly backup script the Coolify task runs was not in the image | The scheduled backup fails every night if it is the one in use | Fixed and Verified in the repository | Local image build: the script is present and parses. Which job runs in production: unverified |
| I1 | Secrets | git history, `setup/setup_users.py` (commits `d26d660`, `dd63d1e`) | A fixed initial user password is in public history | Any account never changed since September can be signed into | Open | Requires production access: force password resets |
| I2 | Server | `deploy/vps_harden.sh` default, deployment doc | Coolify dashboard (8000) and realtime ports public over HTTP | Control of the server and every secret on it | Requires Approval | Owner decision of 29 Oct 2026 to reverse |

### Medium

| ID | Component | Location | Vulnerability | Impact | Status | Verification |
|---|---|---|---|---|---|---|
| D4 | All documents | Frappe checks write permission on the new values only | Another branch's draft (or any Booking) taken over by saving it with one's own branch | Cross-branch read and change of drafts and bookings | Fixed and Verified | `test_another_branchs_draft_cannot_be_taken_over_by_rewriting_its_branch` (failed before), on Treasury Close; the hook covers every doctype |
| D5 | Cash Handover | same file | `handed_over_by` taken from the request at submit | The accountant records a hand-over to himself in a manager's name and confirms it alone | Fixed and Verified | `test_the_person_handing_over_is_the_one_who_submits…` (failed before) |
| D6 | App Subscription, Printer Reading | `imederp/doctype/app_subscription/`, `printer_reading/` | The derived cost center is not checked against the user; a reading bypassed "use the day's screen" by naming a link | Any branch manager posts a platform fee on any course; any Accounts User moves any library's counter | Partially Fixed | Printer Reading fixed (existing 867-test suite passes, no attack test). Subscription rule: owner decision |
| D7 | Treasury Close | `imederp/doctype/treasury_close/treasury_close.py` | `cash_discrepancy` and `amended_from` accepted from the request | A manager makes her own shortage disappear on a reopen; a close is back-dated | Fixed and Verified | Two tests for the discrepancy part (failed before). The `amended_from` check has no attack test |
| S1 | Sessions | System Settings (170 h), no total age | Sessions effectively never expired | A stolen or forgotten session stays usable for a week | Fixed and Verified | 8 unit tests and live HTTP checks (section E) |
| X1 | XStudio sync | `imederp/xstudio/sync.py` `upsert_customer` | A customer matched by phone was renamed from XStudio, where anyone registers with any phone | A doctor's or student's name overwritten, possibly with HTML | Fixed and Verified | `test_a_customer_the_erp_already_had_keeps_its_name…` |
| X2 | Library sync | `imederp/library_sync/sync.py`, `setup/setup_library_connector.py` | One API key for both PCs; library, branch map and status codes come from the request | The key's holder rewrites any library's mirrored documents | Open | Needs one user per PC and a server-side map |
| X3 | Endpoints | 9 functions | State-changing endpoints accepted GET, which skips the CSRF check | A link opened by a signed-in accountant imports forged library documents | Fixed and Verified | `test_each_state_changing_endpoint_refuses_get`; live: GET answers 403 |
| A1 | Booking payments | `imederp/booking_accounts.py` | The Payment Entry was posted as Administrator with no record of who took the money | A cash receipt cannot be attributed in a shortage investigation | Fixed but Not Verified | Written to the entry's remarks and a comment on the booking; no dedicated test |
| K1, K2 | Cash Discrepancy | `withdraw_recovery`, `write_off` | The accountant alone undoes the owner's approval, or settles a case the owner was asked to decide | Segregation of duties | Requires Approval | Known since 2 Nov 2026; unchanged |
| I3 | Firewall script | `deploy/vps_harden.sh` | A comma list of ports was passed to one iptables rule, which refuses it | Closing all four ports aborted half-way | Fixed but Not Verified | Shell syntax checked; not run on Linux |
| I4 | Compose | `compose.coolify.yaml` | The database root password and backup credentials are in the web containers | One code-execution bug gives database root and the backups | Requires Approval | |
| I5 | Release process | no CI; auto-deploy | A push to `production` ships with no test, review or secret scan | Unreviewed code in production | Open | |
| I6 | Images | `deploy/Containerfile`, compose | Pinned by tag, not digest | A changed upstream image is deployed unnoticed | Open | |
| I7 | Dependencies | base image packages | `pip-audit`: 114 known advisories in 13 packages; no lock file | See section I | Open | Needs a newer base image and a compatibility test |
| I8 | Backups | `scripts/backup_offsite.sh`, `deploy/*.sh` | Plain backup sets copied or left behind; cleanup matched only 2026 | Database dump and encryption key readable where they are left | Partially Fixed | Cleanup pattern fixed; the rest open |
| I9 | Headers | proxy | No Content-Security-Policy | Less protection if an XSS is found | Open | Already documented as pending |
| I10 | Repository | deployment docs and scripts | The server's address, domain, container names and its unhardened state are in a public repository | Helps an attacker aim | Open | |

### Low

| ID | Component | Location | Vulnerability | Status | Verification |
|---|---|---|---|---|---|
| A2 | Booking payments | `booking_accounts.py` | A request id of another booking answered with that booking's payment | Fixed and Verified | 2 tests |
| A3 | Material Request | `material_issue.py` | A brace in the rejection reason broke the rejection | Fixed and Verified | 1 test |
| A4 | Owner figures | `owner_dashboard.py`, `owner_figures.py` | Gated by role only, not by company permissions | Open | Not exploitable with today's users (code reading) |
| A5 | Period lock | `period_lock.py` | Posting as Administrator passes a closed period that has an exempt role | Open | Depends on site data |
| A6 | Damaged stock | `damaged_stock.py:70` | `default_damaged_store` has no permission check (returns one store name) | Open | Accepted |
| A8 | Doctor reports | `report/doctor_debts`, `doctor_statement` | Relied on the report's roles alone | Fixed and Verified | 1 test |
| A9 | Reports | several | No required date range; unbounded work in one request | Open | |
| D8 | Transfer, Damaged Stock Sale, Stock Count, Hour Package | doctype folders | Links to posted documents accepted from the request | Fixed but Not Verified | Suite passes; no attack tests |
| D9 | Inter Business Transfer | `confirm_receipt` | Ran on the browser's copy of the document | Fixed but Not Verified | Suite passes |
| D10 | Doctor Ledger Entry | `doctor_ledger_entry.py` | `sales_invoice` settable makes an adjustment skip approval (Accounts Manager only) | Open | |
| D11 | Cash Handover | `confirm_receipt` | The error names the receiver of any hand-over to any signed-in user | Open | |
| D12 | ERPNext rights | site | Accounts User keeps standard rights outside the permission matrix | Open | Unverified on the site |
| X4 | Assistant | `assistant/tools/records.py` | Mirrored payloads (whole imported files) could be sent to the model | Fixed and Verified | 1 test |
| X5 | XStudio | `xstudio/client.py`, `sync.py` | Remote text shown as HTML | Fixed and Verified | 1 test for the error text; hall names by code reading |
| X6 | XStudio | settings, client | http allowed by address prefix; login followed redirects | Fixed and Verified | 2 tests |
| X7 | Library sync | `library_sync/sync.py` | No bounds; one malformed element lost the batch | Fixed and Verified | 2 tests |
| X8 | Assistant | `assistant/api.py` | Rate limit per address only | Fixed and Verified | 1 test |
| X9 | Assistant | `assistant/core/prompts.py` and others | Prompt-injection containment gaps | Partially Fixed | Tag case fixed and tested; summary and planner prompt open. Impact is a misleading answer, not wider access |
| X10 | Library connector | `scripts/library_connector/` | Key in a plain file on a shop PC; http was accepted | Partially Fixed | https now required; file permissions are a PC task |
| I11 | Compose | | No `no-new-privileges`, capability drop or resource limits | Open | |
| I12 | Redis | | No password (not published; safe unless on a shared network) | Open | Unverified |
| I13 | Scripts | `deploy/restore_site.sh` | Secrets on command lines | Open | |
| I14 | Dev compose | `frappe_docker/pwd.yml` | Default passwords; port 8080 on every interface of the development Mac | Open | Development only |
| I15 | Script | `scripts/xstudio_staging.sh` | XStudio's seed admin password as a default | Open | Check it is not used in production |
| I16 | Local file | `.env` | Mode 644 | Open | Developer's machine |
| I17 | Browser tests | `tests/e2e/package.json` | `npm audit`: 1 high advisory in playwright (test tool only) | Open | |

## D. Detailed findings

Only the confirmed High and Medium code findings are detailed. The others are fully described by their row.

### D1, D2, D5, D7, D8: fields the server sets were taken from the request

- **Root cause.** A field marked read-only in a DocType is protected in the browser only. Frappe accepts it from
  a REST insert or save. The controllers trusted these fields when cancelling (reversing "their" entry) or when
  deciding whether to post.
- **Prerequisite.** A signed-in branch manager (D1, D2, D7), or the accountant (D5), sending one or two requests
  to `/api/resource`.
- **Severity.** High for D1 and D2: a low-privileged insider changes or hides ledger entries of any branch.
- **Fix.** `imederp/server_fields.py` `keep()`: on every save these fields are put back to what is stored, and
  are empty on a new document. The document's own actions write them with `db_set`. Cash Handover also reverses
  only the stored entry of a hand-over that was really received, and the person saving or submitting is the one
  handing over.
- **Changed files.** `server_fields.py` and the controllers of Cash Handover, App Payment, Treasury Close, Inter
  Business Transfer, Damaged Stock Sale, Stock Count, Studio Hour Package.
- **Tests.** `imederp/tests/test_security_server_fields.py`.
- **Behaviour change.** If someone other than the drafter submits a hand-over, they are recorded as the person
  handing over (before: the last person who saved the draft).
- **Residual risk.** Other read-only fields were not all reviewed one by one. Doctor Ledger Entry (D10) is open.
  Existing production documents were not checked for values planted before the fix.

### D3: a discrepancy's decision changed by a plain save

- **Root cause.** `validate` protected only the narrative fields once a case was settled.
- **Prerequisite.** The accountant (write permission on Cash Discrepancy), one PUT request.
- **Fix.** The sixteen decision fields are restored from the stored document unless one of the whitelisted
  actions set `flags.by_action`. Version history still records every change.
- **Residual risk.** K1 and K2 are separate and still open: they are actions, allowed by today's policy.

### D4: taking over another branch's draft

- **Root cause.** Frappe checks the right to write against the values being saved. User Permissions are on the
  branch field, so a document sent with the caller's own branch passes.
- **Fix.** A `validate` hook on every document (`check_write_on_stored`) also checks the right on the stored
  values. It is skipped for Administrator, for server code that sets `ignore_permissions`, and during install
  and migrate.
- **Residual risk.** The hook runs for every DocType, ERPNext's included. The full suite passes, but a workflow
  not covered by tests, in which a user legitimately saves a document she cannot write as stored, would now be
  refused with "You are not allowed to change …". Try the main workflows in the browser before release.

### X1: XStudio renamed existing customers

- **Fix.** The name follows XStudio only for customers of the sync's own customer group. Any other customer
  matched by phone is still linked, keeps its name, and the difference is listed on the import log for review.
  Names from XStudio are stored as plain text.
- **Behaviour change.** Visible on the Integration Status report as rows "to look at".

### X3: GET on state-changing endpoints

- **Fix.** `methods=["POST"]` on nine functions. The browser code and the connector already used POST.
- **Affects integrations.** Anything calling these with GET (none known) now gets 403.

## E. Authentication and session review

**Before (verified on the local site and in Frappe's source):**

- Passwords are verified and hashed by Frappe (passlib); the app adds nothing. No password is logged.
- Login throttling: 10 attempts, then 60 seconds. Password policy on, minimum score 2. No two-factor.
- A session ended only after 170 hours without a request. There was no limit on total age.
- Logout deletes the session row and its cache entry.
- Cookie `sid`: HttpOnly, SameSite=Lax, Secure when the request is https. The other cookies hold display values.
- CSRF: a token is required on POST once the desk has loaded. **Verified:** POST without it answers 400.
  A session that never loaded the desk has no token and is not checked; SameSite=Lax is what protects it.

**Now (`imederp/session_policy.py`, an `auth_hooks` hook, the framework's own extension point):**

| | Inactivity | Total age |
|---|---|---|
| Everyone | 30 minutes | 12 hours |
| System Manager, Super Admin, Accounts Manager, Administrator | 15 minutes | 8 hours |

- Configurable per site (`imed_session_*` keys in the site configuration).
- An expired session is deleted on the server the way logout does, and the request continues as Guest.
- Requests signed with an API key are not browser sessions and are untouched (the library connector).

**Verified over HTTP on the local site:**

| Check | Result |
|---|---|
| Anonymous call to four protected endpoints | 403 |
| Session idle 20 minutes (privileged) | 403, `session_expired`, session row and cache entry gone |
| Same cookie again | 403 |
| Session 9 hours old (privileged) | 403, row gone |
| Old cookie after logout | 403 |
| Active session, three calls | 200 each |
| Invalid API token | 401 |

**Effect on open sessions.** At deploy, a session older than its limit ends at its next request.

**Limitations.**

- Activity is any request, so a screen that refreshes itself keeps its session alive.
- The role decides the limit at each request; a role change applies at once but does not end the session.
- Frappe keeps sessions when a user's roles change. Disabling a user does end them.
- Concurrent sessions are allowed (`deny_multiple_sessions` is 0). Left as is: staff share counters and tablets.
- Two-factor authentication is off. Recommended for the owner and the accountant.
- System Settings still says 170 hours; the hook is stricter. Lower it in production (checklist, section 4).

## F. API security review

No function is open to guests (**verified** by test and by anonymous calls). Every function below needs a
signed-in user. "POST" means GET is refused.

| Endpoints | Authorization enforced | Status |
|---|---|---|
| Assistant: `get_status`, `list_chats`, `new_chat`, `get_chat`, `rename_chat`, `delete_chat`, `send_message` | Super Admin or System Manager; chats are their owner's; per-user and per-address limits; POST for writes | Reviewed, OK |
| Assistant tools (6) | Run as the user through `get_list`; company forced; read-only guard | Reviewed, OK |
| Owner dashboard cards (13), owner figures (6), `get_yesterday`, `get_overview`, 2 chart sources | Role check first; read-only | Reviewed, OK (A4) |
| `material_issue`: `request_approval`, `approve`, `reject` | Write permission; approver role, warehouse permission, row lock; POST | Reviewed, fixed (A3, X3) |
| `booking_accounts`: `record_payment`, `make_booking_invoice` | Write permission, own business, amount bounds, row lock; POST | Reviewed, fixed (A1, A2, X3) |
| `sales_cancellation.cancel_with_reason` | Sales Invoice only; cancel permission; POST | Reviewed, OK |
| `damaged_stock.default_damaged_store` | None | Reviewed, open (A6) |
| `integration_status.reimport_period` | System Manager or Accounts Manager; POST | Reviewed, OK |
| `library_sync.receive` | Library Connector, Accounts Manager or System Manager; POST; bounded | Reviewed, fixed (X3, X7); X2 open |
| `xstudio.sync`: `sync_now`, `test_connection`, `dry_run` | System Manager or Accounts Manager; POST | Reviewed, fixed (X3) |
| Cash Discrepancy: 8 actions and `unresolved_count` | Accounts roles or owner; four-eyes on approval; POST | Reviewed; D3 fixed; K1, K2 open |
| Cash Handover: `confirm_receipt`, `cancel_handover`, `receivers` | Receiver only; role rules; POST | Reviewed; D1, D5 fixed; D11 open |
| Treasury Close `reopen`; App Payment `cancel_payment`, `import_payment`; Studio Hour Package `make_invoice`, `cancel_package`; Doctor Ledger `reverse_adjustment`; Book Edition `carry_forward`, `cancel_for_curriculum_change`, `dispose_as_scrap` | Role or write permission; POST | Reviewed, OK |
| Document methods: Expense `request_approval`, `approve`, `reject`; Doctor Ledger Entry `approve`, `reject`; Inter Business Transfer `confirm_receipt` | Framework checks the document; role checks inside | Reviewed; D9 fixed. These six still accept GET (a GET's changes are rolled back by Frappe) |
| Read helpers: Booking `check_availability`, `get_events`; `get_stock`, `get_damaged_qty`, `get_recorded`, `get_store_items`, `get_machines`, `get_opening`, `get_doctor_summary` | Create or read permission plus warehouse, cost center or machine permission | Reviewed, OK |
| 22 script reports | Report roles; most read through `get_list`; role checks in the group-wide ones | Reviewed, OK (A8 fixed, A9 open) |
| Frappe and ERPNext standard API (`/api/resource`, `/api/method/frappe.*`, uploads) | Framework permissions | Not reviewed (unverified) |

SQL injection: every query in the app passes values as parameters. `bandit` flags 13 queries built with
f-strings, all at low confidence; each interpolates a constant or a fixed column name (**verified** by reading
all 13).

## G. Secrets review

No live key, private key, token or real connection string is in the tracked files or in the history of any
branch (manual pattern scan; a secret split over lines could be missed).

| Class | Item | Where | Note |
|---|---|---|---|
| Exposed | Initial user password | history: `d26d660`, `dd63d1e` | I1: force resets |
| Exposed, low value | Development database and Administrator password | `frappe_docker/pwd.yml` | Development stack only |
| Exposed, another system | XStudio seed admin default | `scripts/xstudio_staging.sh` | I15 |
| To verify | Supabase connection string and three model-provider keys | untracked local `.env` | Never committed; rotate if the machine was shared |
| Protected | Database root, restic and bucket credentials | Coolify environment only | Placeholders in the repository |
| Protected | Assistant model key | site configuration on the server | Never sent to the browser or logged |
| Protected | XStudio password and token | Password fields, encrypted | Read only to send |
| Unsafe pattern | Library connector key | plain `config.json` on each library PC | X10 |
| Unsafe pattern | Secrets on command lines; plain backup copies | `deploy/` scripts | I13, I8 |

Removing a secret from the code does not un-expose it. The rotation and incident steps are in
[PRODUCTION_SECURITY_CHECKLIST.md](PRODUCTION_SECURITY_CHECKLIST.md), sections 2 and 9.

## H. Architecture findings

- **Server-set state lived in ordinary fields with no single guard.** Each controller had to remember to protect
  its own. Now one helper (`server_fields.keep`) and one hook do it. New doctypes should list their server-set
  fields the same way.
- **Elevation to Administrator** (`system_user.as_administrator`) is used in six places, each after an explicit
  check (**code reading**). Inside it, role-based exemptions are always true (A5), and the acting user is lost
  unless written down (A1).
- **Role names decide company-wide reads** (A4). Safe with today's seven users; it would not survive adding a
  second company's accountant.
- **The connector's identity is its payload** (X2): the server should hold the map from API user to library.
- **No CI.** Tests, lint and secret scanning run only when someone runs them, while a push deploys.
- **Idempotency and locking** of money-posting functions are sound (row locks, unique keys, re-reads under
  lock), as the audit of 2 Nov 2026 found.

No large refactor was made.

## I. Test results

All on the local development site (`frontend`, MariaDB 11.8, Frappe 16.35.0, ERPNext 16.36.0), through the
guarded runner.

| Run | Command | Ran | Passed | Failed | Skipped |
|---|---|---|---|---|---|
| Baseline, before any change | `scripts/run_tests.sh --app imed_erp` | 834 | 831 | 2 | 1 |
| Exploit tests on the unfixed code | `bench --site frontend run-tests --module imed_erp.imederp.tests.test_security_server_fields` | 9 | 1 | 8 | 0 |
| Same, after the fixes | same | 9 | 9 | 0 | 0 |
| Audit regression tests | `… --module imed_erp.imederp.tests.test_security_audit` | 23 | 23 | 0 | 0 |
| XStudio sync | `… --module imed_erp.imederp.tests.test_xstudio_sync` | 42 | 42 | 0 | 0 |
| Final, all fixes | `scripts/run_tests.sh --app imed_erp` | 867 | 864 | 2 | 1 |

The two failures are the same before and after and are about the local site's state, not this work:
`test_the_sidebar_is_grouped_by_workflow_with_no_dead_link_and_no_duplicate` (the site's sidebar holds library
entries the test does not expect) and `test_a_paused_job_is_said_to_be_paused_not_a_scheduler_failure` (the
local scheduler is paused). They were not fixed or hidden.

**Other checks run:**

- Live HTTP checks of sessions, CSRF, anonymous access and methods on the local site (section E).
- `docker build -f deploy/Containerfile`: builds; the backup script is in the image; the image runs as `frappe`.
- `bandit` 1.9.4 on the app and the connector: 13 Medium at low confidence, 0 High (section F).
- `pip-audit` 2.10.1 on the bench's installed packages: 114 advisories in 13 packages: pillow 39, pypdf 29,
  pyjwt 15, gitpython 6, filelock 6, weasyprint 4, pyasn1 4, oauthlib 3, pdfkit 2, certifi 2, brotli 2,
  werkzeug 1, opentelemetry-api 1. All come with the Frappe/ERPNext base image. None is in the app's own two
  dependencies (anthropic, google-genai). Their exploitability in this deployment was not assessed.
- `npm audit` on `tests/e2e`: 1 high (playwright, a test tool).

**Not executed:**

- Browser suites (`tests/e2e`): they need the test users' passwords.
- The concurrency script of 2 Nov 2026 (`setup/concurrency_check_integrity.py`): locking code was not changed.
- gitleaks, trufflehog, semgrep, trivy: not installed.
- Anything against production.

**One unintended call.** While checking CSRF on the local site, one POST reached
`imed_erp.imederp.xstudio.sync.dry_run`. The local site's XStudio settings are enabled, so it performed one
read-only dry run against whatever XStudio address is configured there (it only sends GET requests and one
login, and keeps nothing). It was not repeated.

**Local side effects.** The local backend container was restarted once to load the new hooks. A test image was
built and removed. The local site has 10 `_Test` customers; whether they predate this audit was not established
(the leak guard passed before every run).

## J. Production deployment requirements

In [PRODUCTION_SECURITY_CHECKLIST.md](PRODUCTION_SECURITY_CHECKLIST.md). The ones that block a release:

1. Review and deploy this branch (the three High code fixes are not in production until then).
2. Force password resets for the accounts created in September (I1).
3. Close Coolify's ports or put them behind HTTPS (I2).
4. Confirm which backup job runs and that last night's succeeded.
5. Tell the staff about the session limits, or change them in the site configuration first.

## K. Residual risk and release decision

**CONDITIONALLY READY.**

- The code on this branch closes every High and Medium code vulnerability that was confirmed, with a test for
  each High one that failed before the fix, and the full suite shows no regression (864 of 867 pass; the same 2
  fail as before).
- It is conditional because the remaining High items are not in the code: a burned password in public history
  and a management port open to the internet. Both need the owner and the server.
- It is also conditional on a browser pass over the main workflows, because the new permission hook (D4) and the
  session limits (S1) touch every user and the browser suites were not run.
- Production as it runs today, without this branch, should be treated as not ready: an insider with a branch
  manager's login can cancel ledger entries.

What this audit cannot say: that no other vulnerability exists. Frappe and ERPNext were trusted as shipped, the
live server was not seen, and parts of the app were read less closely than others (section B).
