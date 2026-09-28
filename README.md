# integrated-business-platform

ERPNext setup for **Mohamed Mamdouh group (MMG)**, an Egyptian multi-business group (currency EGP):

| Business | Cost center |
|---|---|
| Imed Center lecture halls | Imed Center → Imed Halls |
| X Studio (photography, inside the Imed Center premises) | Imed Center → X Studio |
| Shared rent / electricity of the center premises | Imed Center → Center Shared Expenses |
| 2Be Doctor Library, Azarita branch | Libraries → 2Be Doctor Azarita |
| 2Be Doctor Library, Mawasah branch (holds the central store) | Libraries → 2Be Doctor Mawasah |
| BA+ App | BA Plus App |

Project files: https://drive.google.com/drive/folders/1kYML83xHgfcTFBl0uctAHT_EjjVqUj9v?usp=sharing

## Repository layout

```
apps/imed_erp/          Custom Frappe app (doctypes, workspace, setup scripts)
  imed_erp/imederp/     Module "ImedERP": Doctor Agreement, Academic Period, Book Edition,
                        Doctor Ledger Entry, Printer Reading, App Subscription, Owner Dashboard
  imed_erp/setup/       One-off setup scripts run from bench console (see below)
frappe_docker/          Upstream frappe/frappe_docker, used to run ERPNext locally (pwd.yml)
```

## Running ERPNext locally

```bash
cd frappe_docker
docker compose -f pwd.yml up -d
```

The site is `frontend` and is served at http://localhost:8080.

## Installing the imed_erp app

In `pwd.yml` only `sites/` and `logs/` are Docker volumes. The `apps/` folder lives inside the
container, so **`imed_erp` is lost whenever the backend container is recreated** (for example after
`docker compose down`). This repository is the copy that survives. To put the app back into the
container:

```bash
docker cp apps/imed_erp frappe_docker-backend-1:/home/frappe/frappe-bench/apps/
docker exec -u root frappe_docker-backend-1 chown -R frappe:frappe /home/frappe/frappe-bench/apps/imed_erp
docker exec frappe_docker-backend-1 bash -c "cd /home/frappe/frappe-bench && env/bin/pip install -e apps/imed_erp"
```

Then, on a new site only:

```bash
docker exec frappe_docker-backend-1 bench --site frontend install-app imed_erp
```

After changing doctypes, run `bench --site frontend migrate` inside the container.

Edits made in the ERPNext UI while developer mode is on are saved inside the container. Copy them back
into this repo before committing:

```bash
docker exec frappe_docker-backend-1 tar -C /home/frappe/frappe-bench/apps -cf - --exclude=.git --exclude=__pycache__ imed_erp | tar -C apps -xf -
```

## Setup scripts

The scripts in `apps/imed_erp/imed_erp/setup/` are run from bench console:

```bash
docker exec -it frappe_docker-backend-1 bench --site frontend console
```

Then, in this order:

```python
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_regional.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_master.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_users.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_dashboard.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/verify_setup.py").read(), {"frappe": frappe})
```

| Script | What it does |
|---|---|
| `setup_regional.py` | Regional settings: EGP currency (symbol `EGP`, 2 decimals), fiscal year 2026-2027 (1 Sep – 31 Aug, linked to the company), date format `dd/mm/yyyy`, 24-hour time, number format `1,234,567.89`, commercial (half-up) rounding, week starting Saturday. |
| `setup_master.py` | Cost center tree, accounts, warehouses, UOMs (Ream, Box) and items. |
| `setup_users.py` | Branch Manager role, 8 users (`name@imed.local`), and User Permissions that restrict each branch manager to their own cost center and warehouse. Declarative: re-running also corrects drift (name, enabled flag, extra roles, stale User Permissions). Prints a summary table. |
| `setup_dashboard.py` | Number Cards, Dashboard Charts and the Owner Dashboard workspace. Deletes and recreates them each run. |
| `verify_setup.py` | Read-only. Prints found/expected counts and flags anything missing or misconfigured. |

`setup_regional.py`, `setup_master.py`, `setup_users.py` and `verify_setup.py` are idempotent, so they can be re-run
safely. They only ever touch the company `Mohamed Mamdouh group` (abbreviation `MMG`), which is
hardcoded; the demo company `Mohamed Mamdouh group (Demo)` is left alone.

### Users and initial passwords

`USERS` at the top of `setup_users.py` is the single source of truth for the users, their roles and
their cost centers / warehouses (keep the copy in `verify_setup.py` in sync). The script stops before
writing anything if the company, a role, a cost center or a warehouse it needs is missing.

No password is stored in the repository. Passwords are only set when a user is **created**; existing
users' passwords are never touched. Either:

- pass one initial password through the environment (never commit it):

  ```bash
  docker exec -it -e IMED_INITIAL_PASSWORD='<choose-a-strong-one>' frappe_docker-backend-1 bench --site frontend console
  ```

- or leave `IMED_INITIAL_PASSWORD` unset: each new user gets a random password, printed once at the
  end of the run. Hand each one over privately and have the user change it at first login.

`apply_strict_user_permissions` is kept **off** on purpose: with it on, branch managers cannot read
any Item and the store managers cannot read any Warehouse (tested on ERPNext v16).

The `setup/` folder deliberately has no `__init__.py`: the scripts write to the database as soon as
they are executed, so they must never be imported as a Python module.
