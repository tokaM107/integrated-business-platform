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
                        Doctor Ledger Entry, Printer Reading, App Subscription, Owner Dashboard,
                        Expense, Expense Category, Expense Report
  imed_erp/setup/       One-off setup scripts run from bench console (see below)
frappe_docker/          Upstream frappe/frappe_docker, used to run ERPNext locally (pwd.yml)
```

## Versions

| Component | Version |
|---|---|
| ERPNext | **v16.36.0** (image `frappe/erpnext:v16.36.0`, pinned in `frappe_docker/pwd.yml`) |
| Frappe | v16.35.0 (inside that image) |
| MariaDB | 11.8 |
| Python (in the containers) | 3.14 |

Both developers must use this same image tag. To upgrade, change the tag in `pwd.yml` for every
service in one commit, then run `bench --site frontend migrate`.

## Setup from scratch

Prerequisites: Docker Desktop (with WSL 2 on Windows) and Git. Nothing else is needed on the host;
Python and bench live inside the containers.

```bash
git clone https://github.com/tokaM107/integrated-business-platform.git
cd integrated-business-platform/frappe_docker
docker compose -p frappe_docker -f pwd.yml up -d
```

The first start creates the site `frontend` (served at http://localhost:8080, login `Administrator` /
`admin`). Wait until `docker logs frappe_docker-create-site-1` ends, then:

```bash
# 1) Make the app known to bench and install it on the site
docker exec frappe_docker-backend-1 bash -c "grep -qx imed_erp sites/apps.txt || echo imed_erp >> sites/apps.txt"
docker exec frappe_docker-backend-1 bench --site frontend install-app imed_erp

# 2) Developer mode, so doctype changes made in the UI are written to apps/imed_erp
docker exec frappe_docker-backend-1 bench --site frontend set-config developer_mode 1

# 3) Invoice PDFs: let wkhtmltopdf reach the web server inside Docker
docker exec frappe_docker-backend-1 bench --site frontend set-config host_name "http://frontend:8080"

