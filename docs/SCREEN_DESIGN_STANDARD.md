# Screen Design Standard — IMED ERP

How to build any screen (Doctype form) in this project so it is **simple, consistent, and shows each
person only what their job needs**. **Sales Invoice** is the reference implementation; **Expense** is a
second example.

The test every screen must pass, from the user's side:

> *"I'm a normal staff member opening the system for the first time — do I understand what to do?"*
> *"I'm the accountant — is the financial detail I need here, without the screen being full of clutter?"*
> *"I'm the manager — can I see the state of the company and the branches easily?"*

If the answer is no, simplify the screen.

**Scope — read first.** This is a **UI / UX** standard. It only *hides, collapses, orders, and labels*
what is already there. It **never** deletes a field, changes the database, changes accounting, blocks
saving, or invents business rules. Hiding is reversible in one line.

**Hiding is not security.** Removing a field from a form only declutters that view; the data is still
reachable through the API, lists, reports and other forms. Real per-role access control is server-side
and already set up in `setup_users.py` (Role Permissions + User Permissions + the financial permissions
matrix). This standard is the *presentation* layer on top of that.

---

## 1. Roles in this project (the real ones)

Use only the roles that exist (`setup_users.py`, README §"Roles and the permissions matrix"). Do not
invent roles or personas.

| Business role | Real ERPNext role(s) | Who |
|---|---|---|
| General Manager | **Super Admin** (+ System Manager, Accounts Manager) | Owner |
| Accountant | **Accountant** (+ Accounts User, Accounts Manager) | Accountant |
| Branch Manager | **Branch Manager** (+ Sales User, Accounts User; + Stock User in libraries) | Nour, Gilan, Menna, Raghad, Sara — each restricted to their own cost center/warehouse |
| HR | **HR** (+ HR Manager) | HR user |
| CRM Staff | **CRM Staff** | *(role exists, no user yet)* |

There is **no plain "Employee" self-service role** and no employee-linked self-service users. Any
"My Expenses / My Leave / My Profile" experience would need the HR module, employee-linked user
accounts, and a self-service role first — see §13 (**Needs Business Confirmation**). Do not build it on
a guessed role.

## 2. Role-based UI (progressive disclosure by role)

A screen should present the same record differently depending on who opens it — **as decluttering, not
as access control** (see Scope). Rule of thumb:

- Everyone sees the **core business fields** of the record.
- **Accounting / GL detail** is shown only to accounting roles; branch staff get the simpler view.
- **Advanced / rarely used** blocks are collapsed for everyone (reachable in one click), not deleted.

Implement with the helper's `restrict` option (§10), using the shared role groups
`imed.screen.ROLE_GROUPS` (data, defined once). The exact visibility line for each screen is a UX
choice — sensible defaults are used and flagged in §13 where the business should confirm the boundary.

### Role / Screen matrix

Functional guide — what each role should *see first* vs. what should stay hidden/collapsed. Navigation
(which workspaces/screens a role lands on) is governed by Frappe permissions and the home-screen quick
actions (`imed_home.js`, shown per permission); fuller role-based navigation menus are a workspace
config task (§13), not a Client Script one.

| Role | Main screens | Should see | Hidden / collapsed |
|---|---|---|---|
| **General Manager** (Super Admin) | Everything; Owner Dashboard, all branches | Full business overview, all financial & accounting detail | Only raw system/technical fields |
| **Accountant** | Sales, Purchases, Expenses, Accounting, financial reports | All financial & accounting detail (GL, journal, dimensions) | HR internals; raw system fields |
| **Branch Manager** | Their branch's sales & expenses (own cost center) | Day-to-day business fields | GL/journal detail (collapsed/hidden), other branches (enforced server-side by User Permissions) |
| **HR** | Employees, Attendance, Leave, Payroll, HR reports | HR information | Accounting internals |
| **CRM Staff** | *(to be defined)* | *(to be defined)* | *(to be defined)* |

## 3. Field ordering & logical layout

Order fields by the user's **workflow**, not ERPNext's default order. The hierarchy, adapted per
Doctype (do not force the same literal order everywhere):

