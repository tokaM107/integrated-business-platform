# Production hardening

What the production server needs before go-live, from the QA and security audit of 20 Oct 2026 (SEC-04, SEC-05,
SEC-06). The local setup (`frappe_docker/pwd.yml`, the README's setup steps) is for development: its passwords are
`admin`, it serves the site on every interface, and the README turns on `developer_mode` and `allow_tests`. None of
that may reach the production server.

Build production from a clean site with the setup scripts, never from a copy of the development site: the
development site still holds `_Test` companies, items and warehouses left by test runs.

## 1. Passwords and the open port (SEC-04)

Start the containers with the production override, which takes the passwords from the environment and serves the
site on 127.0.0.1 only:

```bash
cd frappe_docker
cat > .env.production <<'ENV'
DB_ROOT_PASSWORD=<a long random password>
ADMIN_PASSWORD=<another long random password>
ENV
chmod 600 .env.production
docker compose --env-file .env.production -f pwd.yml -f overrides/compose.imed-production.yaml up -d
```

Compose refuses to start when either password is missing. Keep `.env.production` off the repository (the
repository is public) and in the owner's password manager.

Then, once the site exists and the setup scripts have run:

```bash
docker exec frappe_docker-backend-1 bench --site frontend set-config developer_mode 0
docker exec frappe_docker-backend-1 bench --site frontend set-config allow_tests 0
docker exec frappe_docker-backend-1 bench --site frontend enable-scheduler
docker exec frappe_docker-backend-1 bench --site frontend scheduler status   # must say enabled
```

The scheduler makes the monthly bill drafts, the expense reminders and the daily doctor accrual; nothing of that
runs while it is off.

## 2. TLS and security headers (SEC-06)

A proxy on the host faces the internet, with TLS, and sends the requests on to 127.0.0.1:8080. With Caddy, which
gets and renews the certificate itself:

```
erp.example.com {
	reverse_proxy 127.0.0.1:8080
	header {
		Strict-Transport-Security "max-age=31536000"
		Content-Security-Policy "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; script-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self' wss:; frame-ancestors 'self'"
	}
}
```

Frappe's desk needs `unsafe-inline` and `unsafe-eval` for scripts; the policy still stops scripts, frames and
connections from other sites. Open every main screen once after turning it on (home, a sale at the point of sale,
an expense with its receipt, a report, the assistant's microphone) and look for blocked requests in the browser
console before go-live.

Close port 8080 in the server's firewall; only 80 and 443 are open.

## 3. Logins (SEC-05, brute force)

Frappe locks an account after 10 failed logins for 60 seconds. In **System Settings**:

- Allow Consecutive Login Attempts: 5
- Allow Login After Fail (seconds): 900
- Enable Two Factor Auth, and turn it on for the owner's and the accountant's roles (Role: Two Factor Authentication).

These are per account. A limit per address is set in the proxy, e.g. Caddy's `rate_limit` module or nginx's
`limit_req` on `/api/method/login`.

Also in **System Settings** (the development site has these, found 21 Oct 2026; production must not):

- Session Expiry: `12:00` (the development site keeps a session alive 170 hours).
- Login with email link: off (passwordless login by email is on in development).
- Enable Password Policy: on, Minimum Password Score: 3.
- Deny Multiple Sessions: on for the accountant's and the owner's accounts if they never use two devices.

## 4. Backups off the server (SEC-05)

`scripts/backup_offsite.sh` takes `bench backup --with-files`, copies the set out of the container, checks that each
archive can be read, keeps 30 days, and with `REMOTE` set copies it off the server with rclone. Where the copy goes
(a cloud drive or a disk at the office) is the owner's decision; until then the backups stay on the server only,
and the script warns so every night.

```bash
# once: rclone config   (a remote named e.g. gdrive)
# cron on the host, every night at 02:30:
30 2 * * * BACKUP_DIR=/srv/imed-backups REMOTE=gdrive:imed-backups /path/to/scripts/backup_offsite.sh >> /var/log/imed-backup.log 2>&1
```

Each set includes `site_config_backup.json`, which holds the database password: the script makes the folder
readable by its owner only, and the remote must be private.

Before go-live, restore one backup onto a test site and open a few records: a backup never restored is not known
to work.

```bash
docker exec frappe_docker-backend-1 bench new-site restore-test --admin-password <...> --db-root-password <...>
docker exec frappe_docker-backend-1 bench --site restore-test restore <set>-database.sql.gz \
	--with-public-files <set>-files.tar --with-private-files <set>-private-files.tar
```

## 5. Before opening it to the staff

- One login each for the owner, the accountant, a library manager and the studio manager: each records a sale, an
  expense and a transfer, and sees no other branch's records.
- `setup/verify_users.py` passes for every user, and every branch manager has their branch: an account with the
  Branch Manager role and no branch is refused everywhere (SEC-07).
- Two people click Confirm Receipt on the same transfer at once, and two payouts of one doctor are submitted at
  once: one goes through, the other is refused.

## 6. Deploying a new version (this branch included)

Never without the owner's approval, and only after a backup copied off the server (section 4).

```bash
# 1. Backup, checked and copied out.
scripts/backup_offsite.sh

# 2. The code.
git fetch && git checkout <the approved branch or tag>

# 3. The database: new doctypes and fields. Since 20 Oct 2026: Treasury Close (and its new fields), Cash
#    Discrepancy, Weekly Cash Reconciliation, Cash Close Settings, the report Cash Discrepancies; Book Edition > Disposed Qty;
#    Damaged Stock Entry > Obsolete Edition; Printer Reading > Counter Reset and Reset Note; App Course > Tier;
#    Sales Invoice and POS Invoice > Return Reason (custom fields).
docker exec frappe_docker-backend-1 bench --site <site> migrate

# 4. The setup scripts that changed (all idempotent), from bench console, in this order:
#    setup_core.py       the student customer group (CRM-01)
#    setup_users.py      Stock Settings readable by the library managers
#    setup_dashboard.py  the owner's cards and reports
docker exec -it frappe_docker-backend-1 bench --site <site> console

# 5. The web and background workers load new modules (a new doctype's folder) only when they start.
docker restart frappe_docker-backend-1 frappe_docker-queue-short-1 frappe_docker-queue-long-1 frappe_docker-scheduler-1
docker exec frappe_docker-backend-1 bench --site <site> clear-cache
```

After it, before staff use it:

- `setup/verify_users.py` passes; `setup/check_doctor_accounts.py` lists nothing new.
- `bench --site <site> scheduler status` says enabled; `bench doctor` shows the workers online.
- One login each for the owner, the accountant, a library manager and the studio manager (section 5); the owner's
  page shows its cards without "NaN".
- If anything is wrong: restore the backup of step 1 onto the site (`bench --site <site> restore ...`) and
  check out the previous version.

The browser tests (`tests/e2e/`) and the two-sessions check (`setup/concurrency_check.py`) run on a throwaway copy
restored from the same backup, never on the production site.

## 7. Opening cash on the first day (ACC-03)

A cash box never goes below zero, so each box must hold, in the books, the cash really in it before the first sale,
expense or payout; otherwise the first payment out of it is refused. Production starts from a clean site, with no
demo transactions.

1. **The evening before:** check every treasury (read-only):

   ```python
   # bench --site <site> console
   from imed_erp.imederp import opening_cash
   opening_cash.check()
   ```

   Each cash box should show its business, no entries and a zero balance. Anything marked `!!` is fixed first
   (a box without a business is closed by nobody). The app's treasury, خزينة تطبيق BA Plus, is a bank account:
   the close and the check below zero do not reach it (a decision is open; see the production readiness report).
2. **The go-live morning, before the first sale:** in each branch the manager and a second person count the cash
   in the box and both sign a count sheet. The count sheets go to the accountant.
3. **The accountant** prepares one draft opening entry from the signed counts, checks it line by line against
   the sheets, attaches them, and submits it:

   ```python
   opening_cash.prepare({
       "الخزينة الرئيسية - MMG": 0,
       "خزينة مكتبة الأزاريطة - MMG": 0,
       "خزينة مكتبة المواساة - MMG": 0,
       "خزينة سنتر Imed - MMG": 0,
       "خزينة X Studio - MMG": 0,
   }, "<go-live date>")
   ```

   It is an Opening Entry against حقوق ملكية الأرصدة الافتتاحية, dated the go-live day. It refuses a wallet, an
   amount below zero, and a box that already has entries (its opening would count twice). The wallets' opening
   balances come from their statements, entered separately by the accountant.
4. **That evening:** each branch manager makes their box's first close; its opening is the balance entered in step
   3, and its expected closing should match the count.
5. **Cash Close Settings:** leave *Reporting Week Starts On* empty until the reporting week is confirmed, and
   *Recovery Policy Approved* off until the owner approves a written policy checked by a lawyer or HR.

