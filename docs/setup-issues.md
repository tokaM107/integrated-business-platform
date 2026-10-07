# Setup issues

Every error met while setting up the environment, with its cause and fix. Add new ones at the top of
the table they belong to, with the date and who met it.

## Environment (Docker, bench)

| Date | Problem | Cause | Fix |
|---|---|---|---|
| 2026-09-29 | `imed_erp` missing from the containers (`ls apps` shows only frappe and erpnext); the ImedERP doctypes do not exist on the site | Containers created from an old `pwd.yml` that did not mount the app; the app was copied into the container and lost when it was recreated | Pull the latest `pwd.yml` (it mounts `../apps/imed_erp`) and run `docker compose -p frappe_docker -f pwd.yml up -d` again, then the install steps in the README |
| 2026-09-29 | `bench new-site ... --install-app imed_erp` / `install-app` fails: app not found | `imed_erp` is not listed in `sites/apps.txt` | `docker exec frappe_docker-backend-1 bash -c "grep -qx imed_erp sites/apps.txt \|\| echo imed_erp >> sites/apps.txt"` |
| 2026-09-29 | `docker: failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` | Docker Desktop not running | Start Docker Desktop; the containers restart by themselves |
| 2026-09-29 | Git Bash: `docker exec -w /home/...` fails with `Cwd must be an absolute path` | Git Bash rewrites Unix paths into Windows paths | Prefix the command with `MSYS_NO_PATHCONV=1`, or use PowerShell |
| 2026-09-29 | `python` not found on Windows | Python is not installed on the host; it is not needed | Run Python inside the container (`bench console`, or `env/bin/python`) |
| before 2026-09-29 | `Module ImedERP not found` after a rebuild | Stale cache | `bench --site frontend clear-cache` |
| before 2026-09-29 | Invoice PDF: `wkhtmltopdf ... network error: Connection refused` / `HostNotFound` | wkhtmltopdf loads the stylesheets over HTTP from `host_name`, which is not reachable inside Docker | `bench --site <site> set-config host_name "http://frontend:8080"` |

## Setup scripts

| Date | Problem | Cause | Fix |
|---|---|---|---|
| 2026-10-04 (Toka) | Running `bench run-tests` left 21 `_Test` companies, about 2,100 accounts, 12 users and a 1,000,000 EGP stock entry on the real company | A new Link field (to User) was not in the test file's `IGNORE_TEST_RECORD_DEPENDENCIES`, so Frappe built ERPNext's test records and committed them | Removed by creation-time window; every doctype test file now lists its links (see README, Tests). Take a backup and copy it out of the container before running tests |
| 2026-10-07 (Toka) | A4 paper lost its ream (500) and box (2500) conversion factors; a purchase by the box would come in as one sheet | ERPNext empties an item's UOM table when its stock UOM changes (Nos to ورقة here) and only shows a short alert | `setup_core.py` puts the factors back on every run (`ensure_conversions`); `verify_setup.py` and `test_paper_stock.py` check them |
| 2026-09-29 | On a new site `setup_regional.py` stops: `Company 'Mohamed Mamdouh group' ... not found` | The README ran `setup_regional.py` before `setup_core.py`, which creates the company | Order changed: `setup_core.py` runs first |
| 2026-09-29 | On a new site `setup_core.py` fails: `Could not find Warehouse Type: Transit` | The setup wizard was not done, so ERPNext's base records do not exist | `setup_core.py` now completes the setup wizard itself on a new site |
| 2026-09-29 | `setup_core.py` fails creating items: `Warehouse Stores - I doesn't belong to Company Mohamed Mamdouh group` | Another company exists (created by the browser wizard); Frappe fills the item's warehouse from the site default | `setup_core.py` sets MMG's own warehouse (Store Mawasah) on each item |
| 2026-09-29 | Fiscal year 2026-2027 runs Jul–Jun instead of Sep–Aug; `setup_regional.py` only warned, leaving Jul–Aug 2027 in no fiscal year | The browser setup wizard creates a Jul–Jun year for Egypt; ERPNext cannot change a saved year's dates | `setup_regional.py` replaces the wrong year if nothing is posted in it, keeping the companies it applied to |
| before 2026-09-29 | Creating an Accounting Period crashes: `'dict' object has no attribute 'document_type'` | ERPNext v16 bug when the closed documents list is left empty | `close_period.py` / `check_financial.py` pass the list explicitly |
| before 2026-09-29 | Branch managers cannot read any Item; store managers cannot read any Warehouse | `apply_strict_user_permissions` on | Kept off by `setup_users.py` |
| before 2026-09-29 | Invoice PDF export breaks | The default EGP symbol is Arabic (`ج.م`) | `setup_regional.py` sets the symbol to `EGP` |

## Still to record

- Eman's first installation of Docker and frappe_docker (Day 2): add each error met at the time.
- The temporary test doctype (create, then delete with developer mode on): record the result here.