docker exec frappe_docker-backend-1 bench --site frontend clear-cache
```

Then run the setup scripts (next sections). **Do not complete the setup wizard in the browser**:
`setup_core.py` completes it itself with the right company, currency and Sep–Aug fiscal year. (If it
was already completed in the browser, the scripts still work: `setup_regional.py` replaces a wrongly
dated fiscal year as long as nothing has been posted in it.)

Measured on 2026-09-29 on a new site: creating the site with ERPNext and imed_erp about 1.5 minutes,
all setup scripts about 40 seconds, so the whole system is built in about 2.5 minutes.

Problems met while setting up, and their fixes: [docs/setup-issues.md](docs/setup-issues.md).

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
| Book Edition | full | create, edit (no submit: submitting approves the edition's pricing) |
| Printer Reading, App Subscription | full | create, edit, submit (no cancel/delete) |
| Expense | full | create, edit, submit (no cancel/delete) |
| Expense Category | full | read only |

Branch managers also have Accounts User (to create sales invoices), so both roles get the same rights
here. Agreements, the doctors' ledger and edition pricing are approved by Accounts Manager (Owner,
Accountant), as in the permissions matrix.

Academic Periods form a tree: a **Round** belongs to a **Term** and a **Module** to a **Round**
(field *Parent Period*), and each period must fall inside its parent's dates.

## Roles and the permissions matrix (requirements §3.2)

| Requirement role | Users | ERPNext roles it comes with |
|---|---|---|
| Super Admin | Owner | System Manager, Accounts Manager |
| Accountant | Accountant | Accounts User, Accounts Manager |
| Branch Manager | Nour, Gilan, Menna, Raghad, Sara | Sales User, Accounts User (+ Stock User for the libraries) |
| HR | HR | HR Manager |
| CRM Staff | nobody yet | none yet (the CRM module is not built) |

`setup_users.py` applies the matrix rows that exist in the system today:

- Only Super Admin and Accountant can **cancel, amend or delete** a financial document (sales / purchase
  / POS invoice, payment, journal entry, stock entry, delivery note, purchase receipt, stock
  reconciliation). Branch managers can create, edit drafts and submit them.
- Branch managers see only their own cost center (and warehouse); Owner and Accountant see all.
- Employees: Super Admin and HR manage them, Accountant can view them.

Rows for modules not built yet (bookings, integrations, AI assistant, price approval) are listed by
`verify_users.py` as not checked.

## Notifications (CORE-10)

`imed_erp/notification_service.py` is the one entry point every module uses to notify people:

```python
from imed_erp.notification_service import notify
notify("doctor_settlement_due", ["accountant@imed.local"], {"doctor": "Dr. X", "amount": "EGP 1,500.00"})
```

Events and their (placeholder) templates are in `EVENTS`. In-app notifications work now, e-mail works
once an outgoing Email Account is set up; WhatsApp and SMS adapters only log until a provider is chosen.

Book Edition and App Subscription have a required **Cost Center** field (Printer Reading has its
**Branch** field). Only leaf cost centers can be picked, and saving with a group (e.g. "Libraries") is
rejected. Through the User Permissions, each branch manager sees only their own records: Sara sees only
Azarita's editions, Raghad only Mawasah's, Menna only the app's subscriptions.

## Interface theme (IMED ERP)

The desk has its own look, **without changing Frappe or ERPNext**: a CSS layer that re-maps Frappe v16's
design tokens and refines a few components. It is loaded from `hooks.py` and needs no build step.

| File (in `apps/imed_erp/imed_erp/public`) | What it is |
|---|---|
| `css/imed_theme.css` | The desk theme: colour, type and shape tokens (light and dark), then sidebar, page head, buttons, inputs, forms, lists, dashboards, home screen, dialogs, toasts, empty states, small screens. |
| `css/imed_web.css` | The login page only (every rule is scoped to `#page-login`). |
| `js/imed_home.js` | Home screen: a greeting band (greeting, today's date, company) with quick actions, each shown only if the user has the permission for it. Hooks into Frappe's `desktop_screen` event and only adds elements; the app grid and its edit mode are Frappe's own. |
| `js/imed_theme_toggle.js` | One-click light / dark switch next to the notifications (beside the bell on the home screen, under "Notification" in the sidebar). Uses Frappe's own theme setting, so the choice is saved to the user. |
| `css/imed_fonts.css`, `fonts/` | IBM Plex Sans Arabic (SIL OFL, licence in `fonts/OFL.txt`), bundled so it works without internet. Only Arabic text uses it; Latin stays on Inter. |
| `images/imed-mark.svg` | Logo and favicon. |
| `icons/desktop_icons/{solid,subtle}/owner_dashboard.svg` | The Owner Dashboard icon on the home screen. |

- **Colours:** teal (`--imed-teal-600` = `#0f766e`) is the primary colour, amber is a rare accent. On the
  dashboard, colour has a meaning: teal = income, amber = needs attention, slate = neutral counts. To change
  the brand colour, change the `--imed-teal-*` scale at the top of `imed_theme.css`.
- **Arabic / RTL:** every left/right spacing uses logical properties (`inline-start` / `inline-end`), so the
  Arabic interface mirrors correctly.
- **Dark mode** (user menu > Toggle Theme) is fully themed.
- **Serving the files:** `pwd.yml` mounts `public/` at `/assets/imed_erp` in the frontend (nginx) and backend
  containers. Without that mount the browser gets 404 for the theme.
- **After editing a CSS file:** reload the page (Ctrl+Shift+R). After changing `hooks.py`: restart the backend
  and run `bench --site frontend clear-cache`.

## AI assistant (chat window, not connected to a model yet)

The owner sees an animated character at the bottom corner of the home screen. Clicking it opens a chat
panel at the side: type a question or record a voice message. Until a model is connected, an offline
placeholder answers that the assistant is not connected yet, so the window, voice and permissions can
already be used and tested.

| File | What it is |
|---|---|
| `public/js/imed_assistant.js`, `public/css/imed_assistant.css` | The character and the chat panel. The conversation stays in the browser tab and is sent with each message. |
| `imed_erp/assistant/api.py` | `get_status` and `send_message` (text, or base64 audio up to 10 MB). Checks who may use it. |
| `imed_erp/assistant/providers.py` | **The one place a model plugs in.** `AssistantProvider.reply(messages, context)` and `transcribe(audio, mime_type, context)`. |

- **Who can use it:** Super Admin (the owner) and System Manager (developers), per the permissions matrix
  and open question 22. Others do not see the character, and the server refuses their requests
  (`ALLOWED_ROLES` in `api.py`).
- **Read only (AI-02):** the assistant answers questions; it must never create, change or delete records. A
  provider reads data as the current user (their permissions apply), never with `ignore_permissions`.
- **Connecting a model later:** write a subclass of `AssistantProvider` (e.g. `imed_erp/assistant/claude.py`)
  and set it for the site; the chat window and API do not change:

  ```bash
  docker exec frappe_docker-backend-1 bench --site frontend set-config imed_assistant_provider "imed_erp.assistant.claude.ClaudeProvider"
  ```

  `messages` arrive as `[{"role": "user" | "assistant", "content": "..."}]`, oldest first, the shape model
  APIs take. Voice needs a speech-to-text service in `transcribe()`; the language model itself does not
  transcribe audio. Keep API keys in `site_config.json` (never in the repository).

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
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_core.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_regional.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_users.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_library.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_expenses.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_dashboard.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/verify_setup.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/verify_users.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/check_financial.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/check_library.py").read(), {"frappe": frappe})
```

`setup_core.py` must run first: it creates the company that every other script needs.
`setup_users.py` checks that the cost centers and warehouses from `setup_core.py` exist and stops
without changing anything if they do not (so a user is never created without their restrictions).

| Script | What it does |
|---|---|
| `setup_core.py` | Run first. On a new site it completes the setup wizard (company MMG, EGP, fiscal year Sep–Aug). Then: cost center tree, warehouses (raw materials and doctors' editions per library), UOMs (Ream = 500 sheets, Box = carton = 5 Reams = 2500 sheets) and items. Runs `setup_coa.py` itself, after the warehouses. |
| `setup_regional.py` | Regional settings: EGP currency (symbol `EGP`, 2 decimals), fiscal years 2026-2027 and 2027-2028 (1 Sep – 31 Aug, linked to the company; a wrongly dated year with nothing posted in it, e.g. the Jul–Jun one the browser wizard creates, is replaced), Arabic interface for users / English for Administrator, rounded totals off, MMG Sales Invoice as the default invoice print format, date format `dd-mm-yyyy`, 24-hour time, number format `1,234,567.89`, commercial (half-up) rounding, week starting Saturday. |
| `setup_users.py` | The requirement roles (Super Admin, Accountant, Branch Manager, HR, CRM Staff), 8 users (`name@imed.local`), User Permissions that restrict each branch manager to their own cost center and warehouse, and the permissions matrix (requirements §3.2) on financial documents. Declarative: re-running also corrects drift (name, enabled flag, extra roles, stale User Permissions). Prints a summary table. |
| `setup_arabic_names.py` | Renames the company's accounts, cost centers, warehouses, item groups, UOMs (Ream, Box) and item names from English to Arabic, updating every link. `setup_core.py` runs it right after the company exists. Leaves the company name, the `All Item Groups` root and the `Nos` UOM in English (ERPNext uses them by name). Screen texts of the app's own doctypes and reports are translated in `imed_erp/translations/ar.csv`. |
| `setup_coa.py` | Chart of accounts from the posting rules document (v2.0, section 2): treasuries, one revenue account per business, costs and expenses, doctors' and lecturers' balances, the inter business current account, and one stock account per library and kind, linked to its warehouse. Reuses the accounts ERPNext already ships (rent, salaries, utilities, ...) and deletes the old Books / Printing Revenue accounts. Can also be run on its own. |
| `setup_library.py` | Libraries (LIB). Makes `منتجات المكتبات` a parent group with `كتب`, `مذكرات` and `خدمات المكتبات` under it; the Author field on Item; the non-stock services COPY-SVC, PRINT-SVC, BINDING-SVC (moved into `خدمات المكتبات`); the stock items BOOK and MEMO; item defaults (revenue `إيراد مكتبة المواساة`, cost center `مكتبة المواساة`, warehouse `إصدارات الأطباء — المواساة`); one POS Profile per library, which gives each sale its own warehouse and cost center. Books and memos are listed in `LIBRARY_ITEMS` at the top (one generic item each until the catalogue is known). Creates no account, cost center or warehouse: a missing one is printed as `WAIT`. Idempotent. |
| `setup_dashboard.py` | Number Cards, Dashboard Charts and the Owner Dashboard workspace (deleted and recreated each run), in the theme's colours, plus the branding settings the theme needs: app name, logo (Navbar Settings), launcher icon style, Owner Dashboard icon. |
| `verify_setup.py` | Read-only. Prints found/expected counts and flags anything missing or misconfigured. |
| `verify_users.py` | Read-only. For every `@imed.local` user: their restrictions, the cost centers they can see, and yes/no for each right in the permissions matrix, marked PASS/FAIL against the matrix. |
| `check_financial.py` | Test, rolled back afterwards. Checks EGP on the company and Global Defaults, the fiscal year, `dd-mm-yyyy` dates, number format, that a printed invoice (HTML and PDF) shows `EGP` and not `£`, and that a closed accounting period blocks invoices and journal entries (CORE-09). |
| `check_library.py` | Test, rolled back afterwards. Creates a test book and memo, receives them in Mawasah's store, issues books to Azarita, then sells through each library's POS Profile and through a plain sales invoice, and checks that the revenue account (Azarita's sales moved to `إيراد مكتبة الأزاريطة` by `imederp/library_revenue.py`), cost center and warehouse were filled in without being typed. |
| `setup_expenses.py` | Expense categories (EXP-07): the tree `كل المصروفات` with `الإيجار`, `المرافق`, `الرواتب والأجور`, `الخامات والمستهلكات`, `الصيانة`, `التسويق` and `الهالك والتالف` under it, each linked to the expense account of the same name (or the English name ERPNext ships it with, before `setup_arabic_names.py`). Creates no account: a missing one is printed as `WAIT`, and re-running links it once it exists. Idempotent. |
| `close_period.py` | Month-end close (CORE-09). Creates an Accounting Period for a finished month with all 18 posting document types closed, so nothing dated in that month can be posted, edited or cancelled. Set `MONTH = "YYYY-MM"` at the top, or leave it empty for last month. Run it only at month end: it changes the books. |

`setup_core.py`, `setup_regional.py`, `setup_arabic_names.py`, `setup_coa.py`, `setup_users.py`, `verify_setup.py` and `verify_users.py` are idempotent, so they can be re-run
safely. They only ever touch the company `Mohamed Mamdouh group` (abbreviation `MMG`), which is
hardcoded; the demo company `Mohamed Mamdouh group (Demo)` is left alone.

### Expenses (EXP-01/02, EXP-07)

An **Expense** records one payment: Activity (a leaf cost center), Expense Category, Expense Amount,
Cash/Bank Account (a leaf cash or wallet account), Supplier (optional: salaries have none) and
Receipt Attachment. A draft can be saved without the receipt, but submitting is refused until one is
attached. The check is in the controller's `before_submit`, so it also holds for the API; the receipt
must be an uploaded image or PDF. Submitting posts a journal entry: debit the category's expense
account, credit the treasury, both on the activity's cost center. Cancelling reverses it.

**Expense Category** is a tree (ImedERP > Expense Category > Tree view). Expenses are recorded on the
categories inside a group, not on the group. A category without its own expense account is posted to its
nearest parent's, so a sub-category such as `كهرباء` under `المرافق` needs no account of its own.

The **Expense Report** lists submitted expenses filtered by period, activity, category, supplier and
treasury. Choosing a group activity (e.g. `مكتبات 2Be Doctor`) or a group category includes everything
under it. **Group Totals By** gives one total per category, activity, month, or their combinations.

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
