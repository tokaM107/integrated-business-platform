# The AI assistant (read-only)

A chat window on every page that answers questions about the business from the live ERP ("إيه رصيد خزنة الأزاريطة؟",
"كام حجز بكرة في القاعات؟"). It reads only: it cannot create, change, delete, submit or post anything, and every read
runs as the user who asks, with that user's own permissions. Who may open it: Super Admin (the owner) and System
Manager (developers), `assistant/api.py`.

## Architecture (`apps/imed_erp/imed_erp/assistant/`, reviewed 2 Nov 2026)

```
assistant/
  api.py                 endpoints: access, rate limit, saved chats, send_message (thin)
  service.py             one question for one request: model + tools of the request + memory -> Orchestrator
  core/        context.py (RequestContext), interfaces.py (Protocols), orchestration.py, prompts.py, exceptions.py
  registry/    businesses.py (integrations from the `assistant_businesses` hook only), tools.py (per-request ToolRegistry)
  businesses/  imed.py (this app's integration), sidebar.py (a navigation adapter the integration uses)
  tools/       base.py (the guard), dashboard.py, reports.py, records.py, ledger.py
  memory/      chat_memory.py (ChatStore + ChatMemory), request_memory.py (unsaved conversations)
  providers/   base.py (the model port + OfflineProvider), gemini.py, claude.py
```

Layers depend downward only: `core/` imports nothing above it. The orchestrator takes a Completer (one model call), a
ToolCatalog and a ConversationMemory. Providers are pure model ports (`complete`, optionally `transcribe`) and know
nothing of tools or memory. `service.py` is the one place they are put together.

Flow of a question: `api.send_message` builds the RequestContext and stores the user's turn (saved chat); the service
builds the request's tools from the registered integrations, picks the memory, and runs the orchestrator: fold older
turns into the chat's summary when due, the **planner** (one model call, JSON out) lists the reads, the **executor**
(no model) runs them through the guard, the **synthesizer** (one model call) answers from the compact results. One
re-plan at most: two model calls a question, three at most, one for a question that needs no data.

## Businesses and where their data comes from

The registry knows no business, no app and no sidebar. Integrations register in their own app's `hooks.py`:

```python
assistant_businesses = ["my_app.assistant.integrations"]   # a callable: f(context) -> list[BusinessIntegration]
```

`BusinessIntegration` (`core/interfaces.py`): `key`, `label`, `businesses(context)`, `doctypes(context)`,
`reports(context)`, `workspaces(context)`, `tools(context)`, `prompt_notes(context)`. An object that does not fulfil
it is refused; two tools with the same name are refused, so one integration can never replace another's read. Its own
tools implement `Tool` (`name`, `spec(context)`, `run(arguments, context)`) and run under the same guard as the
common ones. The orchestrator, the API, the memory and the providers do not change for a new business (shown by
`test_a_new_business_plugs_in_through_the_hook_with_its_own_tool_rules_and_permission`).

This app's integration (`businesses/imed.py`), registered like any other:

| Information | Source, read at request time |
|---|---|
| Business units | the company's leaf **Cost Centers** the user may see (the group's domain model: a business is a cost center) |
| Readable DocTypes, Reports, Workspaces | what this app's sidebar gives its users (`businesses/sidebar.py`), each checked against the user's own permission |
| Rules of meaning (an external system's "due", "held" bookings) | the integration's `prompt_notes`, not the core prompt |
| Owner's live band | its own tool `owner_band_today`, which `owner_yesterday` refuses to anyone but the owner |
| Company, currency, language | Frappe defaults and session (`core/context.py`) |

The sidebar is used as a navigation surface (the assistant reaches only what the user could open from the screens),
not as the definition of the businesses. A test fails if a business, branch or report name is typed into the package.

## Authorization of every read (`tools/`)

| Read | Checks |
|---|---|
| Any tool | runs in a savepoint rolled back after; `frappe.db.commit` raises inside it; refusals and validation errors return as text; unexpected errors are logged (Error Log "Assistant tool failed") |
| `dashboard_cards` | only workspaces whose roles the user holds; a Custom card's method must be whitelisted (`frappe.is_whitelisted`); Document Type cards through Frappe's `get_result` (get_list, permissions) |
| `run_report` | the Report's own roles (`is_permitted`) and Frappe's report permission on its DocType; background (prepared) reports are not forced inline |
| `list_records`, `count_records` | the DocType must be in the user's surface; `frappe.get_list` (roles, user permissions); only fields at a permlevel the user has, never Password/Attach/Code/JSON fields, no filter on a field the user may not read |
| `account_balance` | GL Entry read; the Account itself readable (user permissions); of the request's company; the balance summed from the GL rows `get_list` returns, so a cost-center restriction applies |
| The request's company | one the user may read (Company user permissions, through `get_list`): the user's default, else the site's, else the only one; a default naming another company is ignored; none readable, no answer (`core/context.py`) |
| Reads not limited to one company | the app's reports (none takes a company filter), the dashboard's cards and the owner's band: only for a user who may read every company. A report that declares a company filter (its .js, or ERPNext's financial statements) runs with the request's company forced |
| Records without a company field | for a user who may not read every company, those with a Cost Center link are read for the request's company's cost centers |
| Background jobs | `frappe.enqueue` refused inside a read (a job would run later, outside the guard) |
| Saved chats | the chat's user only, in the chat window and through the desk and REST API (`has_permission`, `permission_query_conditions` in hooks.py); Administrator excepted |

## Memory

- **Saved chats** (`Assistant Chat`, `Assistant Message`): the model gets the last five messages as said plus a running
  summary of the older ones, folded by one small model call once four or more messages have left the window. Only the
  messages after the summary are read per request. An append locks the chat row; a unique index on (chat, seq)
  refuses a duplicate number. Each answer is stored with the facts it was built on.
- **Unsaved conversations** (an API caller sending the whole conversation): exactly what the caller sent, its last
  five messages, for that request only. Nothing is kept between requests, so tabs and callers never share context.
- Memory is never a source of figures: a new question reads again.

## Configuration (site config, never in git)

```
bench --site frontend set-config imed_assistant_provider gemini          # gemini, claude, or offline (unset = offline)
bench --site frontend set-config imed_assistant_api_key AIza...          # Google AI Studio key (sk-ant-... for Claude)
bench --site frontend set-config imed_assistant_model gemini-3.5-flash   # optional; the default
```

Values written before the reorganisation (`imed_erp.assistant.gemini.GeminiProvider`) are still accepted. A free
Gemini key allows 5 requests a minute per model and a daily cap; a quota or overload answer is said as such.

Deployment: `bench migrate` creates the two chat DocTypes and the unique index; the chat window falls back to sending
the whole conversation if they are missing. Rolling back the code leaves the two tables unused and harmless.

Voice: the browser reads an answer aloud (🔊). Spoken questions are recorded, but no provider transcribes audio yet.

Tests: `bench --site frontend run-tests --module imed_erp.imederp.tests.test_assistant` and `...tests.test_assistant_isolation` (two companies, five kinds of user; a fake model; nothing is sent).
