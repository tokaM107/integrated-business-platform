# IMED ERP on the Hostinger VPS with Coolify: the deployment, prepared and rehearsed (27 Oct 2026)

Nothing in this document has been done on the server. Everything was prepared from the repository and rehearsed
on the development Mac in a second, production-shaped stack built from the same files. Each section ends with the
**approval checkpoint** before which nothing moves. Deliverables 1 to 12 of the brief are the sections below;
section 10 holds the actual test results and section 11 the blockers.

## 0. Preflight: what is there today

**Repository** `tokaM107/integrated-business-platform` (GitHub, origin). Branch `feature/imed-hall-bookings`
at `ff1e6a6`, 12 commits ahead of `main` (`6ebac7d`), nothing behind: it contains, in order, the XStudio sync
(`feature/xstudio-sync`, 97e8c9b), the library analysis and collector (`feature/library-sync`, 8de0892), the hall
bookings (3096480) and their finalisation with the sidebar (ff1e6a6). This is the branch to deploy; no other branch
holds approved work that is not in it (`git log main..feature/imed-hall-bookings`). Untracked and never to commit:
the library's `.exe`, `.rar` and Generate-Scripts `.html` files and `tests/e2e/package-lock.json`.

**Versions, read from the running containers** (not from documentation):

| Component | Version | Where |
|---|---|---|
| Frappe | 16.35.0 | image `frappe/erpnext:v16.36.0` |
| ERPNext | 16.36.0 | same image |
| imed_erp | 0.0.1 (the repository) | mounted from `apps/imed_erp` in development; inside the image in production |
| Python | 3.14.7 | image |
| Node | 24.21.0 | image |
| MariaDB | 11.8.9 | `mariadb:11.8` |
| Redis | 6.2.24 | `redis:6.2-alpine` (cache and queue) |
| Docker (Mac) | Desktop; (VPS) Engine 29.7.2 | |

**The development stack** is `frappe_docker/pwd.yml` (the app bind-mounted, passwords `admin`, port 8080 on every
interface, `developer_mode` and `allow_tests` on). It stays what it is: the development stack. The production
stack is `deploy/compose.coolify.yaml` (section 2).

**The site `frontend`** (what is migrated): database 79 MB (1.7 MB compressed), files 5 MB. Business records:
113 bookings (XStudio's, imported), 50 customers, 14 studio hour packages, 7 booking resources (XStudio's rooms
and its packages), 38 integration import logs, 3 doctor agreements, 3 book editions, 3 material requests, 2 stock
ledger entries; **no** sales invoice, payment entry, journal entry, GL entry, expense, close or hand-over yet. It
also holds what test runs left behind (section 4, decision needed): 13 `_Test` companies plus 8 other test
companies, 96 `_Test` accounts, 16 cost centers, 12 warehouses, 20 items, 10 customers, 10 suppliers, 40 fiscal
years, and 12 enabled test users (`test@example.com`, `marcus@abc.com`, ...).

**Secrets and environment dependencies** (names only; none printed, none committed):

| Secret | Where it lives today | Needed on the server |
|---|---|---|
| MariaDB root password | `admin` (pwd.yml) | a new one, in Coolify's environment (`DB_ROOT_PASSWORD`) |
| The site's database user and password | `sites/frontend/site_config.json` and the backup's `site_config_backup.json` | recreated by `bench new-site` on the server (the restore keeps the data, the new password stays) |
| The site's `encryption_key` | `site_config.json`, carried in `site_config_backup.json` | **must be carried over**: it unlocks every stored password (XStudio Settings' password, e-mail accounts). Verified: without it the restored copy cannot decrypt (section 10) |
| XStudio: the accountant's login and password, the session token | XStudio Settings (encrypted in the database) | come with the database; readable once the key above is set |
| Supabase `DATABASE_URL` (XStudio staging) | `xstudio-platform/backend/.env` (git-ignored) | not needed by the ERP |
| Administrator and the staff users' passwords | the database | come with it; rotation in section 7 |
| API key and secret of the library connector user | generated once on the user's form | typed into each library PC's `config.json`, never stored elsewhere |
| SSH key for the VPS | `~/.ssh/hostinger_vps` on the Mac | stays there |