1. **Primary / essential** — what identifies the record (party, date, the one thing it is "about").
2. **Main business information** — the core choices the user makes (items, category, activity).
3. **Financial values** — amounts, quantities, totals.
4. **Related account / activity** — cost center, linked business.
5. **Optional information** — secondary party, free-text.
6. **Notes / attachments** — receipts, files, remarks.
7. **Technical / system fields** — company, derived accounts, journal entry, `amended_from`: a
   **collapsed** section near the bottom; mostly read-only and auto-filled.

Target layout for a document screen (e.g. Sales Invoice): **Basic info → Items → Totals → Advanced
(collapsed)**.

**Where order is set:** the Doctype definition — `field_order` in the `.json` for our own doctypes, or
**Customize Form** (a Property Setter) for standard doctypes. **Not** in JavaScript; the helper does
not reorder (it would fight the framework and break on upgrades).

## 4. Fields to hide (unused / default ERPNext noise)

Our business is **one Egyptian company, EGP, domestic, no e-invoicing**. Hide the generic fields we
never use (hide, never delete):

| Group | What it is | Why |
|---|---|---|
| **Tax** | taxes & charges tables, tax category, tax withholding (TDS), tax totals | No VAT/withholding charged on these screens today. |
| **ZATCA / Saudi** | ZATCA status, UUID, KSA e-invoice QR | Saudi e-invoicing; we are in Egypt. |
| **International** | currency, exchange rate, price-list currency, shipping rule/incoterm, shipping/dispatch address | Everything is EGP and domestic. |
| **Company-currency duplicates** | `base_*` totals | Identical to the transaction values in a single-currency company. |

**Rule:** confirm a field is unused before hiding it. **If uncertain, leave it visible and record it in
§13** rather than guessing. These groups are predefined by name in the helper (§10).

## 5. Simplify ERPNext terminology (business-friendly labels)

Some ERPNext labels are unclear to a first-time user. Relabelling is allowed **only** via Customize
Form (a Property Setter) — never hardcoded in JS, and never when it changes meaning. Decide per label;
when in doubt, keep ERPNext's term and flag it in §13.

| ERPNext label | Clearer label | Decision |
|---|---|---|
| "Cash/Bank Account" | "Treasury" (الخزينة) | Done on Expense, Recurring Expense and the Expense Report. |
| "Cost Center" | "Activity / Branch" | **Needs business confirmation** — "Cost Center" appears across many screens; relabel consistently or not at all. |
| "Grand Total" | keep | Clear enough; translated in Arabic. |
| "Posting Date" | keep | Standard accounting term. |

Arabic labels come from translations (§7), not from relabelling. Relabel the English only where it adds
clarity for English users (Administrator).

## 6. Progressive disclosure (summary)

- **Core fields** visible immediately.
- **Advanced** blocks **collapsed** (one click away), via `collapse` / `collapse_on_new`.
- **Role-specific** detail hidden for roles that do not need it, via `restrict` (§2, §10).
- Nothing is removed from the database; everything stays reachable.

## 7. Arabic / RTL

- **Direction:** RTL for Arabic users (set per user in `setup_regional.py`). The theme uses **logical
  properties** (`inline-start`/`inline-end`) so the UI mirrors correctly. Do not add hard `left`/`right`.
- **Keep LTR content LTR:** numbers, currency, dates, IDs, emails, URLs. Frappe handles this per field
  type — do not override.
- **Labels:** Arabic comes from translations, never hardcoded. App strings live in
  `apps/imed_erp/imed_erp/translations/ar.csv`; common terms resolve from Frappe's built-in Arabic.

## 8. Font and sizes

- **Font:** **IBM Plex Sans Arabic** (bundled, SIL OFL) for Arabic; **Inter** for Latin — set by
  `css/imed_fonts.css` + `--font-stack`. **Do not add Cairo or any new font dependency;** the project
  already has an established offline Arabic font.
- **Sizes:** use the theme's type tokens, never arbitrary px: `--text-sm` labels (~13px), `--text-base`
  body/inputs (~14px), `--text-base`/600 section headings, larger page title. Consistency = reuse tokens.
- **Spacing (airy forms):** every form gets one calm rhythm from the theme (`imed_theme.css §19`): more
  space between fields, clearer labels, roomier inputs, and clear gaps between sections — applied to all
  forms at once, no per-screen work. This is the global lever for "simpler, easier to read" screens; do
  not add ad-hoc spacing per screen. The child-table grids keep Frappe's compact layout on purpose.

## 9. Buttons

