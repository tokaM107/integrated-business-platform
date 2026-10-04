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
docker compose -p frappe_docker -f pwd.yml up -d
```

The site is `frontend` and is served at http://localhost:8080.

## How the imed_erp app is loaded

`pwd.yml` mounts this repository's `apps/imed_erp` folder into the backend, worker, scheduler and
setup containers, and sets `PYTHONPATH` so Python can import it. So:

- The app **survives** `docker compose down` / container rebuilds; there is nothing to copy back.
- Editing a file in `apps/imed_erp` changes it on the site immediately (restart `backend` for Python
  changes to controllers: `docker compose -p frappe_docker -f pwd.yml restart backend`).
- Changes made in the ERPNext UI in developer mode (doctypes, workspace) are written straight into
  this folder, ready to commit.

On a new site only, install the app once:

```bash
docker exec frappe_docker-backend-1 bench --site frontend install-app imed_erp
```

After changing a doctype's JSON by hand, run `bench --site frontend migrate` inside the container.
If a script says "Module ImedERP not found" after a rebuild, clear the cache:
`docker exec frappe_docker-backend-1 bench --site frontend clear-cache`.

## Permissions on the ImedERP doctypes

| DocType | Accounts Manager | Accounts User / Branch Manager |
|---|---|---|
| Academic Period, Doctor Agreement, Doctor Ledger Entry | full | read only |
| Book Edition, Printer Reading, App Subscription | full | create, edit, submit (no cancel/delete) |

Branch managers also have Accounts User (to create sales invoices), so both roles get the same rights
here. Agreements and the doctors' ledger are managed by Accounts Manager (Owner, Accountant).

Book Edition and App Subscription have a required **Cost Center** field (Printer Reading has its
**Branch** field). Only leaf cost centers can be picked, and saving with a group (e.g. "Libraries") is
rejected. Through the User Permissions, each branch manager sees only their own records: Sara sees only
Azarita's editions, Raghad only Mawasah's, Menna only the app's subscriptions.

## Language and invoice printing

Everyone who uses the system gets the Arabic interface; Administrator stays in English
(`setup_regional.py`). Account, item, cost center and warehouse **names** stay in English on purpose.

Sales invoices print with the app's own format, **MMG Sales Invoice**
(`imederp/print_format/mmg_sales_invoice`), set as the default by `setup_regional.py`:

- Printed in Arabic: every label in Arabic, right-to-left, units as وحدة / رزمة / كرتونة. Printed in
  English (Administrator): the same layout in English. ERPNext's own format hardcodes several English
  labels and mistranslates others ("Amount", "Nos"), so it cannot be fixed with translations alone.
- Amount in words always matches the printed total, to the piastre:
  `فقط ثلاثة آلاف و سبعمائة و ثلاثة جنيه مصري وخمسون قرشًا لا غير` for EGP 3,703.50.
  Rounded totals are switched off (`Global Defaults > Disable Rounded Total`), so the amount due is
  the exact total, not rounded to the pound.
- It draws its own header (logo, company, title, number) instead of the site letter head, which
  prints the English doctype name.

## Setup scripts

The scripts in `apps/imed_erp/imed_erp/setup/` are run from bench console:

```bash
docker exec -it frappe_docker-backend-1 bench --site frontend console
```

Then, in this order:

```python
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_regional.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_core.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_users.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_library.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_dashboard.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/verify_setup.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/check_financial.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/check_library.py").read(), {"frappe": frappe})
```

| Script | What it does |
|---|---|
| `setup_regional.py` | Regional settings: EGP currency (symbol `EGP`, 2 decimals), fiscal years 2026-2027 and 2027-2028 (1 Sep – 31 Aug, linked to the company), Arabic interface for users / English for Administrator, rounded totals off, MMG Sales Invoice as the default invoice print format, date format `dd-mm-yyyy`, 24-hour time, number format `1,234,567.89`, commercial (half-up) rounding, week starting Saturday. |
| `setup_core.py` | Company (MMG, EGP), cost center tree, warehouses (raw materials and doctors' editions per library), UOMs (Ream = 500 sheets, Box = 5 Reams = 2500 sheets) and items. Runs `setup_coa.py` itself, after the warehouses. |
| `setup_arabic_names.py` | Renames the company's accounts, cost centers, warehouses, item groups, UOMs (Ream, Box) and item names from English to Arabic, updating every link. `setup_core.py` runs it right after the company exists. Leaves the company name, the `All Item Groups` root and the `Nos` UOM in English (ERPNext uses them by name). Screen texts of the app's own doctypes and reports are translated in `imed_erp/translations/ar.csv`. |
| `setup_coa.py` | Chart of accounts from the posting rules document (v2.0, section 2): treasuries, one revenue account per business, costs and expenses, doctors' and lecturers' balances, the inter business current account, and one stock account per library and kind, linked to its warehouse. Reuses the accounts ERPNext already ships (rent, salaries, utilities, ...) and deletes the old Books / Printing Revenue accounts. Can also be run on its own. |
| `setup_users.py` | Branch Manager role, 8 users (`name@imed.local`), and User Permissions that restrict each branch manager to their own cost center and warehouse. Declarative: re-running also corrects drift (name, enabled flag, extra roles, stale User Permissions). Prints a summary table. |
| `setup_library.py` | Libraries (LIB). Makes `منتجات المكتبات` a parent group with `كتب`, `مذكرات` and `خدمات المكتبات` under it; the Author field on Item; the non-stock services COPY-SVC, PRINT-SVC, BINDING-SVC (moved into `خدمات المكتبات`); the stock items BOOK and MEMO; item defaults (revenue `إيراد مكتبة المواساة`, cost center `مكتبة المواساة`, warehouse `إصدارات الأطباء — المواساة`); one POS Profile per library, which gives each sale its own warehouse and cost center. Books and memos are listed in `LIBRARY_ITEMS` at the top (one generic item each until the catalogue is known). Creates no account, cost center or warehouse: a missing one is printed as `WAIT`. Idempotent. |
| `setup_dashboard.py` | Number Cards, Dashboard Charts and the Owner Dashboard workspace. Deletes and recreates them each run. |
| `verify_setup.py` | Read-only. Prints found/expected counts and flags anything missing or misconfigured. |
| `check_financial.py` | Test, rolled back afterwards. Checks EGP on the company and Global Defaults, the fiscal year, `dd-mm-yyyy` dates, number format, that a printed invoice (HTML and PDF) shows `EGP` and not `£`, and that a closed accounting period blocks invoices and journal entries (CORE-09). |
| `check_library.py` | Test, rolled back afterwards. Creates a test book and memo, receives them in Mawasah's store, issues books to Azarita, then sells through each library's POS Profile and through a plain sales invoice, and checks that the revenue account (Azarita's sales moved to `إيراد مكتبة الأزاريطة` by `imederp/library_revenue.py`), cost center and warehouse were filled in without being typed. |
| `close_period.py` | Month-end close (CORE-09). Creates an Accounting Period for a finished month with all 18 posting document types closed, so nothing dated in that month can be posted, edited or cancelled. Set `MONTH = "YYYY-MM"` at the top, or leave it empty for last month. Run it only at month end: it changes the books. |

`setup_regional.py`, `setup_core.py`, `setup_arabic_names.py`, `setup_coa.py`, `setup_users.py` and `verify_setup.py` are idempotent, so they can be re-run
safely. They only ever touch the company `Mohamed Mamdouh group` (abbreviation `MMG`), which is
hardcoded; the demo company `Mohamed Mamdouh group (Demo)` is left alone.

### Library products (LIB-06)

| Requirement | Where it is in ERPNext |
|---|---|
| Name | Item Name |
| ISBN | A row in the item's **Barcodes** table with type `ISBN` (so it can be scanned at the POS) |
| Author | **Author** field on the item (`custom_author`) |
| Category | Item Group: `كتب` or `مذكرات` |
| Cost price | Valuation Rate |
| Selling price | Item Price in the `Standard Selling` price list |
| Quantity | Stock balance per warehouse (`إصدارات الأطباء — المواساة` under the central store, `إصدارات الأطباء — الأزاريطة` for the branch) |

The warehouse and cost center come from the library's POS Profile; without one, from the item's
defaults (Mawasah). The revenue account comes from the item and is then moved to the selling
library's account by `imederp/library_revenue.py`. An item has only one default per company and both
libraries sell the same book, so Azarita must sell through its POS Profile. A sales invoice row
created through the API without a cost center gets the company's default cost center, not the item's,
so an integration must send the cost center itself.

To reopen a closed month: Accounting > Accounting Period > open the month > untick **Closed** on the
document types to allow (or tick **Disabled** to reopen everything).

Invoice PDFs need the site's `host_name` to point at the web server inside Docker, otherwise
wkhtmltopdf cannot load the stylesheets (`network error: Connection refused`):

```bash
docker exec frappe_docker-backend-1 bench --site frontend set-config host_name "http://frontend:8080"
```

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
