# Production deployment plan (limited launch)

For whoever sets up the production server, with the owner and the accountant for the steps that need them. Each
step says what to do, how to check it, and what to do if the check fails. Nothing here is done yet; nothing is
deployed without the owner's approval (docs/production-hardening.md, section 6).

Order: **A** server, **B** backups, **C** site and data, **D** scheduler and workers, **E** opening cash, **F**
smoke tests, **G** go/no-go. Do not skip ahead: each step relies on the one before.

---

## A. Production server configuration

1. A Linux server (4 GB RAM, 2 CPUs, 40 GB disk at least; the development Mac ran out of disk on 21 Oct, so keep
   20 GB free), Docker and Docker Compose, the firewall open on 80 and 443 only.
2. The code: the branch the owner approves (today `fix/audit-2026-10-20`, not merged), checked out by tag.
3. Passwords and ports: docs/production-hardening.md, section 1 (`.env.production` with long random passwords,
   kept out of git and in the owner's password manager; the production override serves 127.0.0.1 only).
4. TLS and headers: section 2 (Caddy in front; port 8080 closed).
5. Login rules: section 3 (5 attempts, 15 minutes lockout, two-factor for the owner and the accountant, 12-hour
   sessions, no email-link login, password policy).

**Check:** from another machine, `https://<domain>` shows the login page with a valid certificate;
`http://<server-ip>:8080` does not answer. `docker compose ps` shows every container up.

## B. Off-server backups and a restore check

1. The owner chooses where copies go (a private cloud drive or a disk at the office). Until then this step blocks
   the launch: a backup kept only on the server is lost with the server.
2. `rclone config` on the server for that destination; the nightly job of section 4 (02:30).
3. **Run it once by hand** and check: the log ends without a warning; the remote holds four files (database,
   public files, private files, site configuration); `gunzip -t` passes on the database file.
4. **Restore check, before go-live and then once a month:** restore the latest set into a separate site, never over
   the live one:

   ```bash
   docker exec frappe_docker-backend-1 bench new-site restore-check --admin-password <random> --db-root-password <root>
   docker exec frappe_docker-backend-1 bench --site restore-check restore <set>-database.sql.gz \
       --with-public-files <set>-files.tar --with-private-files <set>-private-files.tar --db-root-password <root>
   docker exec frappe_docker-backend-1 bench --site restore-check migrate
   ```

   Compare with the live site, on the same day: the count of GL Entry, Sales Invoice, Journal Entry, Stock Ledger
   Entry, Treasury Close and Doctor Ledger Entry (`bench --site <site> execute frappe.db.count --args "['GL Entry']"`),
   each cash box's balance (`opening_cash.check()`), and one attached receipt opens. All equal: the backup works.
   Then drop the check site (`bench drop-site restore-check`).

   Done on the development machine on 21 Oct: the backup of 16:58 restored into a separate site matched every count
   taken before the demo data was erased (90 ledger rows, 34 vouchers, the app's 50 records, Mawasah -936.50).

## C. The site, migrations and cache

1. A **clean** site, never a copy of the development or demo site (they hold `_Test` companies and demo records):
   `bench new-site`, then install erpnext and imed_erp, then the setup scripts in the README's order
   (`setup_core.py` ... `setup_dashboard.py`).
2. `bench --site <site> migrate`; it must end with "Executing after_migrate hooks" and no traceback.
3. Restart the web and background workers (a new doctype's code loads only on start), then clear the cache (the
   hooks are cached; on 21 Oct the copy site kept serving old hooks until its cache was cleared):

   ```bash
   docker restart frappe_docker-backend-1 frappe_docker-queue-short-1 frappe_docker-queue-long-1 frappe_docker-scheduler-1
   docker exec frappe_docker-backend-1 bench --site <site> clear-cache
   ```

4. `developer_mode 0` and `allow_tests 0` (section 1).
5. **Check:** `setup/verify_setup.py` and `setup/verify_users.py` pass; the owner's page shows its cards without
   "NaN"; Cash Close Settings shows *Reporting Week* Saturday to Thursday and *Recovery Policy Approved* **off**.

Every later version: section 6 of the hardening guide (backup copied off first; migrate; restart; clear cache; the
checks above; restore the backup if anything is wrong).

## D. Scheduler and background jobs

1. `bench --site <site> enable-scheduler`; `bench --site <site> scheduler status` says **enabled**.
2. `bench doctor` lists the workers (short, long, default queues) as online and no stuck jobs.
3. The app's two daily jobs (hooks.py, `scheduler_events`): `recurring_expense.run_daily` (the monthly bills'
   drafts and their reminders) and `doctor_accrual.run_daily` (the doctor's amount on any sale the hooks missed),
   besides ERPNext's own. Check after the first night:
   - **Scheduled Job Log** (desk): each job ran with status Complete, none Failed;
   - **Error Log**: nothing new;
   - a monthly bill due that day has one draft expense, and a second run makes none (tested on the copy site, 21
     Oct: idempotent).
4. E-mail: an outgoing Email Account set and tested (a doctor's statement on settlement, the reminders); without it
   the payout still goes through and the accountant is told (tested).

**If a job fails:** the Error Log names it; nothing is posted twice on a re-run. Fix, then run it once from the
Scheduled Job Type list (Execute).

## E. Opening cash for each branch

docs/production-hardening.md, section 7. In short: the evening before, `opening_cash.check()` shows every box mapped
and empty; on the go-live morning each branch counts its cash with a second person and both sign; the accountant
prepares the draft opening entry with `opening_cash.prepare(...)`, checks it against the signed sheets, attaches
them and submits; that evening each branch manager makes the first close, whose expected closing should match the
count. Wallets: from their statements, by the accountant.

**Blocks the launch until done:** without it the first payment out of any box is refused.

## F. Smoke tests by role (on the production site, before staff use it)

One login each, on a phone and a desktop. Record and keep the results (who, when, pass or fail). Every test record
is cancelled afterwards with the reason "smoke test" (cancelled, not deleted: it stays on record).

| Role | Must work | Must be refused |
|---|---|---|
| Owner | Owner's page cards and shortcuts; every report; approve an expense; read every branch's closes and discrepancies | Approving a recovery (the policy is off): the message says it is blocked |
| Accountant | A journal entry; confirm a transfer; a weekly cash review; investigate a discrepancy, write one off; reopen a close with a reason | Approving a recovery; changing Cash Close Settings |
| Library manager (Sara, Raghad) | A sale at the point of sale and its receipt in Arabic; an expense with a receipt photo; a transfer; the evening's cash close of her own box | Another branch's records, boxes and reports; reopening or cancelling a close; a payment larger than the box holds; a date after today |
| Studio and halls managers | A booking (no double booking of one hour); its invoice; their cash close | Another business's records |
| App manager | A subscription and its platform fee | Cash closes of the libraries |

Also: two people confirm one transfer at the same moment (one succeeds); the browser console shows no blocked
requests under the security headers (section 2).

## G. Go / no-go

Go only when all of these hold; any "no" is a no-go:

- [ ] A to F done and checked, with the results kept.
- [ ] A backup copied off the server and restored once (B).
- [ ] Opening cash entered for every box (E).
- [ ] The owner has decided whether خزينة تطبيق BA Plus takes cash.
- [ ] The owner signs off launching without HR and payroll, tasks, the integrations and ACC-09.
- [ ] Recovery Policy Approved is off (until a written policy is approved).

Passing automated tests is necessary, not sufficient: they prove the code, not this server, its backups, its data or
its users' access.