Follow Frappe's native layout — do not redesign the navigation. The theme (`imed_theme.css §5`) enforces:

- **Primary (Save)** — solid teal `.btn-primary`, top-right; the one obvious main action.
- **Secondary** — outlined `.btn-default`/`.btn-secondary`; never compete with the primary.
- **Cancel / close** — quiet secondary.
- **Destructive (Delete / Cancel doc)** — red `.btn-danger`, sparingly.

Avoid adding custom buttons that compete with Save.

## 10. Status colours

Use the theme's semantic colours (`imed_theme.css §1, §8, §11`) — never ad-hoc colours. Same meaning →
same treatment:

| Meaning | Colour | Indicator |
|---|---|---|
| Success | green | `green` |
| Warning | amber/orange | `orange` / `yellow` |
| Error / danger | red | `red` |
| Information | teal (brand) | `blue` → themed teal |
| Neutral / pending | gray | `gray` |

Use Frappe's indicator names (`frm.set_intro(msg, "orange")`, list indicators); the theme maps them.

## 11. Client Script helper (the reusable template)

`apps/imed_erp/imed_erp/public/js/imed_form_standard.js`, loaded globally by `hooks.py`
(`app_include_js`), exposes `imed.screen.apply(frm, config)`. A doctype's own `.js` is the "Client
Script": call the helper from `refresh()`, then add screen-specific behaviour.

```javascript
frappe.ui.form.on("DOCTYPE_NAME", {
    refresh(frm) {
        imed.screen.apply(frm, {
            hide_groups: ["tax", "zatca", "international"], // generic noise (absent fields skipped)
            hide: ["extra_field", "some_section"],          // screen-specific hides
            collapse: ["advanced_section"],                 // advanced-but-reachable
            collapse_on_new: ["technical_section"],         // collapse only on new docs
            restrict: [                                     // progressive disclosure by role (UX only)
                { unless: imed.screen.ROLE_GROUPS.accounting_manager, hide: ["accounting_section"] },
            ],
        });
        // ... screen-specific behaviour ...
    },
});
```

- **Generic (in the helper):** `FIELD_GROUPS` (tax/zatca/international), `ROLE_GROUPS` (the real project
  roles, as data), and the hide/collapse/restrict mechanics. No per-screen business logic lives here.
