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
                        Expense, Expense Category, Expense Report, Recurring Expense,
                        Expense Settings, Allocation Rule, Printing Cost Settings, Printing Machine,
                        Damaged Stock Entry, Damaged Stock Sale,
                        Inter Business Transfer (and its report), Material Issues report;
                        shared rules: treasuries.py (each business's cash box), no_delete.py,
                        period_lock.py (closed months), library_revenue.py, expense_reminders.py,
                        stock_reorder.py (reorder levels), material_issue.py (branch requests),
                        customers.py (one customer per phone), sales_cancellation.py (reason to cancel a sale),
                        edition_sales.py (which edition each copy sold comes from)
  imed_erp/assistant/   AI assistant (chat window; no model connected yet)
  imed_erp/notification_service.py   Unified notifications (CORE-10)
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

This is the **development** setup: `admin` passwords, the site open on every interface, developer mode and tests on.
For the production server, follow [docs/production-hardening.md](docs/production-hardening.md) instead.

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

Going live: the opening stock ([docs/OPENING_STOCK.md](docs/OPENING_STOCK.md)), the daily import's data standard
([docs/IMPORT_DATA_STANDARD.md](docs/IMPORT_DATA_STANDARD.md), sample files in `docs/import/`), and checking two
doctor statements by hand ([docs/DOCTOR_STATEMENT_RECONCILIATION.md](docs/DOCTOR_STATEMENT_RECONCILIATION.md)).

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
| Academic Period | full | read only |
| Doctor Agreement | full | pick one on an edition or subscription only (select); the agreements are not opened |
| Doctor Ledger Entry | full | none |
| Book Edition | full | create, edit (no submit: submitting approves the edition's pricing); Carry Forward and Cancel: Curriculum Changed on their own library's approved editions |
| Printer Reading, App Subscription | full | create, edit, submit (no cancel/delete) |
| Expense | full | create, edit, request approval (no cancel/delete); every expense is submitted only once the accountant approves it |
| Inter Business Transfer | full | Accounts User: read only. Branch Manager: create, edit, submit (no cancel/delete) |
| Expense Category | full | read only |
| Recurring Expense (monthly bills) | full | read only (so the bill can be picked on an expense) |
| Expense Settings | read only (only the owner edits it) | read only |
| Allocation Rule | full | read only |
| Stock Count | full | Branch Manager: create, edit, submit, own branch's stores only (no cancel/delete) |
| Printing Machine | full (Super Admin, Stock Manager; Stock Request Approver can add and edit) | read only (Stock User, Branch Manager) |

"Full" never includes delete: on every one of these only the owner deletes, and only a draft that was never
posted (owner's decision of 7 Oct 2026; `verify_users.py` checks it).

Branch managers also have Accounts User (to create sales invoices), so both roles get the same rights
here, except on Inter Business Transfer, which Branch Manager may send. Agreements, the doctors' ledger and edition pricing are approved by Accounts Manager (Owner,
Accountant), as in the permissions matrix.

Academic Periods form a tree: a **Round** belongs to a **Term** and a **Module** to a **Round**
(field *Parent Period*), and each period must fall inside its parent's dates.

**Document numbers.** The app's doctypes are named with dot naming series, e.g. `EXP-.YYYY.-.#####` or
`REC-.####`, which keep one counter per prefix. Do not use `format:EXP-{YYYY}-{#####}`: Frappe parses each
braced part on its own, so every `format:` name with `{#...}` shares a single counter with an empty key,
and expense numbers would jump whenever a bill or a rule is made.

## Roles and the permissions matrix (requirements §3.2)

| Requirement role | Users | ERPNext roles it comes with |
|---|---|---|
| Super Admin | Owner | System Manager, Accounts Manager, Expense Approver |
| Accountant | Accountant | Accounts User, Accounts Manager, Expense Approver |
| Branch Manager | Nour, Gilan, Menna, Raghad, Sara | Sales User, Accounts User (+ Stock User for the libraries) |
| HR | HR | HR Manager |
| CRM Staff | nobody yet | none yet (the CRM module is not built) |

`setup_users.py` applies the matrix rows that exist in the system today:

- Only Super Admin and Accountant can **cancel or amend** a financial document (sales / purchase / POS
  invoice, payment, journal entry, stock entry, delivery note, purchase receipt, stock reconciliation).
  Branch managers can create, edit drafts and submit them.
- **Nothing posted is ever deleted (ACC-07, owner's decision of 7 Oct 2026).** A mistake is cancelled,
  which reverses it and keeps it on record. `imederp/no_delete.py` refuses to delete any submitted or
  cancelled financial document, ERPNext's or the app's, for everyone. Only the owner may delete, and only
  a draft that was never posted; the accountant has every other right.
- Branch managers make no journal entries, pay no purchase on the spot and record no payment out: money
  paid out is an Expense the accountant approves (owner's decision of 12 Oct 2026). They still take payments
  in. They only read month-end closing (Accounting Period), the chart of accounts and the split of the shared
  premises' expenses (Cost Center Allocation), which ERPNext's Accounts User could otherwise change.
  The accountant changes these three but never deletes them; only the owner does.
- A branch manager's expenses, transfers, payments in and a sale's money at the counter (Sales / POS
  Invoice) go only through their own business's cash box or the group's InstaPay / Vodafone Cash wallets
  (`imederp/treasuries.py`); Owner and Accountant may use any.
- Branch managers see only their own cost center (and warehouse); Owner and Accountant see all.
- The owner reads every record of the Accounts, Stock, Selling, Buying, Setup and ImedERP modules
  (`setup_users.py` adds read, report, print and export where his role had none; `verify_users.py` checks it).
- Employees: Super Admin and HR manage them, Accountant can view them.
- Prices (Item Price): only the owner edits them. The accountant's price changes need approval (SEC-02),
  not built yet. Customers: the owner, the accountant and branch managers add them.

**Expense Approver** is not a requirement role but a marker the code checks: its holders approve or
reject expenses (EXP-06). The accountant has it, since expenses are paid out of his cash (owner's decision
of 12 Oct 2026), and the owner keeps it.

Rows for modules not built yet (bookings, integrations, price approval) are listed by `verify_users.py` as
not checked. The AI assistant is limited to the owner on the server (`assistant/api.py`).

## Notifications (CORE-10)

`imed_erp/notification_service.py` is the one entry point every module uses to notify people (the expense
reminders and approval notices included):

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
| `css/imed_theme.css` | The desk theme: colour, type and shape tokens (light and dark), then sidebar, page head, buttons, inputs, forms, lists, dashboards, home screen, dialogs, toasts, empty states, small screens, and airy forms (§19: one calm spacing rhythm on every form). |
| `css/imed_web.css` | The login page only (every rule is scoped to `#page-login`). |
| `js/imed_home.js` | Home screen: a greeting band (greeting, today's date, company) with quick actions, each shown only if the user has the permission for it. Hooks into Frappe's `desktop_screen` event and only adds elements; the app grid and its edit mode are Frappe's own. |
| `js/imed_theme_toggle.js` | One-click light / dark switch next to the notifications (beside the bell on the home screen, under "Notification" in the sidebar). Uses Frappe's own theme setting, so the choice is saved to the user. |
| `css/imed_fonts.css`, `fonts/` | IBM Plex Sans Arabic (SIL OFL, licence in `fonts/OFL.txt`), bundled so it works without internet. Only Arabic text uses it; Latin stays on Inter. |
| `js/imed_form_standard.js` | Reusable screen design standard (`imed.screen.apply`): hide unused standard-ERPNext fields (tax / ZATCA / international), collapse technical sections. Each doctype's own `.js` calls it. See [docs/SCREEN_DESIGN_STANDARD.md](docs/SCREEN_DESIGN_STANDARD.md). |
| `images/imed-mark.svg` | Logo and favicon. |
| `icons/desktop_icons/{solid,subtle}/owner_dashboard.svg` | The Owner Dashboard icon on the home screen. |

- **Colours:** teal (`--imed-teal-600` = `#0f766e`) is the primary colour, amber is a rare accent. On the
  dashboard, colour has a meaning: teal = income, amber = needs attention, slate = neutral counts. To change
  the brand colour, change the `--imed-teal-*` scale at the top of `imed_theme.css`.
- **Arabic / RTL:** every left/right spacing uses logical properties (`inline-start` / `inline-end`), so the
  Arabic interface mirrors correctly.
- **Dark mode** (user menu > Toggle Theme) is fully themed.
- **New screens:** follow [docs/SCREEN_DESIGN_STANDARD.md](docs/SCREEN_DESIGN_STANDARD.md) — field order,
  which fields to hide, Arabic/RTL, fonts, buttons, status colours, and the reusable Client Script helper.
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
(`setup_regional.py`). Account, item, cost center and warehouse names are in Arabic
(`setup_arabic_names.py`); only the company, the `All Item Groups` root and the `Nos` UOM stay in English.

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
- It is also the **receipt** of a sale at the point of sale (SEC-06): the library POS Profiles name no print
  format, so Print Receipt uses this default. For a sale at the counter it adds how it was paid (each payment
  method and its amount) and the change given (الباقي للعميل).


Notification templates (`notification_service.py` `EVENTS`) are translated before they are filled in, so
alerts such as reorder levels reach Arabic users in Arabic. Some of ERPNext's own Arabic is wrong and is
corrected in `translations/ar.csv` with the same meaning: `Draft` (مسودة, not «مشروع»), `In Stock`, `Stock UOM`,
`Request Type`, `Due Date`, `Age (Days)`.

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
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_buying.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_expenses.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_recurring_expenses.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_allocation_rules.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_platform_fees.py").read(), {"frappe": frappe})
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
| `setup_core.py` | Run first. On a new site it completes the setup wizard (company MMG, EGP, fiscal year Sep–Aug). Then: cost center tree, warehouses (Mawasah, the main one, with its raw materials, doctors' editions and damaged stock; Azarita's raw materials and editions as a separate branch; the center's office supplies), UOMs (`ورقة` sheet, `رزمة` ream = 500 sheets, `كرتونة` box = 5 reams = 2500 sheets, `ساعة` hour) and items. Paper (item group `ورق`) is stocked in sheets, bought by the box and valued at moving average (see *Paper units and cost* below); the hall and studio hours are sold by the hour. Runs `setup_coa.py` itself, after the warehouses. The customer group `طبيب`: a doctor is a Customer in it (CRM-01). |
| `setup_regional.py` | Regional settings: EGP currency (symbol `EGP`, 2 decimals), fiscal years 2026-2027 and 2027-2028 (1 Sep – 31 Aug, linked to the company; a wrongly dated year with nothing posted in it, e.g. the Jul–Jun one the browser wizard creates, is replaced), Arabic interface for users / English for Administrator, rounded totals off, MMG Sales Invoice as the default invoice print format, date format `dd-mm-yyyy`, 24-hour time, number format `1,234,567.89`, commercial (half-up) rounding, week starting Saturday. |
| `setup_users.py` | The requirement roles (Super Admin, Accountant, Branch Manager, HR, CRM Staff) and the Expense Approver role, 8 users (`name@imed.local`), User Permissions that restrict each branch manager to their own cost center and warehouse, and the permissions matrix (requirements §3.2) on financial documents. Declarative: re-running also corrects drift (name, enabled flag, extra roles, stale User Permissions). Prints a summary table. |
| `setup_arabic_names.py` | Renames the company's accounts, cost centers, warehouses, item groups, UOMs (Ream, Box) and item names from English to Arabic, updating every link. `setup_core.py` runs it right after the company exists. Leaves the company name, the `All Item Groups` root and the `Nos` UOM in English (ERPNext uses them by name). Screen texts of the app's own doctypes and reports are translated in `imed_erp/translations/ar.csv`. |
| `setup_coa.py` | Chart of accounts from the posting rules document (v2.0, section 2): treasuries (one per business, including the BA Plus app's), one revenue account per business, costs and expenses, doctors' and lecturers' balances, the inter business current account, and one stock account per library and kind, linked to its warehouse. Reuses the accounts ERPNext already ships (rent, salaries, utilities, ...) and deletes the old Books / Printing Revenue accounts. Can also be run on its own. |
| `setup_library.py` | Libraries (LIB). The five inventory groups `ورق`, `أحبار`, `كتب وكشاكيل`, `مستهلكات` (ERPNext's own Consumable group) and `خامات تجليد`, with A4 paper in `ورق`; makes `منتجات المكتبات` a parent group with `كتب وكشاكيل` (holding `كتب` and `مذكرات`) and `خدمات المكتبات` under it; the Author field on Item; the non-stock services COPY-SVC, PRINT-SVC, BINDING-SVC (moved into `خدمات المكتبات`); the stock items BOOK and MEMO; item defaults (revenue `إيراد مكتبة المواساة`, cost center `مكتبة المواساة`, warehouse `إصدارات الأطباء — المواساة`); one POS Profile per library, which gives each sale its own warehouse and cost center; a cash payment method for the halls, the studio and the app, each into its own cash box; the stock count fields on Stock Reconciliation, Count Type and Counted By (LIB-03). The libraries' seven printing machines (PRN-01): `Epson الأزاريطة`, `Riso الأزاريطة 1-2`, `Epson المواساة`, `Riso المواساة 1-3`, each with its library, type and location warehouse; a machine already there is kept (an older one only gets its missing library and type). Each run says `ASSUME` while the Epson and Riso ink costs on Printing Cost Settings are still the assumed 0.05 and 0.10. Books and memos are listed in `LIBRARY_ITEMS` at the top (one generic item each until the catalogue is known). Creates no account, cost center or warehouse: a missing one is printed as `WAIT`. Idempotent. |
| `check_opening_stock.py` | Opening stock (INT-08). Checks the libraries' count sheet (`setup/data/opening_stock.csv`, from `opening_stock_template.csv`) row by row and prints the total per store; with `MAKE_DRAFTS = True` and no errors, makes one **draft** Stock Reconciliation (Opening Stock) per branch, for the owner or the accountant to submit. Never submits, never posts twice to a store. See [docs/OPENING_STOCK.md](docs/OPENING_STOCK.md). |
| `setup_customer_phones.py` | One customer per phone number (CRM-04). Run once after `bench migrate` added the Phone Key field: gives each customer saved before it the key of its number, so a new customer with the same number is refused. Changes no phone number and merges nothing: invalid numbers and numbers already on several customers are listed (the oldest customer of a number gets its key). `FILL = False` only prints the report. Idempotent. |
| `setup_dashboard.py` | Number Cards, Dashboard Charts and the Owner Dashboard workspace (deleted and recreated each run), in the theme's colours; they count only submitted documents (and enabled customers), never drafts, plus the branding settings the theme needs: app name, logo (Navbar Settings), launcher icon style, Owner Dashboard icon. The owner follows everything himself and mostly confirms (owner, 12 Oct 2026), so the dashboard is his home page (`default_workspace`), with Arabic section headers: what waits for him first, with counts (expenses waiting for approval, editions to approve, transfers to confirm), then the key numbers and charts, one click to every list of the staff's work (sales, expenses, purchases, counts, stock movements, branch requests, agreements, editions, counters, subscriptions, and All Changes, Frappe's change history), then the reports. |
| `verify_setup.py` | Read-only. Prints found/expected counts and flags anything missing or misconfigured. |
| `verify_users.py` | Read-only. For every `@imed.local` user: their restrictions, the cost centers they can see, and yes/no for each right in the permissions matrix, marked PASS/FAIL against the matrix. |
| `check_financial.py` | Test, rolled back afterwards. Checks EGP on the company and Global Defaults, the fiscal year, `dd-mm-yyyy` dates, number format, that a printed invoice (HTML and PDF) shows `EGP` and not `£`, and that a closed accounting period blocks invoices and journal entries (CORE-09). |
| `check_doctor_accounts.py` | Read-only. Every submitted doctor ledger entry has its posted journal entry for its own amount, each agreement's Balance equals its entries, and no charge for unsold copies is waiting or applied (owner, 21 Oct 2026). Lists what differs; changes nothing. |
| `check_library.py` | Test, rolled back afterwards. Creates a test book and memo, receives them in Mawasah's store, issues books to Azarita, then sells through each library's POS Profile and through a plain sales invoice, and checks that the revenue account (Azarita's sales moved to `إيراد مكتبة الأزاريطة` by `imederp/library_revenue.py`), cost center and warehouse were filled in without being typed. |
| `setup_expenses.py` | Expense categories (EXP-07): the tree `كل المصروفات` with `الإيجار`, `المرافق`, `الرواتب والأجور`, `الخامات والمستهلكات`, `الصيانة`, `التسويق`, `الهالك والتالف` and `الاشتراكات والسيرفرات` under it, each linked to the expense account of the same name (or the English name ERPNext ships it with, before `setup_arabic_names.py`). The monthly bills sit in two groups: `المرافق` (electricity, water, internet, gas, and rent, which keeps its own account) and `الاشتراكات والسيرفرات` (the app's server and AI subscriptions). Creates no account: a missing one is printed as `WAIT`, and re-running links it once it exists. Idempotent. |
| `setup_recurring_expenses.py` | The first monthly bills (EXP-05): rent, electricity, internet and gas of the center premises with their expected amounts; rent, electricity and internet of each library, and the app's server and AI subscriptions, without amounts. Run after `setup_expenses.py`. Fills the list once; from then on it is kept from the Recurring Expense screen. A bill already listed for the same business is left as is. Idempotent. |
| `setup_allocation_rules.py` | Submits the first allocation rule (EXP-03/04): expenses on the shared premises are split 60% halls / 40% studio from 1 Nov 2026, as agreed with the owner. Later changes are new rules from the Allocation Rule screen. A submitted rule for the same cost center and date is left as is. Idempotent. |
| `setup_platform_fees.py` | Submits the platform fee tiers approved by the owner (APP-02) from 1 Sep 2026: 1–100 students 250, 101–500 200, more than 500 170 a student of a course in a term. Later prices are new schedules from the Platform Fee Schedule screen. A schedule already in force from that date is left as is. Idempotent. |
| `setup_booking_prices.py` | The studio's price list from the requirements (v1.2, 4.8): service items and their Item Prices (Standard Selling), the resources (smart boards, reels, podcast, location), the packages and the extras (microphone, lights: 50 a piece an hour). A price already set is never changed. |
| `setup_buying.py` | Buying (LIB-07, ACC-12): the supplier group `موردي الورق والخامات` and the payment terms a purchase invoice is made on, each a Payment Term and a Payment Terms Template of the same name: `نقدي` (due the same day) and `آجل 30 يوم` (due in 30 days). Buying Settings: no purchase order or purchase receipt required first, since the library buys directly; one purchase invoice with **Update Stock** ticked receives the paper and records what is owed. The purchase invoice screen (`public/js/purchase_invoice.js`) shows only what a purchase needs; Update Stock is ticked on a new invoice and the unit is a column of the items table (Property Setters). What exists is left as is. Idempotent. |
| `close_period.py` | Month-end close (CORE-09). Creates an Accounting Period for a finished month with ERPNext's posting document types and the app's own (Expense, Inter Business Transfer, Doctor Ledger Entry, App Subscription, Printer Reading, Stock Count, listed in `period_closing_doctypes` in `hooks.py` and checked by `imederp/period_lock.py`, on save and on cancel; a doctor's ledger has no company and uses the default one) closed, so nothing dated in that month can be posted, edited or cancelled. Set `MONTH = "YYYY-MM"` at the top, or leave it empty for last month. Run it only at month end: it changes the books. |

`setup_core.py`, `setup_regional.py`, `setup_arabic_names.py`, `setup_coa.py`, `setup_users.py`, `setup_buying.py`, `setup_expenses.py`, `setup_recurring_expenses.py`, `setup_allocation_rules.py`, `setup_platform_fees.py`, `setup_booking_prices.py`, `verify_setup.py` and `verify_users.py` are idempotent, so they can be re-run
safely. They only ever touch the company `Mohamed Mamdouh group` (abbreviation `MMG`), which is
hardcoded; the demo company `Mohamed Mamdouh group (Demo)` is left alone.

### Expenses (EXP-01/02, EXP-07)

An **Expense** records one payment: Activity (a leaf cost center), whether it **Repeats** (*This Month
Only* or *Every Month*), Expense Category, Expense Amount, Treasury (a leaf cash or wallet
account), Supplier (optional: salaries have none) and Receipt Attachment. Monthly expenses are covered in
the next section. A draft can be saved without the receipt, but submitting is refused until one is
attached. The check is in the controller's `before_submit`, so it also holds for the API; the receipt
must be an uploaded image or PDF. Submitting posts a journal entry: debit the category's expense
account, credit the treasury, both on the activity's cost center. Cancelling the expense reverses it;
the journal entry itself cannot be cancelled on its own, or the report would still count money that is
back in the treasury.

**Expense Category** is a tree (ImedERP > Expense Categories > Tree view). Expenses are recorded on the
categories inside a group, not on the group. A category without its own expense account is posted to its
nearest parent's, so a sub-category such as `كهرباء` under `المرافق` needs no account of its own.
A group with categories under it cannot be turned back into a category, and a category that already has
expenses cannot become a group.

The ImedERP sidebar (`workspace_sidebar/imederp.json`) lists every screen of the app. Without it Frappe
builds its own, which shows only the first three doctypes of the module.

The **Expense Report** lists submitted expenses filtered by period, activity, category, supplier and
treasury. Choosing a group activity (e.g. `مكتبات 2Be Doctor`) or a group category includes everything
under it. **Group Totals By** gives one total per category, activity, month, or their combinations.

### Monthly bills and reminders (EXP-05)

A **Recurring Expense** is one bill paid every month by one business: rent, electricity, the app's
server... It holds the business, the expense category, the treasury it is paid from, the day of the
month it is due (in a shorter month, its last day) and the **Next Due Date**. The owner and the
accountant keep the list themselves (ImedERP > Recurring Expense): change an amount or a day, add a
bill, or untick **Enabled** when one stops. A bill is checked against the same rules as an expense when
it is saved, so a wrong treasury or a group category is refused there, not a month later.

The **Expected Amount** is optional and decides how the bill is paid:

| Expected Amount | What happens on the due date |
|---|---|
| Set (e.g. the center's rent, 46,000) | A **draft Expense** is made with it. Someone enters the actual amount, attaches that month's receipt and submits it. Changing the amount on the bill changes the months to come. |
| Empty (e.g. the libraries' bills) | Nothing is made. The accountant records the expense himself. |

Either way the Next Due Date moves on one month. If the scheduler did not run for a while, one draft is
made for each month missed. A bill switched back on, or given a new day of the month, starts from this
month (next month if this month already has an expense on it), so it makes no drafts for the months it
was off and never two for the same month. A category with monthly bills on it cannot become a group.

On the Expense form, **Every Month** shows **Monthly Bill**, which lists only the bills of the business
chosen above it; picking one fills in the category and the treasury (and the expected amount, if the
amount is still empty). A monthly expense whose bill is not listed yet is filled in by hand, and is
added to that business's bills when it is submitted (due on the same day of the month, from the month
after the expense), so it can be picked next month. A bill of one business cannot be used on another business's expense.

**Reminders** go to the owner and the accountant (users with Accounts Manager, except Administrator)
as in-app alerts, which never send e-mail:

- a set number of days before a bill's next due date (**Remind Days Before**, default 3);
- while a draft made from a bill is still unsubmitted after its date, again every few days (**Repeat
  Overdue Reminder Every (Days)**, default 2). A rejected draft is not reminded; one waiting for
  approval reminds the accountant, who approves it, instead, on the same days.

Both numbers are in **Expense Settings**. The drafts and the reminders come from one daily scheduler
job, `recurring_expense.run_daily` (`hooks.py`), so the month's drafts exist before the reminders look
for them. Reminders and approval notices go through `notification_service.py` (CORE-10), which also
skips a notification a user already has for the same document, so a second run the same day adds nothing.

### Expense approval (EXP-06)

**Every expense** is paid and posted only once the accountant approves it, whatever its amount: the money
comes out of his cash (owner's decision of 12 Oct 2026, replacing the owner's own approval of 8 Oct). The
owner can approve too. There is no threshold, and Expense Settings (reminder days) can be changed by the
owner only, so nobody else can switch the approval off.

1. A branch manager saves the expense with its receipt and clicks **Request Approval** (Submit is refused
   while the expense needs approval). The accountant receives an in-app alert; the owner is not notified
   of each request but can approve one he opens.
2. The accountant opens it and clicks **Approve**, which submits and posts it, or **Reject**, with an optional
   reason. The person who asked for the approval is notified either way (not the creator: monthly
   drafts are made by the scheduler).
3. A rejected expense is closed for good: it can no longer be saved or submitted. If the payment is
   needed after all, a new expense is made.

Changing the amount, category, business, treasury, date or receipt after a request or an approval clears
it, so the expense as changed needs approval again. Each request carries the time it was sent, so a request
sent again after a change reaches the approver as a new alert.
The accountant's and the owner's own expenses are approved as they submit them. Approval is by the
**Expense Approver** role, checked on the server. The approval fields change only through Request
Approval, Approve and Reject: a save that writes them otherwise, through the API too, is refused, and an
expense made with an approval already on it (a copy, an amendment) starts without one. The form shows the
status (*Pending Approval*, *Approved*, *Rejected*), who decided and the rejection reason.

### Splitting the shared premises' expenses (EXP-03/04)

The halls and the studio share one building, so its rent, electricity, internet and gas are recorded on
the shared cost center `مصروفات المقر المشتركة`. An **Allocation Rule** says how those expenses are
split between the businesses from a given date:

| Field | Example |
|---|---|
| Shared Cost Center | `مصروفات المقر المشتركة` |
| Valid From | 1 Nov 2026 |
| Businesses | `قاعات Imed` 60%, `استوديو X` 40% (must add up to 100%) |
| Notes | Why these shares and who agreed to them |

Submitting the rule makes an ERPNext **Cost Center Allocation** with the same shares and date, and from
then on ERPNext splits every entry posted on the shared cost center as it is posted: a 10,000 electricity
bill becomes 6,000 on the halls and 4,000 on the studio, on both the expense and the treasury side. The
accountant records expenses as before. A bill paid in several parts is split part by part, which adds up
to the same shares.

- **Changing the shares** is a new rule with a later Valid From, never an edit: a submitted rule is
  locked. Past expenses keep the split they were posted with.
- **Valid From** must come after the last expense on the shared cost center and after the latest rule's
  start, so a rule never reaches back over posted months. (ERPNext's own check looks at the ledger only,
  which no longer shows the shared cost center once an expense is split; the rule checks the expenses.)
- **Cancelling a rule** cancels its allocation. Expenses already split keep their split; later ones follow
  the previous rule again, or stay on the shared cost center if there is none.
- The shared cost center cannot be one of its own businesses, and a business cannot be a group (ERPNext
  refuses both).

The split shows in the ledger and in profit and loss by cost center. The **Expense Report** reads the
expenses themselves, so it still shows them on the shared cost center.

Shares are fixed percentages. Shares worked out from each business's area or revenue, also listed in the
task, were left out on purpose: the owner chose a fixed 60/40 (8 halls, 4 of which also serve as the
studio part of the time), and the rule's Notes record what the shares are based on.

### Cash boxes: balances, the daily close and the weekly review (ACC-03)

Rules confirmed by the owner on 21 Oct 2026.

- **A cash box never goes below zero** (`imederp/cash_balance.py`, every document that posts to the ledger): an
  expense, a transfer, a payout, a cash refund or any payment of more than the box holds is refused, on any day from
  its date to today; cancelling cash that came in is checked too. The box's account is locked and its ledger read
  with locking reads, so two payments at once cannot spend the same money. Wallets (bank accounts) are not checked.
  Balances already below zero are not changed; the next payment out of such a box is refused until the money that
  came in is recorded. A POS Invoice posts to the ledger only when it is consolidated, so it is checked then.
- **Treasury Balances** (report): each cash box and wallet on a date, from the ledger.
- **Treasury Close** (`doctype/treasury_close`): the branch manager closes her own branch's cash box at the end of
  the day; no daily approval.
  - Opening = the cash counted at the box's last close (the ledger's balance before the day for its first close).
  - Since the last close, from the ledger: Collections, Transfers In, Expenses and Payouts (expenses and doctors'
    payouts), Transfers Out, Refunds and Other Payments. Expected Closing = Opening + in - out.
  - Shortage (-) / Surplus (+) = Cash Counted - Expected Closing. Balance in the Books shows the ledger beside it.
  - Once a day per box, and in order (no close for a day before the box's last one). Closed By, Closed On, Shift,
    Note and Evidence are kept.
  - It posts nothing and changes no ledger line. A difference opens a **Cash Discrepancy**.
  - A cash entry dated into a closed day is refused to a branch manager; the accountant's is accepted, and the
    closes it changes are marked Needs Review.
  - **Reopen** (owner and accountant only, with a reason): the close is cancelled and kept with its figures, who
    reopened it, when and why; a new draft amends it. Its discrepancy is withdrawn; later closes of the box and any
    reviewed week holding it are marked for review. Refused once its discrepancy is adjusted in the books or has an
    approved recovery (undo those first). Branch managers cannot reopen or cancel.
- **Cash Discrepancy** (`doctype/cash_discrepancy`): the accountant investigates; the owner sees all; a branch
  manager reads her branch's and decides nothing.
  - Shortage: Pending Investigation -> Responsibility Determined (notes written, responsible employees marked) ->
    Recovery Recommended by the accountant (each responsible employee told and heard, the recovery checked against
    the contract and the labour law, an amount typed for each; not more than the shortage) -> Recovery Approved by
    the owner (four eyes: never by whoever recommended it; the owner may return it with a reason), or Written Off
    (the company bears it). Nothing is split between employees by itself; nobody is responsible for having been on
    shift.
  - **Recovery is blocked** until the owner ticks *Recovery Policy Approved* in **Cash Close Settings**, naming the
    written policy checked by a lawyer or HR; until then nothing can be approved.
  - Surplus: Pending Review -> Explained, only with where the cash came from. Until then it stays under review: in
    the open count, the report's Still Open Only and every later weekly review. Never revenue by itself.
  - Post Adjustment (accountant, once, after it is settled): a journal entry dated today between the box and
    فروقات الخزينة, so the books match the cash counted. The next close leaves it out (its opening is already the
    count).
  - **No salary is deducted by the system** (there is no payroll). An approved recovery is listed in the report
    **Cash Discrepancies -> Payroll Review** for the accountant to take to payroll by hand.
- **Weekly Cash Reconciliation** (`doctype/weekly_cash_reconciliation`, accountant and owner): one per week and
  business (or all businesses). Lists every close of the week with its figures, the discrepancy's status and who
  was found responsible; the week's shortages and surpluses; open discrepancies; days a box was not closed.
  Discrepancies of earlier weeks still open are listed apart (Still Open from Earlier Weeks), not added to this
  week's totals: each difference counts once, in its own week, and stays visible until settled. The next close
  never repeats a difference: its opening is the cash counted. Submitting it marks the week reviewed (a note is
  required while any discrepancy is open). It moves no money: it does not assume the cash went to the accountant.
  The week runs Saturday to Thursday (owner, 21 Oct 2026; Cash Close Settings, *Reporting Week Starts On* and
  *Ends On*): Friday is off, a close made on a Friday still shows in its week, and a Friday is never listed as a
  day without a close.
- **Opening cash** on a new site: `imederp/opening_cash.py` checks every treasury and prepares the counted cash as
  a draft opening entry (docs/production-hardening.md, section 7).
- Owner's page: Cash Shortages This Month, Open Cash Discrepancies, and shortcuts to the closes, the discrepancies
  waiting, the weekly reviews and the report.

### The weekly cash hand-over (ACC-09)

**Cash Handover**: at the end of the week (or whenever cash is needed) the branch manager records the cash she hands
to the owner or the accountant and submits it (Pending Receipt): never more than the box holds less what is already
pending, under a lock on the box; part of the cash may be handed over. She prints **Cash Handover Receipt** (Arabic,
the amount in figures and in words, a space to sign). The receiver signs the paper by hand (no electronic
signature), attaches its scan or photo to the hand-over (Signed Receipt: a private PDF or photo of this hand-over,
not used for another) and clicks **Confirm Receipt** with the cash counted. Only the receiver named confirms. Then
one entry: Dr the receiver's custody account (Cash Close Settings: عهدة المالك النقدية / عهدة المحاسب النقدية) / Cr
the branch's box, dated the hand-over day. The day's close counts it as Handed Over, pending or confirmed, and the
week's review lists every hand-over with its receiver, status and whether the signed receipt is there. Cancel with
Reason keeps the record (a pending one: whoever recorded it or the accountant; a confirmed one: the accountant or
the owner, reversing its entry). Set the custody accounts in Cash Close Settings before the first confirmation.

### BA Plus payments (App Payment)

What a student pays BA Plus for a course: **Cash** into the collecting branch's own box (it is then one of the box's
collections, in its daily close), or **electronically** (bank transfer, InstaPay, Vodafone Cash) into the app's bank
account or a wallet, with the transfer's reference number (once per account). Each payment posts Dr the box or
account / Cr مقبوضات الطلبة لحساب الأطباء — التطبيق: the course is the doctor's (APP-05), never the group's revenue,
and the platform fee is unchanged. **App Payments** lists them, with what is not yet matched with the statement
(ERPNext's Bank Clearance dates an electronic payment's entry). `app_payment.import_payment` takes a payment from
BA Plus once per its id there, for the integration to come. Cancelling is the accountant's, with a reason.

### Printer counters read twice a day (PRN-01)

The day's counters (Daily Counter Reading) are read in the **morning** (type each machine's counter, Save: who and
when is kept; a branch manager cannot change them afterwards) and in the **evening** (type each closing, Submit).
Each machine's last closing is shown beside the morning reading; a morning reading above it is a **gap** (sheets
printed while nobody read the counter) and needs its reason, one below it is refused (a reset is the accountant's
Counter Reset). A day waiting for its evening readings blocks the next. The screen and **Daily Printing** show
printed, sold, paper issued for sales, damaged sheets and the gap apart; the counters move no stock.

### Prepaid studio hours (Studio Hour Package)

A teacher buys hours of a studio service (30 hours for a price); **Make Invoice** bills the package once. A booking
names the package (Prepaid Hours): its exact length comes off it while it holds its time, and its own price is 0, so
the session is never billed again. Moved, shortened or cancelled, the difference is given back; each change is a row
of the package's history. Never below zero: a session longer than the hours left is refused unless the accountant
or the owner ticks Bill the Hours Beyond the Package, which bills only those hours at the hourly price. There are no
fixed studio hours; two bookings of one resource still never overlap.

### The demo site

A separate site, **demo** (http://127.0.0.1:8081 on the development machine, container `imed-demo-web`), holds the
demo transactions of 18 Oct restored from the backup of 21 Oct, plus sample cash closes, discrepancies and a
weekly review made by `setup/seed_cash_demo.py`, and on 22 Oct BA Plus payments, counters read twice, a prepaid
studio package and hand-overs by `setup/seed_demo_22oct.py` (both refuse any other site). Every sample record says (تجريبي).
It is for looking at the screens; the development site and the tests do not depend on it, and production starts
from a clean site. Its staff accounts have a demo-only password.

### Dates

No completed transaction is dated after today, for anyone, through the form or the API (`imederp/dates.py`, owner
21 Oct 2026): expenses, transfers, doctor ledger entries (payouts, collections, adjustments), counter readings, stock
counts, damaged stock and its sale, app subscriptions, treasury closes, and ERPNext's invoices, payments, journal and
stock entries. What is planned keeps its future date: bookings, a monthly bill's next date, an allocation rule's or
a fee schedule's Valid From, academic periods. A date must also fall in one of the company's own fiscal years
(2026-2027 from 1 Sep 2026); the `_Test Fiscal Year`s the October test runs left on the development site name no
company and are not used for the group.

### Users

A user is disabled (untick Enabled), never deleted (CORE-07; `imederp/users.py`): their name stays on what they
recorded. Only the developers' account, Administrator, may remove an account made by mistake.

### Paper units and cost

Paper is bought by the box, used by the sheet and stocked in sheets. **Paper Balance** (report, PRN-04) shows each
store's paper in sheets and as boxes + reams + loose sheets (11,030 = 4 boxes, 2 reams, 30 sheets):

| UOM | Sheets |
|---|---|
| `ورقة` (sheet, whole numbers only) | 1 (stock UOM) |
| `رزمة` (ream, whole numbers only) | 500 |
| `كرتونة` (box, whole numbers only) | 2,500 (default purchase UOM) |

None of the three is split, so ERPNext's reorder rounds up: a shortfall of 2,000 sheets asks for one box,
not 0.8.

Every item in the item group `ورق` is valued at **moving average** and bought by the
box; `setup_core.py` applies both to any paper item added to the group later. Moving average means every
sheet in a store costs the same, the average of what was paid: a box at 650 then one at 700 make every
sheet 0.27. Two boxes at 650 come in as 5,000 sheets at 0.26 each, 1,300 in all.

A purchase takes the conversion factor from the item. If the item has no row for the chosen UOM, ERPNext
uses a factor of 1 and a box comes in as one sheet. ERPNext also **empties the item's UOM table whenever
its stock UOM changes**, so `setup_core.py` puts the factors back on every run (`ensure_conversions`), and
`verify_setup.py` reports a missing or wrong one. ERPNext refuses to change the stock UOM or the
valuation method once stock has moved; the script then only warns.

### Buying from suppliers (LIB-07, ACC-12)

The accountant buys paper and materials from suppliers, paid on the spot or on credit, with ERPNext's
own Supplier, Purchase Invoice, Payment Entry and payables reports; `setup_buying.py` sets them up.

1. **Supplier**, in the group `موردي الورق والخامات`.
2. **Purchase Invoice**, with no purchase order or receipt before it: the library buys directly.
   **Update Stock** is ticked on a new invoice, so the one invoice brings the paper into the store and
   records what is owed. Purchases go into the main store, `خامات المواساة`; paper reaches a branch by a
   transfer from it, never by a purchase of its own. Paper is bought by the box (see below). The screen
   (`public/js/purchase_invoice.js`) shows only what a purchase needs: supplier and date, Update Stock
   and the warehouse, the items with their unit, the totals, and the payment terms; the supplier's
   invoice is attached from the sidebar.
3. **Paid on the spot or on credit.** For a purchase paid at once, tick **Is Paid** and choose the
   payment method; the screen fills in its treasury. Otherwise pick the payment terms, `نقدي` (due the same day) or `آجل 30 يوم` (due in
   30 days), and pay later with a **Payment Entry** of type Pay against the invoice. Two boxes at 650 on
   credit leave the supplier owed 1,300; paying 650 from the main treasury leaves 650.
4. **Who pays.** Money paid out is an Expense the accountant approves (owner's decision of 12 Oct 2026,
   `treasuries.block_spending_without_approval`): only the accountant and the owner pay a supplier, on the
   spot (Is Paid) or with a Payment Entry, from any treasury. A branch manager pays no supplier, from her own
   cash box neither. A cash box never goes below zero (`cash_balance.py`).

Shipping is part of what the paper cost. It is added after the purchase with a **Landed Cost Voucher**
on the purchase invoice (or receipt), charged to `مصروفات الشحن والنقل`: two boxes at 650 with 100 for
shipping make every sheet 0.28 instead of 0.26. The voucher credits the shipping account and the
shipping bill, when paid, debits it, so the account nets to zero and the cost sits in the paper.

What is owed to each supplier is ERPNext's **Accounts Payable** (invoice by invoice, with its age) and
**Accounts Payable Summary** (one line per supplier). Both need the company, which they fill in from the
user's default (`Mohamed Mamdouh group`). ERPNext's Arabic for two of their columns is wrong
(`Due Date`, `Age (Days)`); `translations/ar.csv` corrects it.

### Stock counts (LIB-03, PRN-06)

The library counts every day and the consumables (paper, ink) every 7-15 days, on the app's **Stock Count**
screen (`imederp/doctype/stock_count`): one store, the date, Count Type (`Daily` or `Periodic
(Consumables)`), Counted By (whoever makes the count, by default) and every item counted with its counted
quantity. **Get Items in Store** lists every item the store holds, with its recorded quantity, for a full
count; the recorded quantity also shows as soon as an item is picked, and the difference as soon as the
counted quantity is typed. Counted Qty is left empty and a count with an empty one is refused (0 is typed
when there is none), so an item forgotten is not taken for a shortage of all of it. On save the server
works out the recorded quantity, the difference and its value at the store's moving average again; the
branch is the store's.

- **Every count is kept**, with or without a difference, so the owner sees that a branch counted and who
  did. ERPNext's own Stock Reconciliation cannot be that record: it drops the rows with no difference and
  refuses a count where everything matched.
- **On submit**, the count makes a Stock Reconciliation for the rows with a difference, in the system's
  name (Counted By keeps who counted). ERPNext posts the shortage or surplus to the company's Stock
  Adjustment Account, `فروقات الجرد`, on the branch's cost center (Mawasah's or Azarita's library, from the
  store; otherwise ERPNext would use the head office). 4,900 sheets counted where 5,000 are recorded is a
  shortage of 100 sheets, 26 at 0.26 a sheet, a loss on the library; a surplus is posted the other way round.
  That reconciliation is cancelled only by cancelling the count.
- **Who:** branch managers create and submit counts of their own branch's stores only (their cost center
  in User Permission); the owner and the accountant count any store and cancel a count. A branch manager's
  count is dated when it is first saved (later saves keep that moment, so fixing a typo after sales does not
  make a false difference), and one saved on another day is counted again; only the owner and the
  accountant date a count in the past, since its reconciliation reposts every stock entry after that date. A posted count is
  never deleted, and none is saved or cancelled in a closed month.

**Services have no warehouse.** Printing, copying, binding, hall and studio hours are not stock, so
`imederp/services.py` clears the warehouse ERPNext puts on their Sales / POS Invoice rows anyway. Without it, a
branch manager's desk invoice for a service was refused for a store outside her branch.

**Paper used for printing and copying** (`imederp/paper_use.py`, owner's decision of 12 Oct 2026):
printing and copying are services, so selling them took no paper out of stock and the next count showed the
sheets used as a shortage. Now a submitted Sales Invoice (a POS shift reaches it as the closing invoice)
issues one sheet of A4 per unit of `PRINT-SVC` and `COPY-SVC` from the library's raw materials store
(`خامات المواساة` / `خامات الأزاريطة`), as a Material Issue linked by its Sales Invoice field, to cost of goods
sold on the library's cost center. If the store shows fewer sheets than were sold, the sale stands and the
issue is saved as a draft, not tied to the sale's time, and the accountant is notified; once the missing
paper is received he submits it as it is. Cancelling the sale (the form's Cancel too) cancels the issue or
removes the draft; the issue is never cancelled on its own. A return does not bring printed paper back. The
issue is posted in the system's name (`imederp/system_user.py`), which keeps the cashier's own session.

**Stock Count Variance** (report): every item on the submitted counts of a period, with its branch and
store, recorded and counted quantity, difference in quantity and value, count type, who counted and the
date. Filters: dates, branch (a group stands for every branch under it), store, count type, who counted,
and Only Differences; untick it to see the counts that found nothing too. The summary gives the number of
counts, the items with a difference, and the shortage, surplus and net values. A branch manager sees only
their own branch.

The Stock Reconciliation screen is still there for the owner and the accountant, for the opening balance
and corrections. It carries the same two fields (`setup_library.py`, `imederp/stock_count.py`), with a third
count type, `Opening`: an opening count is ERPNext's purpose `Opening Stock`, which posts to a temporary
opening account, and only that. One reconciliation covers one branch's stores, and its cost center is set
from them whatever was typed.

### Damaged stock and its sale by weight (LIB-09, PRN-07, DOC-19)

Requirements v1.2: damaged stock is recorded with its quantity and reason and taken off the balance, and its
sale by weight is recorded as revenue (LIB-09, PRN-07); copies damaged in storage are **a loss on the library,
never charged to the doctor** (DOC-19). The libraries take no customer returns: only damaged stock is sold,
by weight. Decided with the owner's representative on 12 Oct 2026: the loss is taken when the damage is
recorded; the branch manager records and submits it; Azarita's damaged stock goes to the damaged store at
Mawasah, its loss stays Azarita's.

**Damaged Stock Entry** (ImedERP > Damaged Stock): Damage Date, the store the items were damaged in, the
Damage Reason, Responsible (whoever records it, by default), and the items with their quantity in the item's
own unit (sheets, copies). Each item's stock and cost show as soon as it is picked. On submit, in the
system's name (`imederp/damaged_stock.py`):

1. a **Material Issue** takes the items out of their store at their moving-average cost, posted to
   `الهالك والتالف` on the store's library (Mawasah's or Azarita's): 1,000 sheets at 0.26 is a loss of 260.
   No Doctor Ledger Entry is ever made;
2. a **Material Receipt** puts the same quantity into the store ticked **Damaged Store**, `التالف — المواساة`,
   at **zero value**: the store counts what waits to be sold, without carrying its cost a second time.

**Damaged Stock Sale** (sale by weight): Sale Date, Buyer (`مشتري التالف` for a buyer not kept as a customer),
the **weight the scale showed in Kg**, the **price per Kg**, Total Amount = weight × price to the piastre, Paid
in Cash, and the damaged items that left with the sale, each in its own unit, optionally with the damage
record it came from. **Sheets and copies are never converted to kilograms**: no conversion is documented,
so the weight is what was weighed and the quantities are what left the store. On submit:

1. a Material Issue takes those items out of the damaged store (zero value: no cost of sale);
2. a **Sales Invoice** of `DAMAGED-BY-WEIGHT`, the weight in Kg at the price per Kg: revenue to
   `إيراد بيع التالف بالوزن` on the damaged store's library (Mawasah);
3. if Paid in Cash, a **Payment Entry** into that library's cash box (`imederp/treasuries.py`); otherwise
   the invoice stays outstanding on the buyer.

A sale row naming its damage record adds to that record's *Sold by Weight*; selling more than is left of
it is refused, and a damage record partly sold cannot be cancelled before its sale.

- **Only these two move the damaged store.** A plain Stock Entry, Delivery Note or stock-moving invoice
  into or out of it is refused (it would bring stock in at its cost with no reason and no loss, or take it
  out without a sale by weight); the owner and the accountant may, to correct a mistake. Stock counts of the
  damaged store are allowed.
- **Who:** branch managers record damage of their own branch's stores and sell from the damaged store if it
  is theirs (Raghad). The owner and the accountant cancel. Cancelling reverses everything it posted; those
  entries cannot be cancelled on their own. Neither document is deleted once submitted, nor saved or
  cancelled in a closed month.
- **Setup:** `setup_core.py` ticks Damaged Store on `التالف — المواساة`; `setup_library.py` makes the
  non-stock item `DAMAGED-BY-WEIGHT` (Kg, revenue `إيراد بيع التالف بالوزن`) and the buyer `مشتري التالف`.

### Bookings: halls and the studio (HAL-01..04, HAL-06, HAL-08, HAL-10..12, STU-01..05, STU-08, STU-14, ACC-04)

**Hall Bookings** (report, HAL-06): the halls' bookings between two dates, one hall or all: day, hall, activity,
rental model, status, attendees, admission price, rent, collected (a fixed rent: what the customer paid; a revenue
share: what was collected at the door), unpaid (a completed booking's invoice outstanding) and cancellations, with
a total. The halls manager sees her own halls.

**Booking Resource** (ImedERP > Business Operations): what can be booked (HAL-01). A **Hall**, with its Capacity
(required) and Equipment, or a **Studio Service** (smart board, reels, podcast, filming, location). Each belongs to
its business (cost center: the halls' or the studio's), and names the **Service Item** it is sold as
(`HALL-HOUR`, `STU-SB75-HOUR`...) by the hour: its price is that item's Item Price, which only the owner changes
(SEC-02). A hall with its own price (HAL-03) has its own item. Nothing is priced on the resource. A disabled resource
takes no new bookings. The owner and the accountant keep the list; branch managers read it. `setup_booking_prices.py`
makes the studio's resources, packages and extras from the requirements' price list (v1.2, 4.8); the halls'
capacities, equipment and prices are still blank in the requirements, so none is made for them.

**Booking** (`imederp/doctype/booking`), by the hour (HAL-02, STU-01):

The screen (docs/SCREEN_DESIGN_STANDARD.md, *Worked example — Booking*): a card on top with the three steps of a new
booking, or a saved booking's total, paid, remaining and what to do next; the actions as buttons (Record Deposit,
Mark Completed, No Show, Cancel Booking); the worked-out and technical fields in collapsed sections.

| Field | Rule |
|---|---|
| Resource, Customer, Booking Date, From, To | Required. To after From, on the same day; Hours worked out. The customer is the one customer record (CRM-01). |
| Activity, Responsible Person, their Phone | Required for a hall (HAL-02); the phone is checked like a customer's number. |
| Rental Model (HAL-12) | Required for a hall: **Fixed Rent** or **Revenue Share** (see below). |
| Package, Extras | The price (see *Price and money* below). |
| Total Amount, Amount Paid, Remaining | Worked out, never typed, on a booking entered here: the total from the price, Amount Paid from its Payment Entries, Remaining = Total − Paid. An imported booking keeps the booking system's amounts (not negative, paid not more than the total) and posts nothing. |
| Status (STU-08) | Tentative, **Confirmed with Deposit** (needs a deposit; recording one confirms a tentative booking), Completed (makes the invoice) and No Show (only once the booking has started), Cancelled (needs its reason). |
| Source (STU-14) | **Manual** for every booking entered here (WhatsApp, walk-in), whatever is sent; **Imported** only through the import, with its source system and id. |

- **No overlap** (HAL-04, STU-14), checked on the server: a Tentative, Confirmed or Completed booking of a
  resource never overlaps another one, manual or imported. One that ends when the next starts does not overlap. A
  cancelled booking and a no-show free their time. Two people saving the same resource at the same moment are
  checked one after the other: each booking writes its resource's row first, and MariaDB refuses the second one,
  whose save asks to **save again** (it then sees the first). This relies on `innodb_snapshot_isolation`, MariaDB
  11.8's default (`pwd.yml`), which a test checks. Bookings of different resources never wait for each other.
  The same check runs whatever saves the booking: the form, the REST API (`frappe.client`) or the import.
- **Calendar** (HAL-10, STU-02; Bookings > the view menu > **Calendar**, `booking_calendar.js`): Frappe's own calendar, opened on
  the week, with **Day** and **Week** (and Month) and arrows to move. Each booking shows its resource, customer,
  times and status (its colour, with a legend; hovering gives the date too). Bookings at the same time sit side by
  side; a cancelled one or a no-show is faded and struck through (its time is free); two of the same resource that
  overlap (only possible by writing to the database around the check) are red. The list's filters apply (a
  resource, a status). It reads the bookings as the list does (`booking.get_events`), so a branch manager sees only
  their own business's. Selecting free time opens a new booking on that day and those hours; a booking is moved
  on its form, where the overlap check runs, not by dragging. It says when a day or week has no bookings, while
  loading, and when the bookings could not be loaded.
- **Who**: branch managers book only their own business's resources (Nour the halls, Gilan the studio), also when
  changing a booking's resource; the owner and the accountant book any. Only they delete a booking.
- **Import** (`imederp/booking_import.py`, for the booking system once its access is decided, STU-11): a
  booking's key is its source system and its id there, so the same file twice adds nothing. A booking already in
  that changed in the source is listed, not overwritten. A row with an error (overlap, unknown customer phone, no
  id, wrong times) fails alone with its reason. The customer is found by phone; none is made from an import. An
  imported booking is changed only in its source: saving it here is refused (INT-01).

#### IMED's lecture halls (26 Oct 2026)

IMED's own halls (resource type **Hall**, cost center `قاعات Imed`) are managed here, apart from XStudio's rooms,
which are only mirrored (see *XStudio* below). A hall booking names its **Hall Booking Type**: Internal Course or
Lecture, External Lecturer, Fixed-fee Rental, Revenue Share, Internal Meeting, Maintenance Block. The type fixes the
money: a fixed-fee rental is **Fixed Rent**, a revenue share is **Revenue Share**, an internal meeting or a
maintenance block is **Not Billable** (no customer needed, nothing priced, no invoice on completion), an internal
course is Not Billable unless chosen otherwise (its fees are the app's or the course's, never counted twice), and an
external lecturer is rented the hall or shares the revenue, never free. A booking may name the **Doctor / Lecturer**
(the doctor's own customer record, group `طبيب`; never a second record) and the **Course** (an App Course, whose
doctor it takes). A revenue share with no lecturer's share agreed yet is flagged **Financial Arrangement Needs
Review**: no Doctor Agreement defines a hall share, and none is assumed.

- **Confirmed** (no deposit): the halls' staff confirm a booking with the *Confirm Booking* button; the studio keeps
  *Confirmed with Deposit*. Nothing is completed by itself when the time passes.
- **Times**: exact `Starts At` / `Ends At` (Cairo); an end earlier than the start is the next day (**Ends After
  Midnight**), so a late session holds both days; equal times are refused. The overlap check works on the instants,
  with the resource's **Buffer Between Bookings** (minutes kept free around each booking; 0 = back to back is fine).
- **Capacity**: Expected Attendees and Attendees (actual) are checked against the hall's capacity.
- **Maintenance Block**: holds the hall like a booking (so nothing else is booked), no customer, no price; cancel it to
  free the hall. The hall's **Location** is on the resource.
- **Reschedule** (button): the new day and times, saved through the form, where the overlap check runs.
- The owner's dashboard has its own card **حجوزات قاعات IMED** (today, next seven days, active and occupied halls,
  this month's bookings, hours, cancellations, fixed rents not yet invoiced, revenue shares, and what needs action:
  past bookings neither completed nor cancelled, shares not agreed); the sidebar lists **IMED Halls** (the hall
  resources) and the **Hall Bookings** report, which now shows the type, the doctor and the hours.
- Tests: `test_hall_bookings` (26), on top of `test_booking` and `test_booking_pricing`.

#### Price and money (HAL-03, HAL-08, HAL-11, HAL-12, STU-03..05, ACC-04)

A booking entered here is priced when it is saved, on the server (`imederp/booking_pricing.py`), from Item Prices only:

- **Price list** (HAL-03): the customer's category's: **Customer Group > Default Price List** (ERPNext's own field;
  or the customer's own Default Price List). An item with no price there takes the default selling list's
  (`Standard Selling`). The list used, the price and how it was worked out are kept on the booking.
- **By the hour**: the resource's service item, price × hours. Hours are the booking's exact length (90 minutes =
  1.5); nothing is rounded up, since no rounding rule was given.
- **Package** (STU-05, *Booking Package*: resource, service item, Charged, Hours Included, what it includes):
  **Once**, its price is the booking's price, for a booking up to its hours (0 = not counted in hours, reels); a
  longer booking is refused. **Per Hour**, its price × hours (podcast by cameras). Extras come on top, once.
- **Extras** (STU-04, HAL-11, *Booking Extra*: service item, Charged, Applies To): each extra listed once with its
  pieces; **Per Piece per Hour** = price × pieces × hours (the requirements: microphone or lights, 50 a piece an
  hour), **Per Piece** = price × pieces. An extra for the studio only is refused on a hall booking.
- **No price, no booking**: a resource, package or extra without a price is refused with what is missing, never
  priced at zero.
- The prices are those in force on the day the booking is priced, and are kept: they are looked up again only when
  the booking's resource, customer, hours, package, rental model or extras change. A later change of a price list
  does not change a booking already priced.

**The hall's two models** (HAL-12, HAL-08), chosen on each hall booking:

- **Fixed Rent**: the lecturer (the booking's customer) pays the hall's price, worked out as above; no share.
- **Revenue Share**: no rent. Attendees × admission price is the expected revenue (HAL-08); **Collected from
  Attendees** is what the center actually took, and is what is shared, not the expected revenue. The **Lecturer's
  Share %** is agreed on each booking, since the owner has not set one (question 33): a booking is not completed
  without it, nor without the **Lecturer** as a Supplier (ERPNext keeps what is owed to someone on a supplier: a
  customer cannot be the party of the payable account `مستحقات للمحاضرين`). The lecturer's share is rounded to the
  piastre and the center keeps the rest. The customer pays only the extras.
- **No deposit for halls** (requirements 4.9, question 2): a hall is paid after it is completed, against its invoice.

**Money** (`imederp/booking_accounts.py`), through ERPNext's own documents, in the system's name after the booking's
own checks; nothing is written to the ledger by hand:

- **Record Deposit / Record Payment** (the booking's buttons): a Payment Entry from the customer into the booking's
  business's cash box (`خزينة X Studio` for the studio, `خزينة سنتر Imed` for the halls: `treasuries.py`
  BUSINESS_TREASURY, through the payment method whose account it is, `نقدي — استوديو X`...), or a group wallet
  with its transaction number. Another business's cash box is refused. It is never more than what is left to pay,
  and names its booking (Payment Entry > Booking). One click is one payment: the dialog sends one request id,
  unique on the Payment Entry, so a retry returns the same payment. The example of the requirements: smart board
  86", 5 hours = 1,150; a deposit of 500 leaves 650.
- **Completed** makes the booking's **Sales Invoice**, once (saving or asking again makes no second one): the
  booking's lines at the prices kept on it, into the business's income account (`إيراد X Studio`, `إيراد القاعات`)
  and cost center, with the booking's deposits taken off as advances. The rest is paid against the invoice.
  A revenue-share booking also makes one **Journal Entry**: what was collected into `خزينة سنتر Imed`, the
  center's share to `إيراد القاعات`, the lecturer's to `مستحقات للمحاضرين` (neither an expense nor the
  center's income).
- **Correcting**: while the invoice or entry stands, what it was made from cannot change. The accountant cancels it
  (with its reason, ACC-06); the booking then changes, and **Make Invoice** makes it again. A cancelled payment is
  taken off Amount Paid. A booking's total cannot drop below what was paid.
  Cancelling an invoice that took a deposit gives the deposit back to the booking (ERPNext's Accounts Settings >
  Unlink Payment on Cancellation of Invoice, on as ERPNext ships it; with it off, ERPNext refuses the cancellation).
  A part of an hour on an item counted in whole units (Nos) is invoiced as one unit at the amount, the hours and
  price in its description; `ساعة` takes parts of hours as they are.
- An **imported** booking posts nothing: where its money is taken is open (question 11).

| Requirement | Where |
|---|---|
| HAL-03 price per hall and customer category | `booking_pricing.py` (price lists), a hall's own service item |
| HAL-08 attendees, admission price, collected | Booking > Revenue Share |
| HAL-11, STU-04 extras | *Booking Extra*, Booking > Extras |
| HAL-12 the two models, the lecturer's share | Booking > Rental Model; `booking_pricing.revenue_share`, `booking_accounts.make_revenue_share_entry` |
| STU-05 packages | *Booking Package* |
| STU-03, ACC-04 deposit, remaining, each business's cash box | `booking_accounts.record_payment`, the invoice's advances |
| STU-14 one overlap check for manual and imported bookings | `Booking.check_overlap` (both are saved through it) |

### XStudio: the studio's bookings, read from its API (STU-06, STU-09, STU-10, STU-14, INT-01, INT-06, INT-07)

The studio's bookings are made in XStudio (xstudioeg.com), which stays their source. The ERP reads them: every
10 minutes the scheduler runs `imederp/xstudio/sync.py` (when **XStudio Settings** is enabled), which reads the
bookings that start in the last 30 and next 60 days, their customers and their prepaid packages, through XStudio's
existing REST API, and writes an Integration Import Log per run. Imported bookings and packages are read-only here
("Change it there"), post nothing (no Payment Entry, invoice or journal entry; amounts are shown for monitoring),
and the halls map to studio services, never to the lecture halls. Setup once:
`bench --site frontend execute imed_erp.setup.setup_xstudio.run`, then the URL, an `accountant` login and its
password on XStudio Settings, **Test Connection**, enable, **Sync Now**. What the existing API can and cannot tell
(500-row cap, no `updatedSince`, no payment ids), the coverage table and the staging setup on Supabase:
`docs/XSTUDIO_SYNC.md`.

### Point of sale, customers and cancelling a sale (LIB-01, CRM-01/02/04, ACC-06, SEC-06)

**The point of sale** is ERPNext's own (Point of Sale page, one POS Profile per library, `setup_library.py`).
POS Settings make each sale a **Sales Invoice**, so a counter sale goes through the same rules as any other:
the library's revenue account (`library_revenue.py`), its cash box (`treasuries.py`), the paper a print or
copy uses (`paper_use.py`), no warehouse on services (`services.py`). `public/js/point_of_sale.js` adds, above
the item list:

- the three steps of a sale (choose the customer; add books, memos or a service; check the total, then Checkout
  and take the payment), for someone using the screen for the first time;
- one button per library service, **تصوير مستندات** (`COPY-SVC`), **تصوير وطباعة** (`PRINT-SVC`) and
  **تجليد** (`BINDING-SVC`), each with its price. A button adds one unit, exactly as clicking the service in
  the item list does, at the Item Price of the POS Profile's price list (only the owner changes prices); the
  quantity is then typed on the number pad (sheets for copying and printing). A service the profile does not
  sell, or that has no price, shows *غير متاح* and adds nothing. Services carry no tax (none is charged) and no
  stock; printing and copying take their sheets of A4 from the library's raw materials store when the sale is
  submitted (see *Paper used for printing and copying*).

Change is given from the same drawer: each library POS Profile's **Account for Change Amount** is its own cash
box (`setup_library.py`). Without it ERPNext used the company's main treasury, and since POS Settings post no
separate change entry, a sale of 315 paid with 350 left 350 in the library's cash box and a credit of 35 on
the customer.

**One customer per person** (`imederp/customers.py`). The customer is ERPNext's Customer, the same record for
every business (CRM-02: its Connections list its invoices, payments and, later, bookings). CRM-01 adds
**College** and **Academic Year** (الفرقة); the category is the customer group (`طبيب` for doctors). The phone is
ERPNext's own (Mobile No, kept on the customer's primary contact) and stays as it was typed. Next to it a hidden
**Phone Key** keeps one spelling of the number, unique in the database:

| Typed | Key |
|---|---|
| `01012345678`, `010 1234 5678`, `(010) 12345678`, `1012345678`, `٠١٠١٢٣٤٥٦٧٨` | `+201012345678` |
| `+201012345678`, `+20 010 1234 5678`, `00201012345678`, `201012345678` | `+201012345678` |
| `03 4567890` (landline) | `+2034567890` |
| `+966 50 123 4567`, `00966501234567` | `+966501234567` |

- A second customer with the same number, in any spelling, is refused with the name of the customer who has it,
  from the customer screen, the point of sale's "new customer", the API, or a change of number on the
  customer's contact. Two people saving the same number at the same moment cannot both succeed: the database
  refuses the second.
- Egyptian numbers are mobile (010, 011, 012, 015 and 8 digits) or landline (area code and number); a foreign
  number needs its country code. Anything else is refused as not a phone number.
- A customer may have **no number** (a walk-in buyer, `مشتري التالف`): blank is allowed and is never a
  duplicate. This is an open question (see docs/known-issues.md), not a decision.
- Customers saved before this get their key from `setup_customer_phones.py`, which lists the duplicates and
  invalid numbers already there instead of merging or changing them. Such a customer can still be edited:
  only a new or changed number is checked.
- Only a customer's own contact is checked; a supplier's or a user's contact keeps whatever number it has.

**Cancelling a sale** (`imederp/sales_cancellation.py`). The libraries take no returns: a sale made by mistake is
cancelled (ACC-06), and only by the owner or the accountant (SEC-03: the cancel right on Sales Invoice,
`setup_users.py`; branch managers do not have it). **Cancel** first asks for the reason, then cancels with
ERPNext's own cancel, which reverses the ledger and the stock and keeps the invoice as Cancelled (ACC-07). The
reason is saved on the invoice as plain text, at most 1,000 characters (**Cancellation Reason**), and its history (Version) shows who cancelled, when
and why (SEC-01). The reason and the cancellation are saved together: if ERPNext refuses the cancel, the reason
is not kept either. A cancel without a reason, through the API too, is refused; the invoice a Damaged Stock
Sale posted is cancelled with that sale and says so. Amend starts the corrected invoice without the old reason.

When cancelling is not the way:

- **A payment received on its own** (Payment Entry against the invoice): cancel the payment first, or let Cancel
  list it and cancel both.
- **A closed month** (`close_period.py`): ERPNext refuses the cancel until the month is reopened
  (see *To reopen a closed month* below).
- **The paper a sale issued, a sale by weight's invoice**: cancelled only with the sale (`paper_use.py`,
  `damaged_stock.py`).

### Library products (LIB-06)

| Requirement | Where it is in ERPNext |
|---|---|
| Name | Item Name |
| ISBN | A row in the item's **Barcodes** table with type `ISBN` (so it can be scanned at the POS) |
| Author | **Author** field on the item (`custom_author`) |
| Category (classification) | Item Group: `كتب` or `مذكرات` (under `كتب وكشاكيل`), or `ورق`, `أحبار`, `مستهلكات`, `خامات تجليد` |
| Cost price | Valuation Rate |
| Selling price | Item Price in the `Standard Selling` price list |
| Quantity | Stock balance per warehouse (`إصدارات الأطباء — المواساة` under the central store, `إصدارات الأطباء — الأزاريطة` for the branch) |

The warehouse and cost center come from the library's POS Profile; without one, from the item's
defaults (Mawasah). The revenue account comes from the item and is then moved to the selling
library's account by `imederp/library_revenue.py`. An item has only one default per company and both
libraries sell the same book, so Azarita must sell through its POS Profile. A sales invoice row
created through the API without a cost center gets the company's default cost center, not the item's,
so an integration must send the cost center itself.

ISBN and Author are optional: paper, ink or binding supplies are saved without them. An ISBN entered
is checked (a wrong check digit is refused). The selling price typed on a new item becomes its
`Standard Selling` Item Price; later changes are made on that Item Price (item > Connections > Item Price).

### Warehouses, reorder levels and transfers (LIB-02, LIB-04, LIB-08)

```
كل المخازن
├── المخزن المركزي بالمواساة          Mawasah, the main warehouse (group)
│   ├── خامات المواساة                 raw materials: paper, ink, binding supplies
│   ├── إصدارات الأطباء — المواساة     doctors' editions
│   └── التالف — المواساة              damaged stock, kept apart until it is sold by weight
├── مخزن الأزاريطة                     Azarita, the branch (group)
│   ├── خامات الأزاريطة
│   └── إصدارات الأطباء — الأزاريطة
└── مخزن سنتر Imed — أدوات مكتبية      the center's office supplies (ink, toner, ...)
```

Each leaf has its own stock account (`setup_coa.py`). Azarita sits beside Mawasah, not under it, so a
report on Mawasah never includes the branch's stock. On a site built before this change, `setup_core.py`
moves Azarita's two warehouses under `مخزن الأزاريطة`, keeping their stock and accounts.

**Who sees which warehouse** (User Permissions, `setup_users.py`; a group covers what is under it):

| User | Warehouses |
|---|---|
| Raghad | `المخزن المركزي بالمواساة` (with the damaged stock) and `مخزن الأزاريطة`, because she supplies the branch |
| Sara | `مخزن الأزاريطة` only |
| Owner, Accountant | all (no restriction) |

The server checks every warehouse on a document, so Sara cannot open Mawasah, see its stock (Stock
Balance, Bin, API) or submit a stock entry with Mawasah on any row, even through the API.

**Transfer Mawasah → Azarita** is an ERPNext **Stock Entry** of type *Material Transfer* (Stock > Stock
Entry), never a purchase: one ledger line out of the source warehouse and one into the target, the total
stays the same, and the value only moves between the two warehouses' stock accounts. ERPNext refuses a
transfer of more than the source holds (negative stock is off). Damaged goods are not transferred: they go
to the damaged store through a Damaged Stock Entry (see Damaged stock below).

**Reorder levels** are set per item **and** per warehouse in the item's *Reorder Levels* table (Inventory
tab): e.g. A4 paper at 1,000 in `خامات المواساة` (request type Purchase) and 500 in `خامات الأزاريطة`
(type Transfer, since Mawasah supplies it). ERPNext needs a reorder quantity on each row. A warehouse can
have only one row per item, and never a group warehouse (`imederp/stock_reorder.py`). Levels are in the
item's stock unit.

- When a submitted document takes an item's stock in one warehouse to or below that warehouse's level,
  the stock users who may see that warehouse get an in-app alert (`reorder_level_reached` in
  `notification_service.py`): Sara for Azarita, Raghad for both. Only the crossing alerts, not every sale
  below the level. The comparison uses that warehouse's own stock, never the total of all warehouses.
- **Reorder Alerts** report (ImedERP sidebar) lists everything at or below its level now, each user only
  for their own warehouses.
- With *Stock Settings > Raise Material Request when stock reaches re-order level* on, ERPNext also
  raises the Material Requests itself every day.

### Branch requests from the main warehouse, and paper per printing machine

A branch asks Mawasah for materials, Raghad approves, the store issues them and records who received
them; paper is issued to a printing machine, so it can later be compared with the machine's counter.
Built on ERPNext's **Material Request** and **Stock Entry** (`imederp/material_issue.py`):

| Step | Who | Where | What happens |
|---|---|---|---|
| 1. Request | Branch (Sara) | Stock > Material Request > New, type *Material Transfer*: Set Source Warehouse `خامات المواساة` (or `إصدارات الأطباء — المواساة`), Set Target Warehouse the branch's, items and quantities (any unit the item has, e.g. carton), optionally a printing machine per row. Save. | Nothing moves. |
| 2. Ask | Branch | **Request Store Approval** | *Approval Status* = Pending Approval; the approvers get an in-app alert. Changing the request now sends it back to draft. |
| 3. Decide | Raghad | **Approve**, or **Reject** with a reason | Approve submits the request (now locked; a change is Cancel + Amend, approved again). Reject closes it for good. Who and when are kept on the request. The requester is alerted. |
| 4. Issue | The store (Raghad) | On the approved request: Create > Material Transfer. Fill **Received By**, the machine on each paper row, the quantity actually issued. Submit. | Stock leaves Mawasah only now. *Issued By* = whoever submitted; the date and time are the entry's posting date and time. The request shows *Partially Received* until everything is issued, then *Transferred*. |

Rules, checked on the server (so they also hold through the API):

- A request is from a warehouse ticked **Supplies Branches** (`setup_core.py` ticks Mawasah's raw materials
  and doctors' editions, not the damaged store) to another, non-group warehouse. Quantities above zero,
  active stock items only. A branch can only request for the warehouses its User Permissions allow.
- Only Approve submits a request, and only a holder of **Stock Request Approver** can approve or reject,
  for the source warehouses her User Permissions allow. The approval fields cannot be set by anyone else.
- Nothing can be issued from a draft, pending, rejected or cancelled request. The issue goes from the
  approved source to the approved target, and the total issued per row never goes beyond what was approved
  (rows are compared in the item's stock unit; two issues submitted at once are serialised). Stock
  availability and negative stock are ERPNext's own checks.
- **Paper** (item group with **Needs Printing Machine** ticked, or under one: `ورق`) is issued to one
  printing machine per row; a machine named on the request cannot be swapped; the machine must be active
  and at the target branch. To supply several machines, add one row per machine with its own quantity.
  Other items need no machine.

**Printing Machine** (ImedERP > Branch Requests > Printing Machines; PRN-01, PRN-08): name, **Branch** (a library
only: Azarita has 1 Epson and 2 Riso, Mawasah 1 Epson and 3 Riso), **Type** (Epson / Riso), **Model**, **Ink Cost
per Sheet**, **Last Maintenance** (not in the future), **Out of Service** (takes no paper and no readings), and
the location warehouse paper is issued into (e.g. `مخزن الأزاريطة`, under Advanced). The ink cost is filled from **Printing Cost
Settings > Ink by Machine Type** for the machine's type when left empty, and follows a change of type unless it was
set for that machine; Riso ink costs more. The owner's ink prices (18 Oct 2026) are on the settings: a Riso ink of
one colour 3,000 and an Epson set of 4 colours 1,500. Enter the sheets one ink prints and the ink per sheet is worked
out (price ÷ sheets) and locked; until then it is assumed (0.05 Epson, 0.10 Riso), said so on the screen and by
`setup_library.py`. A machine still on its type's rate follows a change on the settings; one set by hand stays. The owner and stock managers add machines; Raghad too.

**Printer Reading** (PRN-01, PRN-02): a counter reading of one **Machine** (a link to Printing Machine, in
service); its **Branch** is the machine's library, filled in and never typed. The **Opening** is the machine's last
submitted closing reading, filled in on the form and set again by the server (on submit too, in case another
reading of the machine was submitted meanwhile); only a machine's first reading is typed. A counter only goes up:
the closing cannot be below the opening, a reading cannot be dated before the machine's last one, and only a
machine's latest reading can be cancelled, so the next one still starts where the last ended. Consumed = closing -
opening. Sales do not say which machine printed them, so what was sold is set against the whole library's counters
for the day, on the Daily Counter Reading below, not on a single reading.

**Daily Counter Reading** (عدادات اليوم, PRN-01; the home page's printer shortcut and ImedERP > Daily Counters):
each library records all its counters of the day on one screen and saves once. Pick the **Branch** (a branch
manager's own library is filled in) and the **Date**; the table lists every machine of the library in service with
its type and opening (its last closing reading, typed only for a first reading); type each **Closing**. Every
machine in service must be there (one not working is marked Out of Service), and there is one screen per library a
day. Submitting it makes one Printer Reading per machine with the same checks (the counter only goes up, no date
before the machine's last reading); cancelling it cancels them, and they are cancelled only from it.

**The day's paper** (PRN-02), on the same screen: **Consumed Sheets** (what the counters went up by, all machines),
**Sold Sheets** (the printing and copying the library sold that day, from its submitted invoices, one sheet per
unit as in `imederp/paper_use.py`; worked out by the system, never typed) and **Variance** (consumed - sold). A
refund takes no sheets back: the paper was printed and counted. A sale of that day submitted or cancelled after the
screen was submitted updates it. The **Variance Value** (PRN-08, PRN-09) is the variance × the **Cost per Printed Sheet**: paper (the
moving average price in the library's store) + waste + the machine's ink + overheads, from Printing Cost Settings
and the machine. Each row shows its machine's cost per sheet; the day's is their average weighted by what each
machine printed (Riso ink costs more than Epson's), and is fixed when the day is submitted, so a later sale is
valued at the same cost. A library with no paper price yet is warned that the paper is left out. The money (cost,
variance value, the day's printing and copying sales, the **Average Price per Sheet** and the **Margin per Sheet**,
average price - cost, PRN-08) is in its own section, shown to the accountant and the owner only; a branch manager
sees the sheets. A machine that stopped for a fault is ticked **Broke Down** with what happened (PRN-09).

**Daily Printing** report (طباعة اليوم; under ImedERP > Daily Counters and on the owner's page; PRN-01, PRN-02,
PRN-09): for a range of dates and a library, each machine's **Consumed Sheets**, its **Utilization** (its share of
the library's printing that day), its share of the **Sold Sheets**, its **Variance** in sheets and its **Variance
Value** at its own cost per sheet, then the library's day in bold under its machines. A sale does not say which
machine printed it, so the day's sales are shared out by each machine's share of the printing (equally on a day
nothing was printed); the machines add up to the day, whose row also has the average price and margin per sheet.
Breakdowns show with what happened. Over more than one day (a month, PRN-03) the **Period** follows: each machine's
printing, utilization, days broken down and variance value, and the period's total. A branch manager sees her own
library.

**Material Issues** report: every request row with its approval, each issue against it (stock entry,
date, time, quantity, recipient, issuer, machine) and what is still to issue. Filters: dates, request,
approval status, target warehouse, machine, item, requested by. The Material Request list shows the
Approval Status column and filter.

**Raghad's approval rights**: `setup_users.py` gives her the `Stock Request Approver` role. Someone else is
made an approver by adding that role to their user (User > Roles), with User Permissions on the source
warehouse.

To reopen a closed month: Accounting > Accounting Period > open the month > untick **Closed** on the
document types to allow (or tick **Disabled** to reopen everything). Only Owner and Accountant can. A
document linked to a closed academic period cannot be saved either.

**Payment methods.** Each library's POS takes cash on its own method, `نقدي — مكتبة المواساة` /
`نقدي — مكتبة الأزاريطة`, which posts to that library's cash box (ERPNext's `Cash` posts to the company's
main treasury), plus `InstaPay` and `Vodafone Cash`, which post to the group's wallets (`setup_library.py`). The other businesses take cash the same
way into their own cash boxes: `نقدي — قاعات Imed` (the center's), `نقدي — استوديو X` and `نقدي — تطبيق BA Plus`.

**Doctors.** A doctor is a Customer in the group `طبيب` (CRM-01), one record whatever they buy or earn. A
Doctor Agreement's doctor can only be one of them: the screen lists only that group, and the server refuses
any other customer.

A **Doctor Agreement** holds the doctor, the type (Books or App), the start date, the settlement cycle
(Module, Term or Round) and its status. **Suspended** (it can be set after the agreement is submitted, with no
amendment) stops new editions and subscriptions on it, while its account can still be settled. **Balance**
is read-only, worked out from the doctor's ledger each time an entry is submitted or cancelled.
Editions, subscriptions and ledger entries go only on a **submitted** agreement (a draft's terms can still
change; a cancelled one is replaced by its amended copy), and submitting an edition checks its agreement
again.

The **doctor's ledger** (Doctor Ledger Entry) holds the agreement, the academic period, the date, the type, the
edition, the quantity, the amount and its **source**: the sales invoice and the invoice line an accrual comes
from, and the journal entry behind it. The source is filled in by the system, read-only and not copied. The
types (DOC-07):

| Type | Arabic | Agreement | Balance |
|---|---|---|---|
| Accrual | استحقاق | Books or App | adds |
| Payout | صرف (paid out to the doctor) | Books | takes |
| Unsold Copies Charge | خصم متبقي (copies he asked for and left unsold, owner's decision of 10 Oct 2026) | Books | takes |
| Adjustment | تسوية | Books or App | its own sign |
| Collection | تحصيل (collected from the doctor) | App | takes |

An entry's amount is positive except an Adjustment's; its edition belongs to the same agreement; an invoice
line is on the invoice named with it, and is counted once per type (a cancelled entry no longer counts, so the
line may be counted again).

**The doctor's amount on each copy sold** (DOC-07, LIB-05; `imederp/doctor_accrual.py`). When a sales invoice is
submitted (the point of sale makes Sales Invoices too), each row that names a Book Edition adds an **Accrual** to
the doctor's ledger: the row's quantity × the edition's Doctor's Amount per Copy (kept on the edition when it was
approved), with the edition's agreement and period, the invoice's date, and the invoice and line as its source.
Three copies at 80 add 240. The invoice and line are the key: a line already in the ledger is skipped, so counting
an invoice again adds nothing. Cancelling the invoice cancels its entries and the balance goes back; a credit
note's rows add an **Adjustment** of minus their amount. The seller does not need to open the doctors'
accounts: the sale posts the entry for them. Rows with no edition (services, other items) add nothing.

In the accounts, the sale's new rows make one **Journal Entry**, named on each entry (Journal Entry): Dr
`حصة الأطباء` / Cr `مستحقات للأطباء — الكتب`, each row on the cost center of the library that sold; a credit note
posts the other way round. `مستحقات للأطباء — الكتب` is a plain liability with no party: ERPNext does not take a
Customer (the doctor, CRM-01) as the party of a Payable account, so which doctor is owed what is in the doctor's
ledger and each agreement's balance. Cancelling the sale cancels the journal entry too; the entry and its journal
entry cannot be cancelled on their own while the sale stands.

A **daily job** (`doctor_accrual.run_daily`, with the scheduler on) is the safety net for sales that reach the
books without these hooks, such as the daily import: every submitted invoice line with an edition (and an amount
per copy) that is not in the doctor's ledger is counted, with the same invoice-and-line key, and the entries of an
invoice that was cancelled are cancelled. Running it again changes nothing. One invoice that fails is rolled back
and written to the Error Log, and the others go on; the next run tries it again.

A sale of an edition carried forward (DOC-15) is entered in the period it was carried to, once that period has
started, so it shows on that period's statement.

**The doctor's statement** (DOC-08, DOC-13; report **Doctor Statement**, under Doctors and Editions and on the
owner's page). One agreement and one academic period on their own, from the doctor's ledger:

| Row | What it shows |
|---|---|
| Balance Brought Forward | the balance from before the period; a negative one stays a debt and is taken from what comes next (DOC-20) |
| Copies Sold (one per edition) | the edition, copies sold in the period (less returns), the selling price, the cost of a copy, the doctor's amount per copy, and what he earned on them |
| Other entries, by date | payouts, charges for unsold copies, adjustments, each with its date and remarks |
| Balance at the End of the Period | where the account stands; the summary says which way it runs |

It leaves out the library's side (owner's decision): its profit per sheet, its marketing and any difference
between the calculated price and the price set by hand. The **cost of a copy** is what it costs to make (DOC-11):
(paper + ink) per sheet × sheets + binding, which takes in the cover (`book_edition.get_copy_cost`). The overheads
per sheet (rent, power, salaries) go into the price only: "no other operating expense is deducted". An entry
belongs to the period it names, or to the term above it (a term's statement takes in its rounds and modules, since
books settle by module, DOC-05); one entered with no period belongs to the period its date falls in. Accounts Manager and System Manager
open it (the accountant and the owner).

**Paying the doctor** (DOC-09, ACC-11). A **Payout** in the doctor's ledger names the **Treasury** it is paid from
(a cash box or a wallet). On submit it posts a Journal Entry: Dr `مستحقات للأطباء — الكتب` / Cr the treasury.
That journal entry runs the usual treasury check (`treasuries.check_entry_treasuries`): the accountant pays from
any treasury, anyone else only from their own business's cash box or the group's wallets. A doctor may be paid in
parts and as often as needed, but never more than he is owed at that moment (that would leave him a debt by
mistake). Cancelling the payout cancels its journal entry; the journal entry is not cancelled on its own.

The payout prints as a **receipt** with **MMG Doctor Payout** (`imederp/print_format/mmg_doctor_payout`), the
default print format of Doctor Ledger Entry: who was paid, the agreement, period, date and treasury, the amount in
figures and in words (`فقط ألف و مئتان و خمسون جنيه مصري وخمسون قرشًا لا غير`), and lines for the doctor's and the
accountant's signatures. Arabic when printed in Arabic, like the invoice. A simple version; the final design comes
in week C. Any other ledger entry prints the same way under the title حركة حساب طبيب.

**The doctor's unsold copies are never his to pay** (owner, 21 Oct 2026; this replaces DOC-18 of requirements v1.2
and the decision of 10 Oct 2026, and with it DOC-22's approval of such charges):

- *Curriculum unchanged:* the copies left stay in the store. The edition is carried forward to the next period and
  they are sold there; the doctor earns his amount on each copy as it sells, in the period it sells in. Closing a
  term or module charges nobody and posts nothing.
- *Curriculum changed:* **Cancel: Curriculum Changed** marks the edition obsolete and charges nothing. Its copies
  left are disposed of with **Dispose as Scrap** (on the edition, menu Edition): a draft **Damaged Stock Entry**
  naming the edition, for its copies left, from its library's store. Submitted, the copies leave the store at their
  cost, posted to الهالك والتالف on the library's cost center (the library bears 100% of it), and wait in the
  damaged store; the edition shows them as **Disposed Qty**. They are then sold by weight with a **Damaged Stock
  Sale** naming that damage record: the kilograms, the price a kilogram and the money, to إيراد بيع التالف بالوزن.
  Cancelling the sale, then the disposal, puts the copies back on the edition.
- No **Unsold Copies Charge** is saved or submitted any more. One recorded before can only be rejected (a draft) or
  cancelled (a submitted one); `setup/check_doctor_accounts.py` lists them.

A closed academic period takes no new entries (`period_lock.py`), except the payout that settles it after it ends.
A sale of an edition whose period is closed is refused until the edition is carried forward.

**Approving a deduction** (DOC-22). A deduction from the doctor, an adjustment taking money off him by hand, is
applied only once the owner or the accountant approves it, the same way as an expense (role Expense Approver). The
form shows **Approve** (which submits it) and **Reject** (with a reason; a rejected one is closed for good). An approver's own deduction is approved as he submits it. Approval Status, Approved /
Rejected By and Rejection Reason are set only by the system, Approve and Reject, never by editing or the API. The
owner's page counts the deductions waiting. A credit note's adjustment is not a deduction: the copies came back.

**A negative balance stays a debt** (DOC-20). A books doctor whose approved deductions are more than he earned owes
the group. The
balance stays below zero and is never closed on its own: what he earns next pays it off first, and nothing is paid
out to him while he owes (a payout is never more than the balance). The report **Doctor Debts** lists, as of a
date, every agreement under which the doctor owes the group: a books agreement below zero and an app agreement's
platform fees not collected yet, with the amount, since when it is owed and its age in 0-30 / 31-60 / 61-90 /
90+ days. Later amounts pay off the oldest part first, so the age is that of the oldest part still unpaid. It is
worked out from the doctor's ledger; on the owner's page under the reports and in the sidebar.

**Changing a doctor's balance by hand** (SEC-07). The balance is never typed: it is read-only on the screen, and
saving an agreement (also through the API, also a draft) works it out again from the ledger. A change by hand is an
entry in the doctor's ledger (an adjustment, a payout, a charge), which only the accountant and the owner can make
(Accounts Manager), a deduction only once approved. Each one submitted or cancelled goes into the agreement's own
history (Version) as the balance before and after, with the user and the time, alongside the entry's own history
(track changes). Sales are not changes by hand and are not listed there: each is on its invoice.

**Balance Direction** (DOC-30) is set by the type: Books is *Owed to Doctor* (his amount on the copies sold),
App is *Owed by Doctor* (the platform fees). Each agreement keeps its own balance; a doctor's agreements are
never offset against each other (owner's decision). The agreement screen shows the balance at the top in its
colour (orange: we owe the doctor; blue: the doctor owes us), and the list shows each agreement in the same
colours, a suspended one in grey. A negative balance runs the other way (DOC-20): a books doctor charged more
than he earned owes the group, and is shown so.

**Doctor Receivables** (RPT-08, ImedERP > Doctors and Editions) lists the books agreements that still owe the
doctor, read from the same ledger (`imederp/doctor_balances.py`); it posts nothing. Only the owner and the
accountant (who may open the ledger) see it. What doctors owe the group is **Doctor Debts** (RPT-10), above.

| Shows | Filters |
|---|---|
| Opening (balance before From Date), Accrued, Adjustments, Unsold Copies Charges, Paid, **Outstanding** (on To Date, the balance the agreement screen shows), Last Settlement, and the number of entries, which opens them. Under each agreement, a row per library: an entry's library is its invoice line's, else its edition's, else its journal entry's one cost center; a payout for the agreement as a whole is *Not by branch*. | From / To Date, Doctor, Agreement, Branch (that library's entries only), Show Settled Agreements |

**The rest of the doctors' requirements** (all from the doctor's ledger; under Doctors and Editions in the sidebar):

| | Requirement | What it shows |
|---|---|---|
| Unsold Editions report | DOC-21 | Editions still on sale whose period (or the one they were carried to) ended before a date, e.g. the next module's start, with the copies left split between the doctor's and the library's. Branch managers see their own library's. |
| Owner Share Plan vs Actual report | DOC-27 | For each edition sold: the owner's share planned in its price (profit per sheet × sheets × copies sold) against what the sales brought after the rest of the planned price; a price set by hand, a discount or a carried copy sold at today's price shows as the difference. On the owner's page. |
| The doctor's file | DOC-29 | A doctor's Customer form lists his agreements with their balance, which way each runs and when it is next settled, kept apart (no offsetting), for the accountant and the owner. |
| His statement sent to him | DOC-23 | After a settlement by hand (a payout, an approved charge, an adjustment, a collection) the doctor is emailed his statement for that period, to the email on his file; with none on file, the accountant is notified. Sales send nothing. |

The agreement's **Account Summary** (DOC-29) gives, for that agreement alone: the balance and its direction,
the **settlement period** (from and to, entered by the accountant: each year has its own dates, owner's
decision of 12 Oct 2026; the next settlement is due at its end, and after settling he enters the next period,
with no amendment) and the **last settlement** (the latest payout or collection in the doctor's ledger, updated with the
balance whenever an entry is submitted or cancelled). Saving a submitted agreement reads the balance and the
last settlement again from the ledger, so a form opened before an entry was posted still saves. The top of the
screen shows the balance and the next settlement together.

A books agreement's **Agreement Terms** give the doctor's amount per copy sold from each date (a row with no
date starts with the agreement). A new amount is a new row from a later date, added without amending the
agreement, and it starts after the last one (an earlier date would move editions already priced); a term
already in force is never changed or removed, one that has not started yet can be taken back. An edition has an **Edition Date** and takes the
amount in force on it, read-only on the edition, and a submitted edition keeps its amount: going from 80 to
100 a copy from 1 November leaves the editions priced at 80 as they were.

**Doctors' editions and the app.** An edition's price per copy is built on what the doctor asks for each
copy (from his agreement's terms in force on the edition's date), with the library's costs and profit on top:

> (paper + ink + overheads + profit) per sheet × sheets per copy + binding + marketing (optional) + the
> doctor's amount.

The price is not rounded (owner's decision, instead of DOC-28's rounding). Another price can be set by
hand, higher or lower (to sell more): the difference is added to or taken from the library's profit, never
the doctor's amount, and a price below the cost of a copy is saved with a warning. Editions belong to a
library only. A books agreement is always a fixed amount per copy, never a percentage (owner's decision).

The rates change several times a year, so the owner and the accountant set them on **Printing Cost
Settings** (waste, ink, overheads and profit per sheet; binding per copy), and every change is recorded.
The paper itself is the moving average price paid for A4 paper in the library's raw materials store, from
the boxes bought, plus the waste rate. An edition takes the rates while it is a draft, any of them can be
changed for that edition only, and they are kept once it is submitted, so a later price change never
touches an approved edition (DOC-24/25). It cannot be submitted before the library has a paper price. Marketing is an optional amount per copy that
goes to the library, not to the doctor.

**Edition quantities and sales (DOC-14..17).** An edition keeps the copies printed because the doctor asked for
them (**Doctor Requested Qty**) apart from those the library added (**Library Extra Qty**); **Total Qty** is their
sum. Neither can be negative, an edition is approved with at least one copy, and once approved the quantities
change only by Cancel and Amend.

- **Which edition a copy came from.** The edition names the **Item** it is sold as. Every sales invoice row of
  that item names the edition (**Book Edition** on the row): it is filled in when the item has one approved
  edition on sale, and must be chosen when it has several (a new edition while the last one's copies are
  carried forward). A row cannot name another item's edition, a draft edition or a cancelled one, an item whose
  editions were all cancelled is not sold without one, and an edition never sells more copies than its Total
  Qty, also when two invoices are submitted at the same moment (the second is asked to submit again).
- **Sold Qty and Remaining Qty** come from the submitted invoices that name the edition, worked out again on
  every submit and cancel (`imederp/edition_sales.py`), so a sale is never counted twice and a cancelled one
  stops counting. The invoice stays the record of the sale; nothing else is posted.
- **Carry Forward** (DOC-15, approved editions with copies left): the edition goes on to a later, open academic
  period with who did it and when. Its approved costs are not touched (DOC-25), and its copies stay on sale at
  the price of the day they are sold, ERPNext's Item Price (DOC-16).
- **Cancel: Curriculum Changed** (DOC-17): the doctor says by word of mouth that the curriculum changed. The
  edition is marked Cancelled with the **Notice Date** (not in the future, not before the edition) and the
  employee who received the notice and records it, taken from the login, never typed; the time it was
  recorded is kept too. The edition stays approved with its sales, stock and costs; no more copies are sold.
  Nothing is charged to the doctor (owner, 21 Oct 2026): the copies left are disposed of as scrap at the library's
  loss with **Dispose as Scrap** (see the doctors' accounts below).
- Status and these fields change only through these buttons (the server refuses them otherwise), and the
  edition's history shows each change. Branch managers act on their own library's editions; the owner and the
  accountant on any.
- An item with no edition sells as before. Open questions (which copies sell first, an Item per edition, how
  printed copies enter the store): docs/known-issues.md.

An App Subscription records the student and the platform fee due from the doctor only: the course is paid
by the student to the doctor directly and is not recorded (APP-05, v1.2). Editions belong to books
agreements and subscriptions to app agreements.

A subscription is made on an *App Course* (APP-01): the course's name, its doctor's app agreement and its
term. The doctor comes from the agreement, and the subscription takes its agreement and term from the
course, so the user only picks the student and the course. A course is made once per agreement and term; a
closed course takes no new subscriptions.

The platform fee (APP-02/03) is counted per course: its submitted subscriptions are its students, the tier
for that number is taken from the *Platform Fee Schedule* in force when its term starts, and the course
shows students × fee per student (300 students → 200 a student → 60,000). Every subscription carries the fee
for one student. It is counted again whenever a subscription is submitted or cancelled, and for every open
term's courses when a schedule is submitted or cancelled; once the term is closed it stays. The tiers are
data the owner keeps (Super Admin), not code: new prices are a new schedule from a later date.
The two counting rules the owner decides are constants at the top of `app_course.py`: `TIER_COUNTED_PER`
(`"course"`, the owner's answer; `"doctor"` counts all the doctor's courses in the term together) and
`COUNT_WITHDRAWN` (a student whose submitted subscription is ticked *Withdrew* still counts; assumed until
the owner answers).

**In the doctor's account (APP-05, decided 19 Oct 2026).** The fee is posted automatically with every student
(`imederp/platform_fee_posting.py`): whenever a course is counted again, the difference between its fee and what
its doctor's ledger already holds for it is one *Doctor Ledger Entry* naming the course, an Accrual when it grows
and an Adjustment when it shrinks (a cancelled student, or the 101st moving the course to 200 a student: 25,000
becomes 20,200). Each has its journal entry: Dr مستحقات على الأطباء — رسوم المنصة (the doctor as the party) /
Cr إيراد رسوم المنصة, on the app's cost center. They need no approval, send no statement, and are cancelled only
by changing the course's subscriptions. The doctor's balance, Doctor Debts and Accounts Receivable show the fees.

**BA Plus's daily file (INT-05, APP-13).** `imederp/app_import.py` takes BA Plus's courses and subscriptions,
each by its id in BA Plus (`import_key` = `ba_plus:<id>`, unique), into *App Course* and submitted *App
Subscription*: the doctor's app agreement is found by his BA Plus id (Doctor Agreement › BA Plus Doctor ID), the
course is made the first time its id comes (in the one term the date falls in), the student is found by phone or
made in the group `طالب`, and the fee is counted and posted as for a subscription entered by hand. The same file
again adds nothing; a known record that changed in BA Plus is listed, not overwritten; a row that fails keeps
nothing and the others go on. An imported course or subscription is changed only in BA Plus (`import_source.py`),
except a course's status. A subscription is always on `تطبيق BA Plus`'s cost center, whoever made it. The columns
and what still needs a real BA Plus export: docs/IMPORT_DATA_STANDARD.md, part 3.

```bash
docker exec frappe_docker-backend-1 bench --site frontend execute imed_erp.imederp.app_import.import_file \
  --kwargs '{"path": "/home/frappe/frappe-bench/sites/app_2026-10-22.csv"}'
```

Each run writes an **Integration Import Log** (INT-07; sidebar: Import Logs; owner and accountant): the system
(`ba_plus`, `library_pos`, `booking`), the file and its SHA-256, when and by whom, rows read, inserted, other
records made, skipped, changed in the source and failed, and each row to look at with its line and reason. Only an
import writes one; nobody edits or deletes it. A run the database drops as a whole keeps nothing and is logged as
Failed.

**Integration Status** (INT-09; report, sidebar; owner and accountant) shows one row per system (the libraries'
point of sale, the studio's bookings, BA Plus): the last import that went through, its log, what it imported,
skipped, found changed and failed, and the last run with its status when it came after (a failed run does not hide
the last good one). A system no import reads says *not connected yet*. **Import a Period Again** runs again the
files that came in the days chosen (each log keeps its file), oldest first, each distinct file once: what is already
in is skipped, so only what failed (e.g. a doctor whose BA Plus id was written since) or is new goes in, and each run
writes its own log. BA Plus only for now; the libraries and the booking system get it with their imports.

**The app statement (APP-11).** The *Doctor Statement* of an app agreement shows one row per course: its
students, tier, fee per student and the fee posted in the term, then the collections, and the balance. A fee not
collected stays the doctor's debt (Doctor Debts, APP-08) and is the next term's balance brought forward (APP-12):
300 students → 60,000, 40,000 collected → 20,000 carried into the next term.

**Collecting them (APP-06).** A *Collection* in the doctor's ledger names the treasury the money goes into and
is never more than he owes; it posts Dr the treasury / Cr the same receivable, and cancelling it takes the money
back out.

The *Platform Fees* report (APP-07; owner and accountant, on the owner's dashboard) lists each course of
each doctor in a term with its students, the tier applied, the fee per student and the fee due, filtered by
term, doctor or agreement. A student is subscribed once to a course: a second submitted subscription is
refused until the first is cancelled.

The tests (`test_app_course.py`, `test_platform_fee_schedule.py`) check the owner's tiers on whole
courses: 100 students → 25,000, 300 → 60,000, 501 → 85,170; the 101st student moves every subscription
to the second tier and cancelling it moves them back; tiers from a later date leave a term that started
before them alone; and both answers to each counting rule.

Invoice PDFs need the site's `host_name` to point at the web server inside Docker, otherwise
wkhtmltopdf cannot load the stylesheets (`network error: Connection refused`):

```bash
docker exec frappe_docker-backend-1 bench --site frontend set-config host_name "http://frontend:8080"
```

### Owner Dashboard: yesterday, and the financial reports (5.1, RPT-01, RPT-02, RPT-05)

The owner logs in to the **Owner Dashboard** (`/desk/owner-dashboard`; first link of the ImedERP sidebar). Under
the welcome band is **yesterday**: one screen with how every business did the day before. Under that come the
approvals, this month's money cards and the charts, which were already there.

**Yesterday** is the calendar day before today in the site's time zone (System Settings: Africa/Cairo), from
00:00 yesterday to 00:00 today, excluded: on 1 Jan 2027 it is 31 Dec 2026, on 1 Mar 2028 it is 29 Feb. Each
document is taken by its business date, never the day it was typed: the ledger's posting date, a counter
reading's date, a booking's date (the day of the service), a doctor's ledger entry's date.

| Card | Shows | Source and rule |
|---|---|---|
| Revenue and expenses by business | Each activity (every leaf cost center: the two libraries, halls, studio, the app, head office, the shared premises) with its revenue, expenses and net, and the total | GL Entry on Income / Expense accounts, `is_cancelled = 0`, not opening, not Period Closing Voucher. Only submitted documents post, so a draft or an expense not approved is not counted. A cancelled document and its reversal are both left out. Accrual basis: an invoice is revenue once; the payment of it moves cash, not revenue. The shared premises' row shows what no rule split, marked *not split* |
| Halls and studio | Bookings **of yesterday's date**, halls and studio apart: held (not cancelled, not a no-show), completed, cancelled, no-show; studio hours booked (held) and delivered (Completed); bookings made yesterday for any date; those of yesterday still neither completed nor cancelled | Booking, by `booking_date` (made yesterday: `creation`) |
| Platform fees | Charged yesterday (Accrual + Adjustment entries), collected (Collection entries: money received), still owed by doctors at the end of the day, new students | Doctor Ledger Entry of the app agreements, submitted; the balance of `مستحقات على الأطباء — رسوم المنصة`. A fee charged is not cash. With no app agreement: *No app agreement yet* |
| Paper and counters | Per library: each machine's opening, closing and sheets, then sheets printed, sold and the difference, in sheets | Submitted Daily Counter Reading of the day. A warning (orange), never a zero, for: no reading, a reading saved but not submitted, a breakdown, a difference, a machine without a library. With no machine: *No printing machine is set up* |
| Integrations and imports | Each one with Working / Needs attention / Failed / Unknown / Not configured, the last success and a one-line error | Booking import: *Not configured* (nothing runs `booking_import.py`, and it keeps no log). File imports: Frappe's Data Import records. The app's daily jobs: Scheduled Job Type and Scheduled Job Log (a failure after the last run, a job that has not run for 36 hours, the scheduler off). AI assistant: its provider's `connected`. E-mail: an outgoing Email Account. Nothing secret is shown: no settings, no file content, only the error's last line |

Colours carry meaning only: green a profit or money in, red a loss or money owed, orange what needs
attention, the rest neutral. The figures come from `imederp/owner_yesterday.py` (`get_yesterday`, one call, a few
grouped queries) and are drawn by `public/js/imed_owner_dashboard.js` (styles: `imed_theme.css` §25). They load
when the dashboard opens and again after five minutes away.

**Who sees it.** The workspace is for **Super Admin** only (`setup_dashboard.py`; it was Super Admin and System
Manager, and a developer account has System Manager). Hiding is not the protection; each figure is refused by
its own endpoint:

- `get_yesterday` answers Super Admin and Administrator only.
- The money cards (`owner_figures.py`) answer the owner and the accountant.
- The reports have their roles (Super Admin, Accounts Manager, Accountant), and each checks again on the server
  (`owner_figures.check_reader`).

A branch manager who types the address gets *Not permitted*. Tested in `test_owner_reports.py` and checked in
the browser.

**The desktop icon.** There is no home screen with tiles any more (owner's decision of 21 Oct 2026): `/desk`
opens the Owner Dashboard. Its entry point is the first link of the ImedERP sidebar and of the ImedERP tile.

A separate Owner Dashboard tile is not used, on purpose. Frappe shows a tile only with a Workspace Sidebar of
the same name, and that sidebar would replace the ImedERP sidebar on the dashboard. It is hidden by
`home_screen.tidy_home` on every migrate.

To make the changes show on a site:

```bash
docker exec frappe_docker-backend-1 bench --site frontend migrate        # the reports and the sidebar links
docker exec -i frappe_docker-backend-1 bash -c "cd /home/frappe/frappe-bench && bench --site frontend console" \
  <<< 'exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_dashboard.py").read(), {"frappe": frappe})'
docker exec frappe_docker-backend-1 bench --site frontend clear-cache
docker restart frappe_docker-backend-1                                   # the new JS/CSS version in hooks.py
```

The console line recreates the dashboard workspace with its Super Admin role. Migrate alone takes the role
from `imederp/workspace/owner_dashboard/owner_dashboard.json`, which already has it.

#### Revenue by Period (RPT-01)

ImedERP > Financial Reports > *Revenue by Period*. Each business's revenue by **Daily**, **Weekly** or
**Monthly** period between two dates.

- **What revenue is.** Income accounts, credit − debit, from submitted documents only. A cancelled document and
  its reversal are left out, and a credit note takes revenue back. This is the accrual basis: revenue is what
  was invoiced. Money collected is not revenue and is not in this report (see Cash Movements and Cash Box
  Balances). An invoice and its payment are therefore one revenue, never two.
- **Rows.** The business tree, from the cost centers: each activity, the group above it with the sum of its
  branches (Libraries: Azarita + Mawasah; Center: halls + studio + shared premises), and the top row, which is
  the total. **Business** filters one branch of the tree; a group stands for every business under it. The site
  has no separate Branch dimension: the branches are these cost centers.
- **Periods.** A week starts on System Settings' first day of the week (Saturday). The first and last periods
  are cut to the dates chosen. There are at most 370 columns.
- **Agrees with** the ledger: the top row's Total is the sum of revenue in GL Entry for the dates (tested).

#### Profit Before and After Shared Costs (RPT-02)

ImedERP > Financial Reports > *Profit Before and After Shared Costs*. Dates and Business, as above.

The shared premises' expenses (`مصروفات المقر المشتركة`) are split when they are posted. The Allocation Rule
makes a Cost Center Allocation, and ERPNext writes each business's share straight into the ledger, with no
trace of the shared cost center. The Expense still names it, on its Journal Entry row, and so does a Purchase
Invoice line. `business_figures.allocated()` reads those documents back. For each account and business, it
takes what the ledger holds less what the document itself put there; what is left came from the shared line.
Nothing is recalculated from percentages, and nothing is posted.

| Column | |
|---|---|
| Revenue | the business's own |
| Direct Expenses | the ledger's expenses less the share of the shared premises |
| Shared Costs Before Allocation | on the shared premises' row only: everything they spent in the period, split or not |
| **Profit Before Allocation** | Revenue − Direct Expenses (shared premises' row: − their expenses) |
| Shared Costs Allocated | the business's share, as posted |
| Shared Costs Not Allocated | on the shared premises' row: what is still on it in the ledger (no rule covered its date) |
| **Profit After Allocation** | the ledger's profit: Revenue − Direct − Allocated (shared premises' row: − not allocated) |

Each expense is in one column of one row, so both profit totals equal the ledger's profit for the period. The
report checks this on every run (*Agrees with the Ledger*). With one business chosen, the two differ by
exactly its share.

If a shared expense was not split, the report says that profit after allocation is **incomplete** and by how
much. The site's first rule starts on 1 Nov 2026, so earlier shared expenses stay unsplit. Nothing is made up
for them.

#### Outstanding Receivables (RPT-05)

ImedERP > Financial Reports > *Outstanding Receivables*. What customers still owe, in three parts, each with its
subtotal:

| Part | What | Source |
|---|---|---|
| Invoiced | Each submitted Sales Invoice with something still owed: amount, paid, outstanding, Unpaid / Partly Paid, days overdue, and the booking it was made for | ERPNext's Outstanding Amount, which already takes off payments, advances applied (a booking's deposits) and credit notes against it. A paid invoice is not listed and a cancelled one does not count |
| Customer Credit | Money a customer has with us, not yet set against an invoice: a payment or deposit not applied, a credit note not applied | Payment Entry `unallocated_amount`; a return's negative outstanding |
| Not Invoiced | A booking, not cancelled or a no-show, with no invoice yet and something left to pay: price, deposits, remaining | The booking's own figures. Not a receivable in the accounts: listed apart, not added to what is owed |

A booking and its invoice are one debt. Once invoiced, a booking appears only as its invoice row. Before that,
its deposits are in its Amount Paid, not again under Customer Credit.

Filters: Business, Customer, From / To Date (the document's date), Payment Status (Unpaid, Partly Paid,
Overdue) and Show (one part). The Invoiced subtotal equals the customer's Payment Ledger for those invoices
(tested).

Doctors' platform fees and books debts are not here; they are on Platform Fees and Doctor Debts (RPT-10).

#### Requirements and where they are

| Requirement | Done by | Tested by (`test_owner_reports.py`) |
|---|---|---|
| 5.1 Owner Dashboard: yesterday by business | `owner_yesterday.money`, dashboard card | `test_each_business_with_approved_documents_only`, `test_yesterday_is_the_calendar_day_before` |
| 5.1 paper and counters | `owner_yesterday.printing` | `test_printing_warns_instead_of_showing_zero`, `test_no_machine_is_not_configured` |
| 5.1 halls and studio hours | `owner_yesterday.bookings` | `test_bookings_by_their_day_not_the_day_they_were_made` |
| 5.1 platform fees | `owner_yesterday.app_fees` | `test_app_fees_without_agreements_are_not_configured` |
| 5.1 integrations and last import | `owner_yesterday.systems` | `test_a_system_without_records_is_never_ok` |
| 5.1 owner only | workspace role, `check_owner`, `check_reader`, report roles | `test_only_the_owner_sees_yesterday`, `test_the_money_endpoints_refuse_a_branch_manager`, `test_the_dashboard_is_the_owner_s_workspace` |
| RPT-01 revenue by day / week / month, business, branch | `report/revenue_by_period` | `IntegrationTestRevenueByPeriod` (8 tests) |
| RPT-02 profit before and after the shared costs | `report/profit_before_and_after_shared_costs`, `business_figures.allocated` | `IntegrationTestProfitBeforeAfterSharedCosts` (6 tests) |
| RPT-05 outstanding receivables, unpaid bookings and sales | `report/outstanding_receivables` | `IntegrationTestOutstandingReceivables` (7 tests) |

**Limits**

- The split of a shared expense is read back from Journal Entries (every Expense) and Purchase Invoices. A
  shared line on another document (a Payment Entry deduction, say) would show as the business's direct
  expense.
- A Journal Entry with two lines on the same account and business, one of them shared, is read as one.
- The booking import keeps no log (known issues 17–19). Its card says *Not configured* until it does.

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

## Tests

Three kinds:

- **Integration tests** (below): each doctype's and module's, rolled back; 507 on 21 Oct 2026. Run them behind the
  leak guard (`scripts/run_tests.sh`).
- **Two sessions at once** (`setup/concurrency_check.py`): a transfer confirmed twice, two payouts, two subscriptions,
  two day screens, two bookings of one hour, each from two database connections at the same moment. It commits its
  records, so it runs only on a throwaway copy of the site (it refuses `frontend`):
  `docker exec frappe_docker-backend-1 bench --site restore-test execute imed_erp.setup.concurrency_check.run`.
- **Browser tests** (`tests/e2e/`, Playwright): each role's logins, pages, refused calls, branch isolation, Arabic,
  phone width and the main workflows, on a throwaway copy too; see `tests/e2e/README.md`.

Each doctype has integration tests next to it; the expense reminders have their own module:

```bash
docker exec frappe_docker-backend-1 bench --site frontend set-config allow_tests true
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_test_records  # first: catches a missing IGNORE entry before it commits _Test records
# or, the guard first and the rest only if it passes:
scripts/run_tests.sh --app imed_erp
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Expense"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Recurring Expense"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Allocation Rule"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Doctor Agreement"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Book Edition"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Doctor Ledger Entry"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "App Course"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "App Subscription"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Platform Fee Schedule"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_doctor_accrual  # card A8: 3 copies at 80 -> 240, twice -> 240, cancelled -> 0, the balance follows
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_doctor_statement
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_doctor_debts
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_doctor_requirements
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_paper_stock
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_stock_count
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_stock_count_variance
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_paper_use
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_treasuries
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_buying
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_expense_reminders
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_warehouses_items
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_material_issue
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_damaged_stock
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_customers
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_sales_cancellation
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_edition_sales
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_doctor_reports
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_app_import
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_opening_stock
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_booking
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_booking_pricing
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_xstudio_sync  # XStudio read-only sync against a stand-in of its API (docs/XSTUDIO_SYNC.md)
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Printing Machine"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Daily Counter Reading"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_daily_printing
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_owner_reports  # 5.1, RPT-01, RPT-02, RPT-05
```

They run on the company's real cost centers, accounts and categories, and everything they create is
rolled back at the end.

> **Before adding a Link field to a doctype that has tests**, add the linked doctype to
> `IGNORE_TEST_RECORD_DEPENDENCIES` at the top of its test file. Otherwise Frappe builds ERPNext's own
> "_Test ..." records for it and **commits** them to the site: on 4 Oct 2026 one missing entry (User)
> left 21 test companies, about 2,100 accounts, 12 users and a 1,000,000 EGP stock entry on the real
> company, which had to be removed by hand. Take a backup first (`bench --site frontend backup`) and
> copy it out of the container: `bench backup` deletes backups older than a day.
