# XStudio sync — what it does, what it cannot, how to run it

> Branch `feature/xstudio-sync`, 24 Oct 2026. The analysis behind it: `docs/XSTUDIO_ERP_INTEGRATION_ANALYSIS.md`.
> XStudio's code was not changed. Everything here is on the ERP side and reads XStudio's **existing** API.

## 1. What is implemented (ERP side)

| Piece | Where | Notes |
|---|---|---|
| Settings screen | DocType `XStudio Settings` (single) + child `XStudio Hall Map` | URL, login, password (encrypted), days back/ahead, minutes between runs, customer group, resource for packages, hall → resource map. Buttons **Test Connection** and **Sync Now**. "Last Runs" section shows health. |
| API client | `imederp/xstudio/client.py` | GET only (plus the login POST). JWT from `POST /api/auth/login`, kept encrypted, renewed on 401. 20 s timeout. |
| Mappers | `imederp/xstudio/mappers.py` | Pure functions: Cairo times, statuses, amounts, service key, payload hash, package unit. |
| The run | `imederp/xstudio/sync.py` | `run()` / `run_scheduled()` / `sync_now()` / `test_connection()`. One Integration Import Log per run (`source_system = xstudio`). |
| Scheduler | `hooks.py` cron `*/10 * * * *` | Runs only when Settings → Enabled and Minutes Between Runs have passed. |
| Booking fields | `Booking` JSON | Section "XStudio": XStudio status, payment status, service, screen/cameras, full price, amount due/paid, price-pending, deposit, exact start/end (Cairo), hours, crosses-midnight flag, customer name/phone as sent, package id, photographer id, cancelled-by, source payload (JSON), payload hash, changed-in-source-at, last-read-at, not-returned flag. |
| Package fields | `Studio Hour Package` JSON | Source section (source, system, id, key, payload, hash, times) and XStudio section (name, **unit Hour/Reel**, category, expires on, XStudio hours remaining, ledger-explains-balance flag, payment status, paid total, payments summary). Usage child rows carry XStudio's row id. |
| Customer fields | custom fields (`imederp/xstudio/fields.py`) | `xstudio_customer_id` (unique), `xstudio_needs_review`, `xstudio_last_synced_at`. |
| Import Log | `Integration Import Log` | New source `xstudio`, counter **Updated**, row kinds **Needs Review** (actionable) and **Note** (information only, counted nowhere). Integration Status report shows the row. |
| Controllers | `booking.py`, `studio_hour_package.py` | An imported booking takes its package hours from the source and is never drawn/priced/posted here. An imported package cannot be saved, cancelled or drawn on by a booking entered here ("Change it there"). |
| Site setup | `setup/setup_xstudio.py` | Customer group `عملاء الاستوديو`, resources `X Studio — Hall {1,3,4,5,6,8}` and `X Studio — Prepaid Packages` (studio services, cost center `استوديو X`), the hall map. Run once: `bench --site frontend execute imed_erp.setup.setup_xstudio.run`. |
| Tests | `imederp/test_xstudio_sync.py` | 35 tests against an in-memory stand-in of XStudio's API (same endpoints, filters, 500 cap, roles). |

**Nothing financial is posted.** No Payment Entry, Sales Invoice, Journal Entry, GL Entry or cash-box movement is created from XStudio data; `booking_accounts.py` skips imported bookings and `record_payment` refuses them. Amounts are shown for monitoring.

## 2. Existing XStudio endpoints used

| Endpoint | Role needed | Used for | Limitation (xstudio-platform/backend/src/routes.js) |
|---|---|---|---|
| `POST /api/auth/login` | — | token (7 days) | password kept in ERP (encrypted); no API keys exist. **The client refuses every other non-GET call** (`client.py request()`), whatever the account may do in XStudio. |
| `GET /api/health` | — | Test Connection | |
| `GET /api/halls` | — | Test Connection (unmapped halls) | |
| `GET /api/bookings?from&to` | `bookings.read` | the bookings of the window | **max 500 rows, no paging** (`:582`); filter is on `starts_at` only; **no `updatedSince`** |
| `GET /api/bookings?customerId` | `bookings.read` | finding a booking moved out of the window | same 500 cap per customer |
| `GET /api/customers/:id/packages` | `packages.read` | packages, usage ledger, payments | one call per customer; **payments carry no id** (`:912-914`); no `updated_at` on packages (`schema.sql`) |