- **Screen-specific (in each doctype's `.js`):** which groups/fields/sections to hide, and which role
  rules to apply.
- Every field name is guarded (`frm.fields_dict[...]`), so the same config is safe on any doctype, and
  forms that never call the helper are unaffected.
- `restrict` is **UX decluttering, not access control** — never gate a mandatory field a role must fill.

**To apply to a new screen:** add/extend a `refresh` handler in that doctype's `.js`, call
`imed.screen.apply(...)`, register it in `hooks.py` (`doctype_js` for a standard doctype), and set field
order/labels in the definition (§3, §5). For a standard doctype, add the file to `doctype_js`.

## 12. UX consistency checklist

Every screen: same section structure where it applies · same terminology · same button/action hierarchy
· same status colours · same RTL behaviour · same Arabic font · required fields clearly marked · no
unnecessary fields · no duplicate information · advanced detail kept out of the primary workflow.

## 13. Needs Business Confirmation

Do not guess — confirm these with the business:

| Topic | Question | Status |
|---|---|---|
| **Employee self-service** | There is no "Employee" role or employee-linked users. Should staff get a self-service view (My Expenses / My Leave / My Profile)? That needs the HR module, employee users, and a self-service role set up first. | **Not configured — needs decision** |
| **Role visibility boundaries** | The exact line for "who sees accounting detail" (we default to Accountant / Accounts Manager / Super Admin / System Manager; branch staff get the simpler view). Confirm per role. | **needs confirmation** |
| **`tax_id` / `company_tax_id`** (Sales Invoice) | Tax-registration numbers — may be legally required on Egyptian invoices. Left **visible**, not hidden. | **needs confirmation** |
| **Relabelling "Cost Center"** | Rename to "Activity / Branch" for clarity? It appears on many screens; must be consistent or not at all. | **needs confirmation** |
| **HR screens** | HR role exists, but Attendance / Leave / Payroll screens are standard ERPNext and not yet tailored. Tailor them? | **needs confirmation** |
| **CRM Staff** | Role exists with no user and no defined screens. | **needs confirmation** |
| **Shared expense distribution** | Auto-distribution of shared costs across businesses is **not** implemented; today a shared cost is booked to the `Center Shared Expenses` cost center. Allocation basis is a business decision. | **needs confirmation** |

---

## Worked example — Sales Invoice (reference implementation)

Standard ERPNext doctype, attached via `hooks.py` `doctype_js` → `public/js/sales_invoice.js`, which
reuses `imed.screen.apply` (no bespoke code). Goal: a short, EGP-only invoice following **Basic info →
Items → Totals → Advanced (collapsed)**.

- **Hidden — Tax:** `taxes_section` (tax template, shipping rule, incoterm, named place), the taxes
  table (`section_break_40`), tax totals (`section_break_43`), `sec_tax_breakup`, Tax Withholding
  (`section_tax_withholding_entry`). *Why:* no VAT/withholding charged today.
- **Hidden — Currency / international:** `currency`, `conversion_rate`, `price_list_currency`,
  `plc_conversion_rate`, shipping/dispatch addresses. *Why:* EGP and domestic. The four currency fields
  are mandatory **but auto-filled** server-side (EGP, rate 1), so hiding them cannot block saving —
  verified by inserting and deleting a draft. `selling_price_list` stays visible.
- **Hidden — company-currency duplicates:** `base_total`, `base_net_total`, `base_totals_section`.
- **Collapsed (progressive disclosure):** `accounting_dimensions_section` (Cost Center / Project),
  `additional_discount_section` — reachable in one click, not primary.
- **Kept (needs confirmation):** `tax_id` / `company_tax_id` (§13).
- **On screen:** the tax blocks, currency/exchange fields, shipping addresses and duplicate
  company-currency totals disappear; advanced blocks are collapsed. What remains: customer & date →
  items → totals (Grand Total, In Words).
- **Preserved:** saving, totals, and the server-side library income-account logic all still run
  (exercised by the save test). UI hiding never touches server validation.

## Worked example — Purchase Invoice (buying paper and materials)

Standard ERPNext doctype, attached via `hooks.py` `doctype_js` → `public/js/purchase_invoice.js`, which
reuses `imed.screen.apply`. The library buys directly (no purchase order or receipt first): one invoice
with **Update Stock** receives the paper into the store and records what is owed (`setup/setup_buying.py`).

- **On screen:** supplier and date → Update Stock and the warehouse → items (item, quantity, unit, rate)
  → totals; **Is Paid** for a purchase paid on the spot (payment method and treasury on the Payments
  tab); the payment terms (`نقدي` / `آجل 30 يوم`) alone on the Terms tab; the supplier's invoice attached
  from the sidebar.
- **Hidden:** the `tax`, `zatca` and `international` groups; currency and price list
  (`currency_and_price_list`); the tax sections (`taxes_section`, `section_break_51`, `totals`,
  `sec_tax_breakup`, `section_tax_withholding_entry`); company-currency duplicates; subcontracting and
  rejected goods (`is_subcontracted`, `supplier_warehouse`, `rejected_warehouse`,
  `raw_materials_supplied`); pricing rules; the Address & Contact tab; Terms and Conditions text.
- **Collapsed:** `accounting_dimensions_section` (Cost Center / Project) and the additional discount.
- **Definition-time (Property Setters in `setup_buying.py`):** Update Stock is ticked on a new invoice,
  and the unit (`uom`) is a column of the items table next to the quantity.

## Worked example — Expense (`imederp/doctype/expense`)

A lean custom doctype with no tax/currency noise, so here the standard is about **progressive
disclosure by role**, not hiding noise (`expense.js`).

- **Everyone sees** the business fields (in `expense.json` order): posting date → activity → category →
  amount → treasury → supplier → description → receipt.
- **Accounting section** (company, expense account, journal entry — all read-only, auto-filled on save):
  - **Branch staff** (no accounting-manager role) → the section is **hidden**: a simpler screen.
  - **Accountant / managers** → the section is shown, **collapsed on a new expense**.
  - Safe because these fields are never user-entered; the accounting logic is untouched.
- **Note:** branch managers also hold *Accounts User* but not *Accounts Manager*, so by the default
  boundary they get the simpler view (see §13 to confirm this line).
- **Arabic / RTL, font, buttons, colours:** inherited from the theme and translations; no overrides.
