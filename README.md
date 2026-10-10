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
                        Expense Settings, Allocation Rule, Printing Cost Settings,
                        Inter Business Transfer (and its report);
                        shared rules: treasuries.py (each business's cash box), no_delete.py,
                        period_lock.py (closed months), library_revenue.py, expense_reminders.py
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
| Expense | full | create, edit, request approval (no cancel/delete); every expense is submitted only once the owner approves it |
| Inter Business Transfer | full | Accounts User: read only. Branch Manager: create, edit, submit (no cancel/delete) |
| Expense Category | full | read only |
| Recurring Expense (monthly bills) | full | read only (so the bill can be picked on an expense) |
| Expense Settings | full | read only |
| Allocation Rule | full | read only |

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
| Accountant | Accountant | Accounts User, Accounts Manager |
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
- Branch managers make regular journal entries too (create and submit; no cancel, amend or delete). They
  only read month-end closing (Accounting Period), the chart of accounts and the split of the shared
  premises' expenses (Cost Center Allocation), which ERPNext's Accounts User could otherwise change.
  The accountant changes these three but never deletes them; only the owner does.
- A branch manager pays expenses, sends transfers and makes journal and payment entries only from their
  own business's cash box or the
  group's InstaPay / Vodafone Cash wallets (`imederp/treasuries.py`); Owner and Accountant may use any.
- Branch managers see only their own cost center (and warehouse); Owner and Accountant see all.
- Employees: Super Admin and HR manage them, Accountant can view them.
- Prices (Item Price): only the owner edits them. The accountant's price changes need approval (SEC-02),
  not built yet. Customers: the owner, the accountant and branch managers add them.

**Expense Approver** is not a requirement role but a marker the code checks: its holders approve or
reject expenses (EXP-06). Only the owner has it.

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
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_recurring_expenses.py").read(), {"frappe": frappe})
exec(open("/home/frappe/frappe-bench/apps/imed_erp/imed_erp/setup/setup_allocation_rules.py").read(), {"frappe": frappe})
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
| `setup_core.py` | Run first. On a new site it completes the setup wizard (company MMG, EGP, fiscal year Sep–Aug). Then: cost center tree, warehouses (Mawasah, the main one, with its raw materials, doctors' editions and damaged stock; Azarita's raw materials and editions as a separate branch; the center's office supplies), UOMs (`ورقة` sheet, `رزمة` ream = 500 sheets, `كرتونة` box = 5 reams = 2500 sheets, `ساعة` hour) and items. Paper (item group `ورق`) is stocked in sheets, bought by the box and valued at moving average (see *Paper units and cost* below); the hall and studio hours are sold by the hour. Runs `setup_coa.py` itself, after the warehouses. |
| `setup_regional.py` | Regional settings: EGP currency (symbol `EGP`, 2 decimals), fiscal years 2026-2027 and 2027-2028 (1 Sep – 31 Aug, linked to the company; a wrongly dated year with nothing posted in it, e.g. the Jul–Jun one the browser wizard creates, is replaced), Arabic interface for users / English for Administrator, rounded totals off, MMG Sales Invoice as the default invoice print format, date format `dd-mm-yyyy`, 24-hour time, number format `1,234,567.89`, commercial (half-up) rounding, week starting Saturday. |
| `setup_users.py` | The requirement roles (Super Admin, Accountant, Branch Manager, HR, CRM Staff) and the Expense Approver role, 8 users (`name@imed.local`), User Permissions that restrict each branch manager to their own cost center and warehouse, and the permissions matrix (requirements §3.2) on financial documents. Declarative: re-running also corrects drift (name, enabled flag, extra roles, stale User Permissions). Prints a summary table. |
| `setup_arabic_names.py` | Renames the company's accounts, cost centers, warehouses, item groups, UOMs (Ream, Box) and item names from English to Arabic, updating every link. `setup_core.py` runs it right after the company exists. Leaves the company name, the `All Item Groups` root and the `Nos` UOM in English (ERPNext uses them by name). Screen texts of the app's own doctypes and reports are translated in `imed_erp/translations/ar.csv`. |
| `setup_coa.py` | Chart of accounts from the posting rules document (v2.0, section 2): treasuries (one per business, including the BA Plus app's), one revenue account per business, costs and expenses, doctors' and lecturers' balances, the inter business current account, and one stock account per library and kind, linked to its warehouse. Reuses the accounts ERPNext already ships (rent, salaries, utilities, ...) and deletes the old Books / Printing Revenue accounts. Can also be run on its own. |
| `setup_library.py` | Libraries (LIB). The five inventory groups `ورق`, `أحبار`, `كتب وكشاكيل`, `مستهلكات` (ERPNext's own Consumable group) and `خامات تجليد`, with A4 paper in `ورق`; makes `منتجات المكتبات` a parent group with `كتب وكشاكيل` (holding `كتب` and `مذكرات`) and `خدمات المكتبات` under it; the Author field on Item; the non-stock services COPY-SVC, PRINT-SVC, BINDING-SVC (moved into `خدمات المكتبات`); the stock items BOOK and MEMO; item defaults (revenue `إيراد مكتبة المواساة`, cost center `مكتبة المواساة`, warehouse `إصدارات الأطباء — المواساة`); one POS Profile per library, which gives each sale its own warehouse and cost center; a cash payment method for the halls, the studio and the app, each into its own cash box. Books and memos are listed in `LIBRARY_ITEMS` at the top (one generic item each until the catalogue is known). Creates no account, cost center or warehouse: a missing one is printed as `WAIT`. Idempotent. |
| `setup_dashboard.py` | Number Cards, Dashboard Charts and the Owner Dashboard workspace (deleted and recreated each run), in the theme's colours, plus the branding settings the theme needs: app name, logo (Navbar Settings), launcher icon style, Owner Dashboard icon. |
| `verify_setup.py` | Read-only. Prints found/expected counts and flags anything missing or misconfigured. |
| `verify_users.py` | Read-only. For every `@imed.local` user: their restrictions, the cost centers they can see, and yes/no for each right in the permissions matrix, marked PASS/FAIL against the matrix. |
| `check_financial.py` | Test, rolled back afterwards. Checks EGP on the company and Global Defaults, the fiscal year, `dd-mm-yyyy` dates, number format, that a printed invoice (HTML and PDF) shows `EGP` and not `£`, and that a closed accounting period blocks invoices and journal entries (CORE-09). |
| `check_library.py` | Test, rolled back afterwards. Creates a test book and memo, receives them in Mawasah's store, issues books to Azarita, then sells through each library's POS Profile and through a plain sales invoice, and checks that the revenue account (Azarita's sales moved to `إيراد مكتبة الأزاريطة` by `imederp/library_revenue.py`), cost center and warehouse were filled in without being typed. |
| `setup_expenses.py` | Expense categories (EXP-07): the tree `كل المصروفات` with `الإيجار`, `المرافق`, `الرواتب والأجور`, `الخامات والمستهلكات`, `الصيانة`, `التسويق`, `الهالك والتالف` and `الاشتراكات والسيرفرات` under it, each linked to the expense account of the same name (or the English name ERPNext ships it with, before `setup_arabic_names.py`). The monthly bills sit in two groups: `المرافق` (electricity, water, internet, gas, and rent, which keeps its own account) and `الاشتراكات والسيرفرات` (the app's server and AI subscriptions). Creates no account: a missing one is printed as `WAIT`, and re-running links it once it exists. Idempotent. |
| `setup_recurring_expenses.py` | The first monthly bills (EXP-05): rent, electricity, internet and gas of the center premises with their expected amounts; rent, electricity and internet of each library, and the app's server and AI subscriptions, without amounts. Run after `setup_expenses.py`. Fills the list once; from then on it is kept from the Recurring Expense screen. A bill already listed for the same business is left as is. Idempotent. |
| `setup_allocation_rules.py` | Submits the first allocation rule (EXP-03/04): expenses on the shared premises are split 60% halls / 40% studio from 1 Nov 2026, as agreed with the owner. Later changes are new rules from the Allocation Rule screen. A submitted rule for the same cost center and date is left as is. Idempotent. |
| `close_period.py` | Month-end close (CORE-09). Creates an Accounting Period for a finished month with ERPNext's posting document types and the app's own (Expense, Inter Business Transfer, Doctor Ledger Entry, App Subscription, Printer Reading, listed in `period_closing_doctypes` in `hooks.py` and checked by `imederp/period_lock.py`, on save and on cancel; a doctor's ledger has no company and uses the default one) closed, so nothing dated in that month can be posted, edited or cancelled. Set `MONTH = "YYYY-MM"` at the top, or leave it empty for last month. Run it only at month end: it changes the books. |

`setup_core.py`, `setup_regional.py`, `setup_arabic_names.py`, `setup_coa.py`, `setup_users.py`, `setup_expenses.py`, `setup_recurring_expenses.py`, `setup_allocation_rules.py`, `verify_setup.py` and `verify_users.py` are idempotent, so they can be re-run
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
  Overdue Reminder Every (Days)**, default 2). A rejected draft is not reminded; one waiting for the
  owner's approval reminds the owner instead, on the same days.

Both numbers are in **Expense Settings**. The drafts and the reminders come from one daily scheduler
job, `recurring_expense.run_daily` (`hooks.py`), so the month's drafts exist before the reminders look
for them. Reminders and approval notices go through `notification_service.py` (CORE-10), which also
skips a notification a user already has for the same document, so a second run the same day adds nothing.

### Expense approval (EXP-06)

**Every expense** is paid and posted only once the owner approves it, whatever its amount (owner's decision
of 8 Oct 2026). There is no threshold, and Expense Settings (reminder days) can be changed by the owner
only, so nobody else can switch the approval off.

1. The accountant saves the expense with its receipt and clicks **Request Approval** (Submit is refused
   while the expense needs approval). The owner receives an in-app alert.
2. The owner opens it and clicks **Approve**, which submits and posts it, or **Reject**, with an optional
   reason. The person who asked for the approval is notified either way (not the creator: monthly
   drafts are made by the scheduler).
3. A rejected expense is closed for good: it can no longer be saved or submitted. If the payment is
   needed after all, a new expense is made.

Changing the amount, category, business, treasury or receipt after a request or an approval clears it,
so the expense as changed needs approval again.
The owner's own expenses are approved as he submits them. Approval is by the
**Expense Approver** role, checked on the server, so it also holds for the API. The form shows the
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

### Paper units and cost

Paper is bought by the box, used by the sheet and stocked in sheets:

| UOM | Sheets |
|---|---|
| `ورقة` (sheet, whole numbers only) | 1 (stock UOM) |
| `رزمة` (ream) | 500 |
| `كرتونة` (box) | 2,500 (default purchase UOM) |

Every item in the item group `ورق` is valued at **moving average** and bought by the
box; `setup_core.py` applies both to any paper item added to the group later. Moving average means every
sheet in a store costs the same, the average of what was paid: a box at 650 then one at 700 make every
sheet 0.27. Two boxes at 650 come in as 5,000 sheets at 0.26 each, 1,300 in all.

A purchase takes the conversion factor from the item. If the item has no row for the chosen UOM, ERPNext
uses a factor of 1 and a box comes in as one sheet. ERPNext also **empties the item's UOM table whenever
its stock UOM changes**, so `setup_core.py` puts the factors back on every run (`ensure_conversions`), and
`verify_setup.py` reports a missing or wrong one. ERPNext refuses to change the stock UOM or the
valuation method once stock has moved; the script then only warns.

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
transfer of more than the source holds (negative stock is off). Moving goods to the damaged store is the
same kind of transfer.

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

To reopen a closed month: Accounting > Accounting Period > open the month > untick **Closed** on the
document types to allow (or tick **Disabled** to reopen everything). Only Owner and Accountant can. A
document linked to a closed academic period cannot be saved either.

**Payment methods.** Each library's POS takes cash on its own method, `نقدي — مكتبة المواساة` /
`نقدي — مكتبة الأزاريطة`, which posts to that library's cash box (ERPNext's `Cash` posts to the company's
main treasury), plus `InstaPay` and `Vodafone Cash`, which post to the group's wallets (`setup_library.py`). The other businesses take cash the same
way into their own cash boxes: `نقدي — قاعات Imed` (the center's), `نقدي — استوديو X` and `نقدي — تطبيق BA Plus`.

**Doctors' editions and the app.** An edition's price per copy is built on what the doctor asks for each
copy (from his agreement, as a fixed amount), with the library's costs and profit on top:

> (paper + ink + overheads + profit) per sheet × sheets per copy + binding + marketing (optional) + the
> doctor's amount.

The price is not rounded (owner's decision, instead of DOC-28's rounding). Another price can be set by
hand, higher or lower (to sell more): the difference is added to or taken from the library's profit, never
the doctor's amount, and a price below the cost of a copy is saved with a warning.

The rates change several times a year, so the owner and the accountant set them on **Printing Cost
Settings** (waste, ink, overheads and profit per sheet; binding per copy), and every change is recorded.
The paper itself is the moving average price paid for A4 paper in the library's raw materials store, from
the boxes bought, plus the waste rate. An edition takes the rates while it is a draft, any of them can be
changed for that edition only, and they are kept once it is submitted, so a later price change never
touches an approved edition (DOC-24/25). It cannot be submitted before the library has a paper price. Marketing is an optional amount per copy that
goes to the library, not to the doctor.

An App Subscription records the student and the platform fee due from the doctor only: the course is paid
by the student to the doctor directly and is not recorded (APP-05, v1.2). Editions belong to books
agreements and subscriptions to app agreements.

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

## Tests

Each doctype has integration tests next to it; the expense reminders have their own module:

```bash
docker exec frappe_docker-backend-1 bench --site frontend set-config allow_tests true
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Expense"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Recurring Expense"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --doctype "Allocation Rule"
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_paper_stock
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_expense_reminders
docker exec frappe_docker-backend-1 bench --site frontend run-tests --module imed_erp.imederp.test_warehouses_items
```

They run on the company's real cost centers, accounts and categories, and everything they create is
rolled back at the end.

> **Before adding a Link field to a doctype that has tests**, add the linked doctype to
> `IGNORE_TEST_RECORD_DEPENDENCIES` at the top of its test file. Otherwise Frappe builds ERPNext's own
> "_Test ..." records for it and **commits** them to the site: on 4 Oct 2026 one missing entry (User)
> left 21 test companies, about 2,100 accounts, 12 users and a 1,000,000 EGP stock entry on the real
> company, which had to be removed by hand. Take a backup first (`bench --site frontend backup`) and
> copy it out of the container: `bench backup` deletes backups older than a day.
