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