**The VPS, read over SSH as root on 27 Oct 2026** (nothing changed): Ubuntu (kernel 6.8), x86_64, **4 vCPU,
16 GB RAM, 193 GB disk (11 GB used)**, Docker Engine 29.7.2, no swap, time zone UTC. **Coolify 4.5.0 is installed
and healthy** (`coolify`, `coolify-db` Postgres 15, `coolify-redis`, `coolify-sentinel`, `coolify-proxy` Traefik
v3.6) with five applications already running (among them `way2a-ai`). Docker network `coolify` is
`172.16.1.0/24`, the proxy at `172.16.1.7`. Listening on every interface: 22, 80, 443, **8000 (the Coolify
dashboard), 8080 (the Traefik dashboard), 6001 and 6002 (Coolify's realtime)**; UFW is **inactive**. Coolify's
backup folder is empty. Resources are enough for the ERP (it needs about 3 GB RAM and one to two vCPU at this
load) beside the apps already there; the disk is ample.

**Requirements the ERP adds**: a domain name with an A record to `72.62.36.46`; outbound HTTPS from the VPS to
`www.xstudioeg.com`; an S3-compatible bucket (Hostinger Object Storage, Backblaze B2, Wasabi, ...) for the
off-server backups; the owner's e-mail for Let's Encrypt notices.

## 1. Hostinger VPS prerequisites (deliverable 1)

Already met: Ubuntu, Docker, Coolify, 4 vCPU, 16 GB, 193 GB. To do before the ERP (section 7 has the commands):

1. A firewall: only 22, 80 and 443 reachable from the internet; 8000 (Coolify) and 8080 (Traefik dashboard)
   reachable only through an SSH tunnel or from the office's address; 6001/6002 are Coolify's own and can stay
   behind the firewall too (Coolify's realtime works through 443 when `APP_URL` is an https domain).
2. SSH: key only (`PasswordAuthentication no`), root login by key only or a sudo user; fail2ban.
3. A swap file of 4 GB (MariaDB and the image build are the memory peaks; the VPS has none).
4. Automatic security updates (`unattended-upgrades`), and the server's clock on UTC (it is).
5. The domain's A record.

## 2. Production container configuration (deliverable 2)

`deploy/compose.coolify.yaml`: the official frappe_docker production layout (`frappe_docker/compose.yaml` with the
`mariadb`, `redis` and `noproxy` overrides) flattened into one file, with:

| Service | Image | Role | Health |
|---|---|---|---|
| configurator | built | writes db and redis addresses into the sites volume, exits | runs once per start |
| backend | built | gunicorn (2 workers × 4 threads) | HTTP answer on :8000 |
| frontend | built | nginx, the only service with a domain, port 8080 inside the network | HTTP answer on :8080 |
| websocket | built | socket.io on :9000 | — |
| queue-short, queue-long | built | `bench worker` | — |
| scheduler | built | `bench schedule` | — |
| db | `mariadb:11.8` | utf8mb4, no published port | `healthcheck.sh --connect --innodb_initialized` |
| redis-cache, redis-queue | `redis:6.2-alpine` | no published port; the queue's data persisted | `redis-cli ping` |

Volumes: `sites` (the site, its files, its config), `logs`, `db-data`, `redis-queue-data`. Workers and the
scheduler start after the configurator finished and the database and both Redis are healthy; nginx after the
backend is healthy. The container health checks ask only that the process answers, because a fresh stack has no
site until the restore (a health check that needed the site kept the first rehearsal from ever coming up: fixed and
re-run). The site's own health is the acceptance test (section 9). Nothing publishes a port: Coolify's proxy reaches
`frontend:8080` on the compose network, `db` and `redis` are reachable from the ERP's containers only.

nginx serves the one site `frontend` whatever the Host header (`FRAPPE_SITE_NAME_HEADER=frontend`), so the site
keeps the name it has in the backup; `host_name` in its config is set to the public URL by the restore script.
The client's real address is taken from `X-Forwarded-For` when the request comes from `172.16.1.0/24` (the proxy).

Pinned: `frappe/erpnext:v16.36.0` (the base of the built image), `mariadb:11.8`, `redis:6.2-alpine`. Upgrading
Frappe or ERPNext is a separate, tested change of `ERPNEXT_VERSION` in the Containerfile, never automatic.

## 3. The custom image (deliverable 3)

`deploy/Containerfile`: `FROM frappe/erpnext:v16.36.0`, copies `apps/imed_erp` from the repository (the only thing
`.dockerignore` lets through), `pip install -e` into the bench environment, lists the app in `sites/apps.txt`,
builds its assets (`bench build --app imed_erp --production`) into the image's asset folder, and proves the import
and the asset folders exist. The entrypoint, gunicorn, nginx template and worker commands are the published
image's own.

```bash
# on any machine with Docker, from the repository root (Coolify does the same on the server):
docker build -f deploy/Containerfile -t imed-erp:test .
```

Built on the Mac on 27 Oct 2026 in 10 seconds on top of the cached base (2.88 GB; arm64 there, amd64 on the server,
where Coolify builds it from the same files). `bench version` inside: erpnext 16.36.0, frappe 16.35.0, imed_erp
0.0.1; `assets/imed_erp/{css,js}` present.

## 4. Coolify configuration (deliverable 4)

In Coolify (https://<the VPS>:8000, or the tunnel):

1. **Project** "IMED ERP", environment "production".
2. **Source**: the GitHub repository (it is public; a GitHub App source is still better for the deploy webhook and
   for making it private later). **Branch**: `production` (section 11: created from the approved commit, never
   pushed by this preparation). **Automatic deployment on push: off** (deployments are started by hand, after a
   backup).
3. **Build pack**: Docker Compose. **Base directory** `/`. **Docker Compose location** `/deploy/compose.coolify.yaml`.
   Coolify builds the image on the VPS from `deploy/Containerfile` (the compose `build:` entries) and creates the
   volumes with its own prefix.
4. **Environment variables** (Developer view): the keys of `deploy/coolify.env.example`. `DB_ROOT_PASSWORD` is
   marked *secret*; the stack refuses to start without it. Nothing else is required; the RESTIC_* values come with
   the backup job (section 7).
5. **Domain**: on the `frontend` service, `https://erp.<domain>` with port 8080 (Coolify's UI asks for the port when
   the service exposes several; here it is 8080). Coolify's Traefik gets the Let's Encrypt certificate itself
   once the A record resolves. No domain on any other service.
6. **Persistent storage**: the four named volumes from the file; nothing else to add. Coolify shows them under
   Storage; they survive redeploys and are not deleted by "Stop".
7. **Health checks**: the ones in the file; Coolify reports the deployment healthy when `frontend` is.
8. **Deploy**: the first deploy brings an empty stack (no site). Then the restore (section 5). Every later
   deploy: backup → "Redeploy" (rebuilds the image from the branch, restarts the containers; the volumes stay) →
   `bench --site frontend migrate` → the checks of section 9. **Rollback**: Coolify keeps the previous image;
   "Redeploy" the previous commit (set the branch's commit or revert the commit in git), then restore the backup
   taken before the deploy if the database changed (`deploy/restore_site.sh` with `FORCE=1`).
9. **Scheduled tasks** (Coolify → the application → Scheduled Tasks, run inside the `backend` container):
   - nightly backup and off-server copy (section 7);
   - nothing else: Frappe's scheduler lives in the `scheduler` container.

Secrets go in Coolify's environment, shown once, never in the repository. Coolify stores them encrypted in its own
Postgres; whoever can open Coolify can read them, so the Coolify login is itself a secret to keep (section 7).

## 5. Migrating the existing site, and the XStudio cutover (deliverables 5 and the XStudio sequence)

The site moves as a bench backup set (database, public files, private files, site config with the encryption
key), restored into the new stack with `deploy/restore_site.sh`, which was written for this and rehearsed
(section 10). **The local site is never changed**: the backup is a copy; the Mac keeps running until the cutover
is confirmed, and its stack is only stopped (not deleted) after that.

Two ERPs must not both sync XStudio: both would read the same bookings and both would write their own copies;
the imports are idempotent per site, so nothing would be duplicated inside one site, but the two sites would
drift apart and the one abandoned would hold imports the other never saw. The sequence keeps exactly one of them
syncing at any moment:

| # | Step | Where | Check |
|---|---|---|---|
| 1 | **Pause**: `bench --site frontend disable-scheduler` on the Mac; wait for a running sync to end (Integration Import Log: no Running row) | Mac | `scheduler status` says disabled; XStudio Settings' Health unchanged |
| 2 | **Final backup**: `scripts/backup_offsite.sh` (or `bench --site frontend backup --with-files`), copy the four files to the Mac and to the owner's drive. This is the **independent recoverable backup**: it is not touched again | Mac | `gzip -t`, `tar -t` pass (the script does both) |
| 3 | **Restore** on the server: copy the set to the VPS (`scp` over the existing key), then `BACKEND=<coolify backend container> SET=... BACKUP_DIR=... DB_ROOT_PASSWORD=... HOST_NAME=https://erp.<domain> deploy/restore_site.sh` | VPS | the script ends "the site is restored, the scheduler is disabled", counts equal the Mac's, "stored passwords decrypt: yes" |
| 4 | **Credentials and encrypted settings**: the script carried the `encryption_key` and set `developer_mode 0`, `allow_tests 0`, `host_name`; open XStudio Settings on the new domain: login shown, password present (dots) | VPS | `bench --site frontend execute imed_erp.imederp.xstudio.sync.dry_run` runs and reads XStudio (writes nothing) |
| 5 | **API connectivity**: the dry run above logs in to xstudioeg.com from the VPS and reads the window; expected: rows read ≈ 160, inserted 0, skipped ≈ 116, 1 failed (the known walk-in booking without a customer, present on the Mac too) | VPS | status "Completed with Errors" with exactly that failed row; Health stays as it was |
| 6 | **Existing imported records**: Booking 113, Customer 50, Studio Hour Package 14, Integration Import Log 38 (the Mac's counts of 27 Oct 14:53; take the real ones at cutover) | VPS | counts equal |
| 7 | **Switch the staff** to the new domain (the Mac's stack is stopped: `docker compose -p frappe_docker -f frappe_docker/pwd.yml stop`, not down) | both | the Mac answers nothing on 8080 |
| 8 | **Enable the scheduler on the server**: `bench --site frontend enable-scheduler`; the four paused Scheduled Job Types stay `stopped = 1` (they come with the database: `recurring_expense.run_daily`, `doctor_accrual.run_daily`, `email_account.pull`, `email_account.notify_unreplied`; verified still paused after the rehearsal restore) | VPS | `scheduler status` enabled; `bench doctor`: workers online |
| 9 | **Idempotency and the first automatic sync**: within 10 minutes a new Integration Import Log appears (trigger scheduler) with inserted 0 / skipped ≈ 116 / the same 1 failed; a second run the same; XStudio Settings' Health "Healthy" and Last Success updated | VPS | two logs, no inserted rows that the Mac did not have, no duplicates (`select import_key, count(*) ... having count(*) > 1` returns nothing) |

XStudio's production data is never written: the client refuses every method but GET and the login POST
(`imederp/xstudio/client.py`); nothing in this procedure changes that.

**Approval checkpoint A** (before step 1): the owner approves the cutover day and hour, the domain, and the test
records decision below. **Checkpoint B** (after step 6, before 7): the counts and the dry run on the server are
shown to the owner; only then are the staff switched.

**Test records (decision needed).** The copy carries the `_Test` companies, accounts, items, warehouses and 12 test
users of section 0 (`bench --site <site> execute imed_erp.setup.list_test_records.run` lists them, read-only).
They do not interfere with the business (their own companies, no entries), but they are clutter in every link
field and the test users can log in. Options: (a) restore as is and **disable the 12 test users** on the server
right after the restore (one command, reversible); (b) also delete the test companies and their records on the
rehearsal copy first, verify, and only then on the server (ERPNext's company deletion tool, a few hours of careful
work, not rehearsed yet); (c) a clean site from the setup scripts with the business records re-imported (XStudio
re-syncs its bookings and packages by itself; the 3 agreements, 3 editions and 3 material requests would be
re-entered). The preparation assumes (a); (b) can be rehearsed on request.

## 6. Domain and HTTPS (deliverable 6)

1. DNS: `erp.<domain>  A  72.62.36.46` (TTL 300 while cutting over).
2. Coolify: the domain on `frontend` (section 4.5). Traefik requests the certificate from Let's Encrypt and renews
   it; nothing to install. HTTP is redirected to HTTPS by Coolify's proxy settings (on by default).
3. The site's `host_name` is set by the restore script to `https://erp.<domain>` (links in e-mails and print
   formats).
4. Security headers: nginx in the image already sends `X-Frame-Options`, `X-Content-Type-Options` and
   `Referrer-Policy` (frappe_docker's `security_headers.conf`); HSTS and the Content-Security-Policy of
   docs/production-hardening.md §2 are added as Traefik middleware labels on `frontend` in Coolify (Custom labels)
   once the site is up and every main screen was opened with the policy on.

## 7. Security, backups and operations (deliverable 7)

**Server** (one-off, as root, before the ERP):
```bash
apt-get install -y ufw fail2ban unattended-upgrades
ufw default deny incoming; ufw default allow outgoing
ufw allow 22/tcp; ufw allow 80/tcp; ufw allow 443/tcp
ufw allow from <office IP> to any port 8000 proto tcp      # Coolify, or reach it through: ssh -L 8000:localhost:8000
ufw enable                                                 # 8080 (Traefik dashboard), 6001, 6002 closed to the internet
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && systemctl reload ssh
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab
```
Docker publishes ports around UFW: the ERP's compose publishes none, so the rule holds for it; check with
`ss -tlnp` after the deploy that only Coolify's own ports and 80/443 listen.

**Least privilege in the ERP**: the site's database user is its own (not root); the library connector posts as
`library-connector@imed.local` with the role *Library Connector* only (`setup/setup_library_connector.py`,
accepted by `library_sync.sync.receive`); XStudio is read with the accountant's existing XStudio login
(read-only by construction); staff roles as today. Login rules of docs/production-hardening.md §3 are applied in
System Settings after the restore (5 attempts, 15 min lock, 12-hour sessions, no e-mail-link login, password
policy, two-factor for the owner and the accountant); the development site has the weak values and they come
with the database, so this is a cutover step, not an option.

**Rotation of what was exposed** (do after the restore, on the server, by the owner, never pasted anywhere):
- `owner@imed.local` and `Administrator`: new passwords (`bench --site frontend set-password <user>` prompts, or the
  user's form). The owner's password was given in this chat on 25 Oct 2026, so it is rotated.
- The 12 test users: disabled (`list_test_records.run` names them).
- `DB_ROOT_PASSWORD`: new on the server by construction (the Mac's `admin` never leaves the Mac).
- XStudio: the accountant's XStudio password was typed by the owner into XStudio Settings, not into chat; rotate it
  in XStudio when convenient and update the setting (the token is renewed by the next run).
- Supabase (staging): its connection string was shown in part in chat on 24 Oct; the project is not needed by the
  production ERP: pause it or reset its database password in the Supabase dashboard.
- The library connector's API secret is generated after the restore (never before, never on the Mac).
- The encryption key is not rotated (that would re-encrypt every stored password); it stays in the two backup
  copies and in Coolify's volume only.

**Backups off the server**: the image ships `restic`. In Coolify → the application → Scheduled Tasks, on the
`backend` container, nightly at 02:30 (server time, UTC) :
```bash
bench --site frontend backup --with-files && restic snapshots -q >/dev/null 2>&1 || restic init && restic backup --tag imed-erp /home/frappe/frappe-bench/sites/frontend/private/backups && restic forget --keep-daily 30 --keep-weekly 12 --prune
```
with `RESTIC_REPOSITORY`, `RESTIC_PASSWORD`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` in the environment
(section 4). Each set holds the site config with the encryption key; the bucket must be private and the restic
password kept with the owner (without it the backups are unreadable). **Restore test, monthly and before every
version**: pull the latest set (`restic restore latest --target /tmp/r`) and run `deploy/restore_site.sh` against
a second site name (`SITE=restore-check`) in the same stack, compare counts, drop the check site. The Mac keeps
the independent copy of the cutover set.

**Monitoring**: Coolify shows container health and restarts; its notifications (Telegram or e-mail) are set in
Coolify → Settings → Notifications: deployment failures and unhealthy containers. Inside the ERP: Integration
Status (sidebar → الإعدادات) and XStudio Settings' Health for the sync; Error Log and Scheduled Job Log for jobs.
Logs: `docker logs <container>` and the `logs` volume (`frappe.log`, `scheduler.log`, `worker.log`).

**Rollback**: section 4.8.

## 8. The second library, PC1 (deliverable 8)

Facts: PC1 is a Windows computer with SQL Server and the database **Db2BDoctor**; the first library's computer
has **Db2BDoctorNew**. Both run the same Tanmya Market application, so both number their documents from 1: the ERP
now keys every mirrored document on the library too (`tanmya:<library>:<family>:<id>`; `library` is a short name
fixed in each PC's `config.json`: `pc1`, and e.g. `azarita` for the first), refuses a batch without it, and
`Library Sales Document` shows the library. A connector user with the role *Library Connector* only posts the
batches. **The schema in hand is Db2BDoctorNew's** (the Generate-Scripts report analysed on 26 Oct); Db2BDoctor is
assumed to be the same product's schema, which the collector run on PC1 confirms or corrects before any import.

Nothing of SQL Server goes to the VPS: the connector runs on PC1, reads with SELECT only, and posts JSON over HTTPS
to `https://erp.<domain>/api/method/imed_erp.imederp.library_sync.sync.receive` with token auth. No inbound port
is opened on PC1 or the library's router.

Steps on PC1 (`scripts/library_connector/`, order matters):

1. `COLLECT_METADATA.bat` (one click, read-only, masked) → bring back `library_metadata_<date>.zip`. From its
   `TblOperationInfo` and `TblStatusRefInfo` rows: the operation codes → kinds, the issued and cancelled status
   codes; from `TblBranchInfo`: PC1's branch code → its cost center (which library PC1 is: to confirm, section 11).
2. A read-only SQL login for the connector (the library's IT, or the owner, in SQL Server Management Studio):
   `CREATE LOGIN imed_reader WITH PASSWORD = '<strong>'; USE Db2BDoctor; CREATE USER imed_reader FOR LOGIN
   imed_reader; ALTER ROLE db_datareader ADD MEMBER imed_reader;` and nothing else. The ODBC string then uses
   `Uid=imed_reader;Pwd=...` instead of `Trusted_Connection=yes`, with `ApplicationIntent=ReadOnly;` kept.
3. `config.json` from `config.pc1.example.json`: `library: pc1`, the ERP URL, the connector user's API key and secret
   (generated on the server after the restore), the maps and codes from step 1, the branch map.
4. `python tanmya_connector.py --config config.json --check`: exit 0 only when no placeholder is left, the database
   is a `Db2BDoctor*`, the intent is read-only and every query is a plain SELECT.
5. `--dry-run`: reads PC1's database and writes `batch_<time>.json` next to the script; nothing is posted. Open it:
   the documents, their codes and branch look right.
6. The first live batch by hand (`python tanmya_connector.py --config config.json`); in the ERP, Integration Status
   shows the log with its counts and the documents under Library Sales Document with library `pc1`. Running it
   again inserts nothing (skipped = all).
7. `install_task.ps1` registers the Task Scheduler job "IMED Library Connector" every 10 minutes as the library's
   Windows user (it refuses while `--check` fails). `connector.log` next to the script keeps each run's line.

Retries and increments are the connector's own: the watermark per family in `state.json`, the last 7 days re-read
every run, three attempts per batch with back-off, and the watermark moves only after the ERP acknowledged.
Imports are idempotent (payload hash) and post nothing to accounting or stock: the mirror is for reading and
reconciliation until the owner decides otherwise.

**Not claimed**: the live connector was not run against a SQL Server. What was tested is in section 10 (the
ERP end with real HTTP and token auth on the rehearsal stack, and the connector's config guard).

## 9. Verification checklist (deliverable 9)

Run on the server after the restore (steps 3–6 of section 5), then again after the switch (steps 7–9):

- [ ] `https://erp.<domain>/login` opens with a valid certificate; `http://` redirects; `http://72.62.36.46:8080` does not answer.
- [ ] `/api/method/ping` → `pong`; `/assets/imed_erp/css/imed_theme.css` → 200; `/socket.io/?EIO=4&transport=polling` → 200.
- [ ] Login as the owner (new password), nour, gilan, the accountant: the sidebar in Arabic, each sees their own business's records; HR sees no booking page (`tests/e2e/halls_27oct.js` logic, by hand or with session ids on the server).
- [ ] Counts equal the cutover backup's: Booking, Customer, Studio Hour Package, Integration Import Log, Booking Resource, Doctor Agreement, Book Edition, Material Request, User; Sales Invoice, GL Entry, Payment Entry, Journal Entry unchanged (0 today).
- [ ] `docker compose ps`: db, redis-cache, redis-queue, backend, frontend healthy; `bench doctor`: 2 workers online.
- [ ] `bench --site frontend scheduler status`: enabled after step 8; the four paused job types still `stopped`.
- [ ] XStudio: the dry run and then two scheduled logs as in section 5 steps 5 and 9; no duplicate `import_key`.
- [ ] Halls apart from the studio: `Booking Resource` of type Hall are only IMED's (none today), the sidebar's two groups, the studio's manager sees no hall booking.
- [ ] Library endpoint: a `POST` with a wrong token → 401; the connector user's token with the rehearsal batch → a log with inserted 2, then skipped 2 (section 10); then delete those two `pc1` test documents (they are marked `PC1-000x` with product "كتاب تجريبي") or keep them cancelled.
- [ ] PC1: `--check` passes, `--dry-run` writes a batch, the source database is untouched (the login is `db_datareader`).
- [ ] Backup: the nightly task ran once by hand, the bucket holds a snapshot, `restic restore` + `restore_site.sh` into `restore-check` matched the counts, `restore-check` dropped.
- [ ] System Settings: login rules of section 7; test users disabled; `developer_mode` and `allow_tests` 0.

## 10. Actual test results (deliverable 10), 27 Oct 2026, on the development Mac

| Test | Result |
|---|---|
| Repository and branch state | `feature/imed-hall-bookings` = `ff1e6a6`, 12 ahead of `main`, 0 behind; working tree clean except untracked library binaries |
| Versions read from the containers | Frappe 16.35.0, ERPNext 16.36.0, Python 3.14.7, Node 24.21.0, MariaDB 11.8.9, Redis 6.2.24 |
| VPS read over SSH (read-only) | Coolify 4.5.0 healthy, Traefik v3.6, Docker 29.7.2, 4 vCPU / 16 GB / 193 GB, UFW inactive, five apps running |
| `docker compose -f deploy/compose.coolify.yaml config` | valid; refuses to start without `DB_ROOT_PASSWORD`; no `ports:` anywhere |
| Image build `deploy/Containerfile` | OK (10 s on the cached base; 2.88 GB); imed_erp 0.0.1 installed, assets built, apps.txt lists erpnext, frappe, imed_erp |
| Rehearsal stack `imedprod` from the compose file and the built image | 9 containers; db, both redis, backend, frontend, websocket, scheduler healthy; `--wait` returned OK (after the health-check fix noted in section 2) |
| Backup of the live local site | `20261027_145315-frontend`: database 1.7 MiB, files 10 KiB each, config 339 B; archives checked |
| Restore into the existing isolated site `restore-test` (development stack) | Booking 113, Customer 50, Studio Hour Package 14, Integration Import Log 38, Booking Resource 7, Doctor Agreement 3, Book Edition 3, User 23: equal to the live site; scheduler disabled by the restore |
| Encryption key | On the restored copy **without** the key: "Failed to decrypt key XStudio Settings.password"; with the key from `site_config_backup.json`: decrypts. The restore script carries it. |
| `deploy/restore_site.sh` into the rehearsal stack | first run: permission error on the copied files (fixed: chown inside the container); second run end to end: restored, key carried, developer_mode/allow_tests off, host_name set, migrated, scheduler disabled, stored passwords decrypt, counts equal |
| Rehearsal stack through nginx | `/api/method/ping` 200 `pong`; `/login` 200; theme CSS 200; frappe desk bundle 200; socket.io polling 200; `bench doctor`: 2 workers online, scheduler disabled |
| Paused jobs after restore | the four job types still `stopped = 1`; `xstudio.sync.run_scheduled` enabled (runs only when the scheduler is) |
| XStudio dry run from the rehearsal stack (reads production XStudio, writes nothing) | window 2026-09-27 → 2026-12-26: rows read 160, inserted 0, skipped 116, failed 1 (booking b9f026fd…: walk-in without a customer account in XStudio, the same row that fails on the Mac every run), notes on incomplete historical usage as on the Mac. Credentials, token and connectivity work on the restored copy |
| New version rollout on the rehearsal stack | image rebuilt with the library changes, `up -d --wait` rolled the containers, `migrate` added the `library` field; the site stayed restored |
| Library endpoint on the rehearsal stack, real HTTP through nginx | connector user created by `setup_library_connector.run` (role Library Connector only); keys generated on the rehearsal copy only; `tanmya_connector.py --from-json` posted a two-document PC1 batch with token auth: log IMP-2026-00039 Completed, read 2, inserted 2; the same batch again: IMP-2026-00040, read 2, skipped 2, inserted 0; both documents keyed `tanmya:pc1:stock:1` and `:2`, library `pc1`, cost center مكتبة المواساة; Sales Invoice, GL Entry, Payment Entry, Journal Entry counts unchanged (0) and Stock Ledger Entry unchanged (2); a wrong token → 401 |
| Library tests | `test_library_sync`: 17 OK (incl. two libraries, same id → two documents; nameless batch refused) |
| Connector config guard | `config.pc1.example.json --check` → exit 2 listing every placeholder; a config without `Db2BDoctor` / `ApplicationIntent=ReadOnly` → listed |
| Full app test suite (earlier today, before the library change) | 748 OK; the library module re-run after the change: OK |

Not tested: the image on amd64 (built on arm64 here; Coolify builds it on the VPS), Let's Encrypt on the real
domain, the restic job against a real bucket (no bucket yet), the connector against a SQL Server, two-factor
login, the Traefik security-header labels.

## 11. Remaining blockers (deliverable 11)

1. **Domain name** for the ERP, and its DNS A record (owner).
2. **Backup bucket** (S3-compatible) and its keys; the restic password chosen and kept by the owner.
3. **Test records decision** (section 5): (a) disable the test users only, or (b) remove the test companies too.
4. **Which library PC1 is** (Azarita or Mawasah) for its cost center, and the first library's name for its `library`
   slug; the PC1 metadata ZIP (`COLLECT_METADATA.bat` on PC1) before its first import.
5. **Coolify access** for whoever runs the deploy (the owner's Coolify login or a member invited), and the GitHub
   source connected in Coolify.
6. **The `production` branch** (or tag) created from the approved commit and pushed: this preparation pushed nothing.
7. **Firewall and SSH hardening** on the VPS (section 7, root): the Coolify dashboard and the Traefik dashboard are
   open to the internet today.
8. Rotation of the exposed credentials after the restore (section 7).
9. HAL-09 / mail: no outgoing e-mail account is set; nothing in the cutover needs one.

## 12. Exact actions and credentials required from you (deliverable 12)

1. Approve the branch to deploy (`feature/imed-hall-bookings` at `ff1e6a6` plus this preparation commit) and
   say the word to push it as `production`.
2. Give the domain (e.g. `erp.imed-academy.com`) and point its A record at `72.62.36.46`.
3. In Coolify: connect the GitHub source (or make the repository a public source) and invite the deployer; or do
   steps 1–8 of section 4 yourself with this document open.
4. Choose and create the backup bucket; give its endpoint and keys to Coolify only; choose the restic password.
5. Decide the test records option (a) or (b).
6. Approve checkpoint A (cutover day/hour) and later checkpoint B (after the counts on the server).
7. After the restore, on the server: set new passwords for `owner@imed.local` and `Administrator`, generate the
   library connector's API keys on its user form and type them into PC1's `config.json`; apply the login rules.
8. For PC1: run `COLLECT_METADATA.bat` there and bring the ZIP; tell which library PC1 is; have the read-only SQL
   login created.
9. Authorise, explicitly and separately: the push, the first Coolify deploy, the restore on the server, the
   switch of the staff, enabling the scheduler. Nothing of these is done by this preparation.
