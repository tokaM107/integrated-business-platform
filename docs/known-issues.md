# Known issues and gaps

Problems known in ERPNext for our use, and features ERPNext does not have that we must build.
Each item should have a GitHub issue; put its number in the last column once created.

## Known problems

| Problem | Details | Planned | Issue |
|---|---|---|---|
| Arabic text breaks in charts | Reported in the owner demo: Arabic labels in dashboard charts do not display correctly. Charts use frappe-charts (SVG). Needs a screenshot and exact steps. | Decision and fix in week 10 | — |
| Missing / wrong Arabic translations | Parts of the interface stay in English or are mistranslated (e.g. "Amount", "Nos" on the invoice). The invoice is already fixed by the MMG Sales Invoice print format. | Full translation in week 11 | — |
| Print formats | Only the sales invoice has an Arabic format so far. | Week 11 | — |

### Issue text: Arabic text breaking in charts

> **Title:** Arabic text breaks in dashboard charts
>
> **Steps:** log in as a user with the Arabic interface, open the Owner Dashboard, look at "Revenue by
> Business" and "Stock Value by Warehouse".
>
> **Expected:** Arabic labels read correctly, right to left.
>
> **Actual:** Arabic text in the charts breaks (as seen in the owner demo). _Attach a screenshot and say
> exactly where: axis labels, legend or tooltip._
>
> **Scope:** frappe-charts SVG rendering; affects every Dashboard Chart with Arabic labels.
>
> **Plan:** decide in week 10 between (a) English labels on charts, (b) patching the chart labels with
> RTL shaping, (c) another chart library for the owner dashboard.
>
> Labels: `bug`, `CORE`, `Configuration`

## Features to build from scratch (not in ERPNext)

| Feature | Requirements | Status |
|---|---|---|
| Bookings for the studio and halls | STU, HAL (the studio booking system stays the source of truth; we read from it, INT) | Not started |
| Paper counters (printer readings, sheets consumed vs sold) | PRN | Started: *Printer Reading* doctype |
| Doctor agreements, editions and settlements | DOC | Started: *Doctor Agreement*, *Book Edition*, *Doctor Ledger Entry* |
| BA+ app subscriptions and platform fees | APP | Started: *App Subscription* |
| Integrations with the library system, studio booking system and BA+ app | INT | Not started (open questions ★ 10, 27, 28) |
| Mobile application | — | Not started |
| AI assistant (owner only, read only) | AI | Chat window, voice and permissions done; model not connected yet (`imed_erp/assistant/providers.py`) |
| Unified notifications (WhatsApp / SMS / in-app) | CORE-10 | Skeleton: `imed_erp/notification_service.py` |

## Open questions: point of sale, customers and cancelling a sale (LIB-01, CRM, ACC-06, SEC-06)

Built without a decision on these; the behaviour named is what the system does until one is made.

| # | Question | Until decided | Ask |
|---|---|---|---|
| 1 | **Customer without a phone number.** May a customer be saved with no number (walk-in buyers), or must every customer have one? | Allowed; a blank number is never a duplicate. | Owner |
| 2 | **Which numbers count for duplicates.** Only the customer's main mobile number, or every number on their contact (a second mobile, a landline)? | Only the main mobile (Customer > Mobile No). | Owner / CRM |
| 3 | **Foreign and unusual numbers.** Are there customers with foreign numbers or numbers that are not Egyptian mobiles/landlines? | Egyptian mobile (010/011/012/015) and landline accepted; foreign numbers with their country code; anything else refused. | Libraries |
| 4 | **Existing duplicates.** When `setup_customer_phones.py` lists customers sharing a number, which record stays and who merges them? | Nothing merged; the oldest keeps the number's key, the others can be edited but keep no key until someone decides. | Owner |
| 5 | **Customer category.** CRM-01 lists student / doctor. Only the doctor group (`طبيب`) exists; should a `طالب` group be made, and is it required on every customer? | Category is the customer group; no student group made. | Owner |
| 6 | **Receipt paper.** Does the counter print on a receipt (thermal) printer or on A4? | The receipt is MMG Sales Invoice (A4 layout). A narrow receipt layout needs the printer's paper width. | Libraries |
| 7 | **Receipt for a payment collected later** (SEC-06: "every sale *or collection*"). Should a Payment Entry print its own Arabic receipt? | Not built; only the sale's receipt. | Owner / Accountant |
| 8 | **Service prices.** COPY-SVC, PRINT-SVC and BINDING-SVC are sold at their Item Price. LIB-10 says one price per printed sheet whatever the printing; is binding one price, or by size? The development site's prices (1.00) are placeholders. | The Item Price as set by the owner; nothing priced in code. | Owner |
| 9 | **Cancelling other financial documents with a reason.** ACC-06 names sales; should Payment Entry, Journal Entry and the app's documents also require a reason on cancel? | Only Sales Invoice requires one. | Owner / Accountant |
| 10 | **Requirement IDs.** In requirements v1.2, SEC-06 is "a receipt for every sale or collection"; cancelling with a reason is ACC-06. The task named the cancellation SEC-06. | Code and README cite ACC-06 for the reason and SEC-06 for the receipt. | Team |
| 11 | **POS change account** (fixed, to confirm). The library POS Profiles had no change account, so change was left as a credit on the customer and the whole amount handed over showed in the cash box. Each profile now gives change from its own cash box. | Applied by `setup_library.py`. | Accountant |
| 12 | **Libraries' existing sales system.** Requirements §4.6 say the libraries keep their current sales system as the sales interface, with its data received through integrations (LIB-11), while LIB-01 asks for a POS screen here. Will the counter use ERPNext's POS, or only receive sales from the old system? | Both are possible; the POS is ready. | Owner |