The sync account must hold `bookings.read` **and** `packages.read`. Of XStudio's existing roles that is `manager` or `accountant` (`middleware/auth.js:7-27`); `viewer` lacks `packages.read`. Use a dedicated **accountant** login with its own password. It also holds `payments.write` in XStudio, which the ERP never uses; a read-only role would need an XStudio change (not in this sprint).

## 3. How a run works

1. Window = [today − Days Back, today + Days Ahead] in Cairo (defaults 30 / 60).
2. `GET /api/bookings?from&to`. If 500 rows come back, the span is halved and read again, down to one hour. A one-hour span that still returns 500 is listed in the log as **Failed: "XStudio returned its maximum..."**, and the run is **not** claimed complete for that span.
3. Customers (from the bookings' `customer_id/name/phone`): found by `xstudio_customer_id`; else by phone (`normalize_phone`) and linked; else created in `عملاء الاستوديو`. A phone that is a placeholder (`no-phone-…`) or invalid → customer **without** a number, `xstudio_needs_review = 1`. Never a made-up number.
4. Packages of those customers (`GET /api/customers/:id/packages`): inserted and submitted, or their mirror fields updated.
5. Bookings: inserted, updated (payload hash changed) or skipped (unchanged). Overlap with a booking entered here → that row fails with "already booked".
6. Usage ledger rows appended once each by XStudio's row id; `Hours Used` = ledger sum; `Hours Remaining` = **XStudio's figure**, never recalculated; a ledger that does not add up to it → flag off + an informational **Note** on the log (incomplete historical usage; not an error).
7. Bookings imported earlier whose start is in the window but which XStudio did not return: looked up by `customerId`; found → updated (moved); not found → `xstudio_not_in_last_fetch = 1` + **Needs Review**. **Nothing is deleted or cancelled because XStudio did not return it.** A failed API call aborts the run (Failed log) and changes nothing.

Each record is its own savepoint; a failing record is listed with its reason and the rest continue. Two runs cannot overlap (MariaDB named lock). Health: Healthy / Degraded (errors or 1–2 failures) / Down (3 failures in a row).

## 4. Synchronization coverage

| Entity / event | Status | Notes |
|---|---|---|
| Customers from bookings (id, name, phone) | Working, mock-tested, live on staging | A customer is matched by XStudio id, then by phone, then made; a **name or phone changed later in XStudio is not written over the ERP customer** (seen 25 Oct 2026; a row to add when wanted). | Email/address/notes are not read (no customer list endpoint without the 200-row cap). A customer with no booking in the window is not imported. |
| Customer without usable phone | Working, mock-tested | Created without number, flagged for review. |
| Historical bookings, last 30 days (+60 ahead) | Working with limitations, mock-tested | Complete unless a one-hour span holds ≥ 500 bookings (then listed, not claimed). |
| Booking statuses | Working, mock-tested | `pending`→Tentative; `confirmed`→Tentative, or Confirmed with Deposit when `amount_paid > 0`; `completed`→Completed; `cancelled`→Cancelled with reason "Cancelled in XStudio by …". XStudio's own status kept. |
| Exact times incl. midnight | Working, mock-tested | Exact start/end kept in Cairo Datetime fields; a booking ending at 00:00 is shown to 23:59:59 on its day **and flagged**, never silently. |
| Duplicate prevention | Working, mock-tested | `import_key` unique on Booking and Studio Hour Package; usage rows by XStudio id; payload hash skips unchanged rows. |
| Import Log + Integration Status | Working, mock-tested | |
| Change detection (any field) | Working with limitations | Only when the booking is read again: its start must be inside the window, or the booking must be found in its customer's list (≤ 500). A change on a booking older than Days Back whose customer has > 500 bookings is **not** detected. |
| Rescheduling | Working, mock-tested | Inside the window; outside, via the customer list. |
| Cancellation + package hours back | Working, mock-tested | Ledger row `cancel_refund` brings the hours back. |
| Completed + amount paid | Working, mock-tested | Aggregate `amount_paid` only. |
| Packages (incl. bought before the window) | Working, mock-tested | Whole ledger comes with the package. Balance = XStudio's figure. |
| Package usage ledger | Working, mock-tested | Rows whose booking is outside the window are kept with "(booking … not imported)". |
| Package whose usage rows do not add up to its balance (migrated from the sheet by XStudio's import, which writes no usage row for the hours already used; or `PATCH /customer-packages/:id`) | Kept, marked, noted | **XStudio's balance is the balance** (owner's rule, 25 Oct 2026). Hours Remaining = XStudio's figure, never recalculated; Hours Used = the usage rows that exist; the package's "Ledger Explains the Balance" is off and the log carries an informational **Note** (kind `Note`, counted nowhere: the run stays Completed and Healthy). Not an error, nothing to do. |
| Deleted package (`DELETE /customer-packages/:id`) | **Not possible to detect reliably** | It simply stops being returned; the ERP copy stays as last read. |
| Payments | Aggregate only | Booking: `amount_paid`/`payment_status`; package: `paid_total` + text summary. **No individual payment records, no stable payment ids exist in the API.** |
| Reels bundles | Working, mock-tested | `unit = Reel`. |
| Manual Sync Now / Test Connection | Working, mock-tested (permissions) | System Manager / Accounts Manager. |
| Periodic polling | Implemented; `run_scheduled` gating tested; a live scheduled tick not yet observed | Cron every 10 min; gated by Settings → Enabled and Minutes Between Runs. |
| Lecture halls (HAL) | Untouched | XStudio halls map only to studio services; a Hall resource is refused in the map. |
| Photographers, week closings, blocks, notifications | Not implemented | Out of this sprint. |
| Live XStudio API | **Verified on staging** (24 Oct 2026) | XStudio's real backend run locally against a separate Supabase Cloud database (empty, then initialised from `schema.sql`/`seed.sql`), ERP at `http://host.docker.internal:4000`. Run 1: 13 read, 8 inserted (6 bookings, 2 packages, 3 customers). Then in XStudio: reschedule, extra payment, cancellation of the midnight booking, hand-edited package balance, new podcast booking. Run 2: 14 read, 1 inserted, 4 updated, 4 unchanged, 1 Needs Review (the hand edit), 0 failed, all figures matching. No Payment Entry, Sales Invoice or Journal Entry created. **The production XStudio was not touched.** |

## 5. Tests

`bench --site frontend run-tests --module imed_erp.imederp.test_xstudio_sync` → **35 tests, OK** (24 Oct 2026). Also green after the change: `test_booking` (23), `test_booking_pricing` (26), `test_app_import` (19, one expectation updated for the new status row), `test_customers` (14), `Studio Hour Package` (10), `test_test_records` (guard). Full `--app imed_erp` run after the change: **697 tests, 696 passed**; the one error (`test_doctor_accrual.test_qa33…`) was a `tabError Log` table left marked as crashed by the disk-full incident, repaired with `REPAIR TABLE`, after which the module passes (14/14).

## 6. Staging XStudio on Supabase Cloud (no Docker Postgres)

XStudio reads one variable, `DATABASE_URL` (`backend/src/db.js:25`). SSL is switched on automatically when the host matches `supabase.co` / `supabase.com` (`db.js:28-33`, `rejectUnauthorized: false`), so nothing else is needed for Supabase.

1. Create a **new** Supabase project for staging. Never use the production project's URL. Take the **direct / session** connection string (port 5432), not the transaction pooler (6543): the booking service uses `SELECT … FOR UPDATE` inside transactions.
2. Initialise the schema once (idempotent): `psql "$DATABASE_URL" -f backend/sql/schema.sql` then `psql "$DATABASE_URL" -f backend/sql/seed.sql`. Supabase has `btree_gist` and `pgcrypto`. `ensureSchema()` in `src/index.js` adds the late columns on every boot.
3. Start the backend from `xstudio-platform/backend` with the variables in a git-ignored `.env` or the shell: `DATABASE_URL`, `TZ=Africa/Cairo`, `PORT=4000`, `JWT_SECRET=<random>`, `WHATSAPP_DRIVER=dev`; leave `TELEGRAM_*` unset. `npm ci && node src/index.js`.
4. `scripts/xstudio_staging.sh` (this repo) logs in as the seed admin, **changes its password**, creates the `accountant` login for the sync and prints nothing secret.
5. On the ERP: `XStudio Settings` → URL `http://host.docker.internal:4000` (the ERP runs in Docker; http is accepted for this host only), login = the accountant's phone, password; run `setup_xstudio.run` once; **Test Connection**; enable; **Sync Now**.

## 6a. Automatic sync: scheduler, locking, retries (verified 25 Oct 2026 on the local `frontend` site)

- The job: `hooks.py` cron `*/10 * * * *` → `run_scheduled`, registered as a Scheduled Job Type on migrate. It runs only
  when XStudio Settings → Enabled, and only when Minutes Between Runs (default 10) have passed since the last attempt.
- Needs the Frappe scheduler **enabled for the site** (`bench --site <site> scheduler status` / `enable-scheduler`) and
  the `scheduler` and `queue-*` containers up (`bench doctor` → workers online). Enabling the scheduler starts every
  other enabled Scheduled Job Type too; on `frontend` the ones that would create records or touch mail were paused
  (`stopped = 1`): `recurring_expense.run_daily`, `doctor_accrual.run_daily`, `email_account.pull`,
  `email_account.notify_unreplied`. Un-pause them from the Scheduled Job Type list when wanted.
- Two runs never overlap: a MariaDB named lock (`get_lock`) is taken by the scheduler's run and by Sync Now alike; the
  second is refused with "Already Running".
- A failed run (XStudio unreachable, a timeout, a refused login) is written as a Failed log, rolled back to the run's
  savepoint, counted in Failures in a Row, and **retried on the next tick**; three in a row → health Down. There is no
  in-run retry of a single call (the client timeout is 20 s).
- **Dry run** (nothing kept, not even the log; the settings are left as they were):
  `bench --site <site> execute imed_erp.imederp.xstudio.sync.dry_run`. Works with the sync disabled, so it is the
  first look at a real XStudio before any import: the window, the counts, the customers / packages / bookings it
  would add, and the rows it would list for review.

## 6b. Time zone

The site's System Settings time zone must be `Africa/Cairo` (`setup_regional.py` sets it; the dev site had been
left on Frappe's default `Asia/Kolkata` and was corrected on 25 Oct 2026). The sync itself converts XStudio's UTC
instants with an explicit Cairo zone, so Date/Time fields are right whatever the site zone; Datetime fields
(exact start / end, last read) are stored naive in Cairo and are only *displayed* right when the site zone is Cairo.
Containers and MariaDB stay on UTC (nothing to change there). Changing the setting rewrites no row.

## 6c. Connecting the real XStudio (xstudioeg.com): the procedure, in order

Nothing below writes to XStudio, and nothing is imported until step 6. No credential goes through chat, a ticket
or a commit: the password is typed once into XStudio Settings (stored encrypted) or passed through an environment
variable to `setup_xstudio.configure`.

1. **The account.** Owner's decision of 25 Oct 2026: the accountant's existing XStudio login is used (it opens the admin panel; the ERP client is hard-wired read-only, so that access is never exercised). No new account or role is made. *(The original plan, kept for reference:)*  XStudio's super admin (Admin → Users, or `POST /api/admin/users`)
   creates a staff login with role **accountant** (`bookings.read` + `packages.read`; `manager` also works but
   holds `bookings.write`), its own phone and a long random password, named "ERP Sync". Never the owner's own
   login. XStudio has no read-only role and no API keys (§7): the accountant role is the least that can read
   packages.
2. **The hostname.** Production is `https://www.xstudioeg.com` (API under `/api`, `backend/src/index.js`); check it
   answers `GET /api/health` with `{"ok":true}` over https. The settings refuse `http://` for any host but a local
   test server.
3. **Enter the connection**, with the sync still **off**: on XStudio Settings, URL, the sync login's phone,
   its password → Save → **Test Connection**. It must say the login worked and list no unmapped hall (the six halls
   1, 3, 4, 5, 6, 8 are mapped by `setup_xstudio.run`). Or from a shell, password through the environment only:
   `XSTUDIO_SYNC_PASSWORD=... bench --site <site> execute imed_erp.setup.setup_xstudio.configure --kwargs
   '{"base_url": "https://www.xstudioeg.com", "login": "<phone>", "enabled": 0}'`.
4. **Permissions check.** Test Connection calls `/api/halls` (public) and the login; the dry run below is the
   check of `bookings.read` and `packages.read` (a missing permission fails the run with XStudio's 403 reason).
5. **Dry run:** `bench --site <site> execute imed_erp.imederp.xstudio.sync.dry_run`. It reads the window
   (30 days back, 60 ahead), reports the counts, the customers / packages / bookings it would add and the rows it
   would list for review, and keeps nothing. Read it for: a span listed as incomplete (a one-hour span with ≥ 500
   bookings, §7), customers without a usable phone, and bookings that would fail on a manual booking in the way.
6. **The owner approves** the dry run's report. Only then: Enabled → Save → **Sync Now** (the first real run,
   with the owner watching the Integration Import Log), then the scheduler keeps it up every 10 minutes.

## 6d. Keeping it running when the Mac is off

The ERP today runs in Docker Desktop on the development Mac (`frappe_docker/pwd.yml`, site `frontend`,
`http://localhost:8080`); its scheduler and workers stop with the Mac, and so does the sync. For the sync to run
on its own, the ERP must be on an always-on server, which is the production deployment of
`docs/production-deployment-plan.md` (A: a Linux server with Docker; D: scheduler and workers enabled and
checked with `bench doctor`), with the XStudio connection entered there (§6c) and port 443 open outbound to
xstudioeg.com. Nothing else is needed on XStudio's side: XStudio is the server, the ERP only calls it.
Until then, the sync runs whenever the Mac is on and Docker Desktop is running, and catches up on its first tick
(the window is re-read in full on every run; nothing is missed by a pause shorter than 30 days).

## 7. Known limitations that need an XStudio change (not done in this sprint)

| Gap | Why | File | Smallest future change |
|---|---|---|---|
| 500-row cap, no paging | `LIMIT 500` | `routes.js:582` | `limit`/`cursor` params |
| No `updatedSince` | filter on `starts_at` only | `routes.js:569-584` | `updatedSince` on `updated_at` + index |
| No payment ids | `payments[]` built without `id` | `routes.js:912-914` | add `p.id` to the `json_build_object` |
| No `updated_at` on packages/users | schema | `schema.sql:24-35, 64-75` | column + existing trigger `set_updated_at` |
| Hard delete of packages | `DELETE` erases ledger | `routes.js:865-878` | soft delete (`deleted_at`) |
| No read-only role with `packages.read` | roles | `middleware/auth.js:7-27` | role `integration` |
| 7-day token, no API key | `jwtExpiry` | `db.js:7` | `X-Api-Key` |

## 8. Production readiness

- **Code implemented locally:** everything in §1, on branch `feature/xstudio-sync`, not committed, not pushed, not deployed.
- **Tested with mocks:** §4 rows marked mock-tested.
- **Tested against a running XStudio instance:** yes, XStudio's own backend on a Supabase **staging** database (see §4, last row). Not against xstudioeg.com.
- **Connected to the real XStudio (25 Oct 2026, 15:09 Cairo), on the development Mac:** the accountant's existing
  XStudio login (role `manager`; the ERP client refuses every write), URL `https://www.xstudioeg.com`. Staging records
  removed first (8 bookings, 2 packages, 4 customers; the 7 staging logs kept). Dry run, then the first import
  IMP-2026-00008: 155 rows read, 97 bookings (77 Tentative, 20 Cancelled, halls 1/3/4/5/6), 30 customers in
  عملاء الاستوديو (4 without a usable phone, flagged), 14 packages (13 Hour, 1 Reel; 8 with a hand-edited balance,
  flagged), 92 usage rows, 0 failed. Second run IMP-2026-00009: 0 inserted, 111 unchanged, no duplicate on any key.
  No Payment Entry, Sales Invoice, Journal Entry or GL Entry. Automatic sync enabled afterwards (see the final report
  of that day). Backup of 14:43 kept in the site and in `~/Documents/imed-erp-backups`.
- **Deployed on an always-on server:** none. The sync runs only while the Mac, Docker Desktop, the scheduler, the
  workers and the internet are up (§6d). The scheduler job is present in `hooks.py` but inert until Settings → Enabled, which should be done only after the staging run and the full regression suite pass.

## 9. Source of truth (owner's rule, 25 Oct 2026)

XStudio's production database, through its API, is the single source of truth for customers, bookings and their
statuses, halls, packages, their totals, the usage rows that exist, the remaining balances and the payment
summaries. Audit of the ERP side on that day: nothing in `imederp/xstudio/` reads a spreadsheet or a file; the only
balance ever written is XStudio's `hours_remaining`; the ERP's own package arithmetic (`studio_hour_package.py`)
refuses imported packages; every call is a GET (the client refuses the rest); a second run changes nothing
(idempotent). The separate file import of studio bookings (`booking_import.py`, "Studio (bookings, file)") is an
older, unrelated path that the XStudio sync neither uses nor falls back to.
