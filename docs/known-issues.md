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
| Bookings for the studio and halls | STU, HAL (the studio booking system stays the source of truth; we read from it, INT) | Built: *Booking*, *Booking Resource* (STU-01/02/03/08/14, HAL-01/02/04/07/10), the day and week calendar. The import is written (`booking_import.py`) but nothing runs it yet. Pricing, add-ons, rental models and reports: see the requirements review below |
| Paper counters (printer readings, sheets consumed vs sold) | PRN | Built: *Printing Machine*, *Daily Counter Reading*, *Printer Reading* (machine linked), the *Daily Printing* report |
| Doctor agreements, editions and settlements | DOC | Started: *Doctor Agreement*, *Book Edition*, *Doctor Ledger Entry* |
| BA+ app subscriptions and platform fees | APP | Courses, tiers and the fee per course (APP-01/02/03); not posted to the doctor's ledger yet (APP-05) |
| Integrations with the library system, studio booking system and BA+ app | INT | Not started (open questions ★ 10, 27, 28) |
| Mobile application | — | Not started |
| AI assistant (owner only, read only) | AI | Chat window, voice and permissions done; model not connected yet (`imed_erp/assistant/providers.py`) |
| Unified notifications (WhatsApp / SMS / in-app) | CORE-10 | Skeleton: `imed_erp/notification_service.py` |

## Requirements v1.2 review (19 Oct 2026): gaps not built or not decided

Every requirement of v1.2 was compared with the code. These are the Must and Should items that are missing,
partly built or built differently, and were not recorded before. The rest is built, or recorded in the other
sections of this file. Each row says what it needs before it can be built.

### Money: decide before go-live

| # | Requirement | Gap | Risk | Needs |
|---|---|---|---|---|
| 1 | APP-05, APP-06, ACC-13 (Must) | Platform fees are not posted to the doctor's account, and a *Collection* in the doctor's ledger posts no journal entry: the money collected from a doctor enters no cash box. | Collected fees are missing from the books and the app's treasury. | When the fee is posted (each subscription, or the course's total when the term closes), the revenue account, and the treasury a collection goes into. Owner / accountant. |
| 2 | ACC-03 (Must) | No daily close: nothing compares the cash counted in a box with its balance. | A shortage at a branch is found only at the weekly hand-over, if at all. | How the close is made (ERPNext POS Closing Entry per library, or a daily count per treasury) and who approves it. Accountant. |
| 3 | ACC-05 (Must) | Revenue is recorded when the invoice is submitted (ERPNext's accrual basis), not when it is collected; the rest shows as receivables. | The P&L can show revenue not collected yet. | Keep accrual (usual accounting, receivables report shows what is owed) or follow the text. Accountant. |
| 4 | ACC-04 (Must) | A deposit (عربون) is not posted: the *Booking*'s amount paid stays on the booking, and the account العرابين المقبوضة is not used. | Cash taken as deposits is in no treasury. | With the bookings' posting question below. |
| 5 | ACC-09 (Must) | The weekly hand-over to the owner is an *Inter Business Transfer* to the main treasury; there is no owner or bank account to hand over to, and it mixes with transfers between businesses. | The owner's receipts cannot be listed on their own. | An account for the owner's custody (and a bank account if cash goes to the bank). Owner. |
| 6 | ACC-10 (Should) | Wallets (InstaPay, Vodafone Cash) are not reconciled with their statements. | Wallet differences go unseen. | After go-live. |

### Before go-live

| # | Requirement | Gap | Risk | Needs |
|---|---|---|---|---|
| 7 | SEC-05 (Must) | No daily automatic backup kept off the server. | A failed server loses the data. | Set up with the production server (week C): scheduled `bench backup --with-files` and a copy off the server. |
| 8 | HR-01, HR-02, HR-04, HR-06 (Must); HR-03, HR-05 (Should) | HR is not built and HRMS (Frappe's HR app) is not installed: no payroll, attendance or salary split between businesses. Salaries are recorded as expenses. | The owner may expect payroll from the Must list. | Confirm HR is after go-live, and when HRMS is installed (an install and migrate on a live site). Owner. |
| 9 | LIB-07 (Must) | Supplier purchases (`setup_buying.py`, on branch `feature/buying`) are not merged, though the owner's dashboard refers to it. | Purchases use ERPNext's defaults (no Update Stock default). | Merge and test `feature/buying`. |
| 10 | Owner's dashboard (5.1) | Done on 19 Oct: studio bookings and hours, hall bookings and what is unpaid on bookings are cards on the owner's dashboard, with the bookings list and the transfers report (RPT-03). | | |

### Halls and studio

| # | Requirement | Gap | Needs |
|---|---|---|---|
| 11 | HAL-12 (Must), open question 1 | No rental model on a hall booking (fixed rent or a share of the entry fees) and no share. | The share % (open question 3). Owner. |
| 12 | HAL-08 (Must) | No attendees or entry price on a hall booking. | Nour. |
| 13 | HAL-06 (Must), STU-15 (Should) | No hall report (by day and hall: bookings, attendees, rent, collected, cancelled, unpaid) and no studio occupancy report. | After 11 and 12. |
| 14 | HAL-10, STU-02 (Must) | Done on 19 Oct: the bookings calendar, by day and by week (Bookings > Calendar, `booking_calendar.js`). Frappe's calendar view, with each booking's start and end made from its date and times on the server (`booking.get_events`). | |
| 15 | STU-04 (Must), HAL-11 (Should) | Extras (a microphone, lights at 50 a piece an hour) cannot be listed on a booking; they are in its typed total. | Booking rows for extras with prices. |
| 16 | Permissions matrix, bookings | The accountant may create and edit bookings (matrix: none), and a branch manager edits and cancels without approval (matrix: with approval). | Who approves a branch manager's change or cancellation. Owner. |

### Integrations, reports and the rest

| # | Requirement | Gap | Needs |
|---|---|---|---|
| 17 | INT-04, STU-06 (Must) | The booking import is written but nothing runs it (no job, no upload). | The file and its schedule (INT-02). |
| 18 | INT-07 (Must) | Failed rows are returned, not kept: no log, no alert, no re-import of a period. | An import log doctype with each run's failed rows, and an alert. |
| 19 | INT-09, RPT-12 (Must) | No screen showing each integration's last run and failures. | After 18. |
| 20 | INT-06, INT-14 | Only bookings have a source id and a source; sales, stock and app subscriptions not yet. | With the daily import (IMPORT_DATA_STANDARD.md). |
| 21 | INT-11 (Must) | Store and forward is not addressed. With a daily file, a failed day is imported again from the same file. | Write it down when the import is built. |
| 22 | INT-08 | Only opening stock has an import plan; customers, doctors' balances, past bookings and app history have none. | Open question 25. |
| 23 | APP-09 (Must), open question 5 | The app's student count is not reconciled with an approved billing count; who approves the count (the doctor, before his statement?) is not answered. | Owner. |
| 24 | APP-11 (Must) | The doctor's statement for an app agreement has no courses, students, tier or fees. | With 1. |
| 25 | RPT-01, RPT-02 (Must) | Revenue per business and period, and profit before and after the shared costs, are ERPNext's P&L by cost center; the README does not say how to read them. | A README section, or a report. |
| 26 | PRN-03 (Should) | Waste and losses are in three places (Daily Printing, damaged stock, Stock Count Variance), not one monthly report. | A report. |
| 27 | PRN-04 (Must) | The paper balance is in sheets only, not in boxes and reams. | A column in boxes and reams. |
| 28 | PRN-09 (Must) | A machine's "rate of use" is its share of the library's printing, not the time it ran. | Owner: which one is meant. |
| 29 | PRN-01 (Must) | The day's opening reading is the last closing one; nothing reads the counter at the start of the day. | Owner: is the closing reading enough. |
| 30 | CORE-06 (Must) | One selling price list; old prices and their dates are kept only in the change log. | A price list per business if prices differ. |
| 31 | CORE-07 (Must) | Users can be deleted, not only disabled. | Remove delete on User from System Manager users other than the developers. |
| 32 | CORE-08 (Must) | Customers, doctors, suppliers and employees are separate records, not one party. | Decided by ERPNext's design; written here as a deviation. |
| 33 | EXP-04 (Must) | Shared costs are split by fixed percentages only (60 / 40), not by revenue or area. | The owner chose fixed percentages (README); a new rule changes them. |
| 34 | AI-09 (Should), SEC-09 | The assistant keeps no log of questions; the external systems' keys are in `site_config.json`, not encrypted. | After the model is connected. |
| 35 | CRM-03 (Should) | No call or follow-up log. | After go-live. |
| 36 | TSK, open question 1 | Answered: only the owner assigns tasks. TSK is after go-live; keep this when it is built. | |

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

## Open questions: edition quantities, carry forward and cancellation (DOC-14..17)

| # | Question | Until decided | Ask |
|---|---|---|---|
| 1 | **Which copies sell first: the doctor's or the library's extra ones?** DOC-14 tracks them apart, and DOC-18 charges the doctor for *his* copies left at cancellation, so the order decides what he pays. | Sold Qty and Remaining Qty are for the edition as a whole; they are not split between the two quantities. | Owner |
| 2 | **Two editions of the same book on sale at once** (a new one while the last one's copies are carried forward): which is sold first? | The seller chooses the edition on the invoice row; none is picked for them. The point of sale cannot show the field, so such a sale is made from the desk. | Owner / Libraries |
| 3 | **One Item per edition, or one per title?** Stock is valued per item (FIFO by default; one generic `BOOK` item today), so copies of different editions of one item share one cost: the carried copies' original cost (DOC-15/16) is kept on the edition, not in the stock value. One Item per edition (or batches) would keep it in stock too. | Any item can be named on an edition; nothing in valuation changed. | Owner / Accountant / Taqa |
| 4 | **How printed copies enter the store, and at what cost.** Approving an edition posts nothing; stock of the item comes from receipts or purchases at the rate typed there, not from the edition's approved costs. | Not built; no stock or ledger entry from editions. | Accountant / Taqa |
| 5 | **The edition's selling price and the Item Price.** DOC-16 sells carried copies at the price of the day; the price on the invoice is ERPNext's Item Price, which only the owner changes (SEC-02). Should approving an edition set it? | Not linked; the Item Price is set by the owner as before. | Owner |
| 6 | **The copies of a cancelled edition.** They are no longer sold here. Are they sold by weight as damaged stock, returned to the doctor, or kept? | Still in the store; no stock movement made. | Owner / Libraries |
| 7 | **Who received the notice.** DOC-17 asks for the employee who received the verbal notice. The one recording it is taken as that employee. If someone else may record it for them, which name is kept? | The logged-in employee recording it. | Owner |
| 8 | **Carry forward at period end.** Manual (button) for now. Should every unsold edition be carried forward automatically when its period ends, and to the next period of which cycle? | Manual, to any later open period. | Owner / Accountant |
| 9 | **Damaged copies of an edition** (DOC-19). Damaged Stock Entry does not name an edition, so damaged copies are not taken off the edition's Remaining Qty. | Not linked. | Libraries |

**Depends on the doctors' accounts (Taqa):** what the doctor is due per copy sold (DOC-07) and the cancellation
charge (DOC-18, approved under DOC-22) should read the sales from Sales Invoice Item › Book Edition, the edition's
approved costs, and its Remaining Qty at cancellation; split between the doctor's and the library's copies once
question 1 is answered. Nothing here makes a Doctor Ledger Entry.

## Open questions: doctor reports, daily import and opening stock (RPT-08, RPT-10, INT, opening stock)

| # | Question | Until decided | Ask |
|---|---|---|---|
| 1 | **Platform fees in the doctor's ledger.** App Subscriptions post nothing to the ledger, so an app agreement's balance holds only its collections, and Doctor Debts (RPT-10, read from the ledger) shows a fee as owed only once it is in the ledger. Should each subscription's fee be posted to the ledger as an Accrual? | Fees on subscriptions alone do not show as debts. | Owner / Taqa |
| 2 | **Payouts by library.** RPT-08 asks for receivables by library. A payout made for the agreement as a whole has no library, so the libraries' rows do not each show what is still owed to them. Should a payout name its library? | Shown as *Not by branch*; the agreement's row is the balance. | Accountant / Taqa |
| 3 | **Who sees the reports.** RPT-08 and RPT-10 are Super Admin reports. | The owner and the accountant (Accounts Manager, who may open the doctor's ledger). | Owner |
| 4 | **Each system's identifiers, access and cancellations** (requirements questions 27, 28; INT questions 2, 6). | No import built; the data standard and the proposed source-ID fields wait for the answers (docs/IMPORT_DATA_STANDARD.md). | Libraries / app / studio teams |
| 5 | **Opening stock inputs**: the physical count, the approved cost of each item and who approves it, the full catalogue, the go-live date, and whether the test stock is cleared first. | Template and check ready; no opening made (docs/OPENING_STOCK.md). | Libraries / Accountant / Owner |
| 6 | **Two real doctor statements** to check by hand. | Template ready, empty (docs/DOCTOR_STATEMENT_RECONCILIATION.md). | Accountant |

## Open questions: platform fees (APP-02, APP-03)

The two counting rules are constants at the top of `imederp/doctype/app_course/app_course.py`, each with what it means: `TIER_COUNTED_PER` (`"course"`, answered by the owner on 18 Oct 2026; `"doctor"` counts all the doctor's courses in the term together) and `COUNT_WITHDRAWN`. Open terms are counted again with their next subscription.

| # | Question | Until decided | Ask |
|---|---|---|---|
| 1 | **A course of exactly 100 students.** The requirements say 1–100 and "100 to 500". | 100 is in the first tier (250); the second starts at 101. One row of the schedule to change. | Owner |
| 2 | **A student who withdraws** after the term starts (the *Withdrew* box on the submitted subscription). | Still counted and charged: `COUNT_WITHDRAWN = True` in `app_course.py`, one line to change. | Owner |
| 3 | **From when the tiers are in force.** | 1 Sep 2026, the start of the first term (setup_platform_fees.py). | Owner |

## Open questions: bookings (HAL-01, HAL-02, STU-01, STU-08)

| # | Question | Until decided | Ask |
|---|---|---|---|
| 1 | **Halls and the studio share rooms**: 4 of the 8 halls are also the studio part of the time (allocation rule notes). Does a studio booking in a room block a hall booking of the same room, and the other way round? | Each resource is checked on its own; no sharing between resources. | Owner / Nour / Gilan |
| 2 | **Studio services and the studio's rooms**: can two services (e.g. smart board and podcast) be booked at the same time, or do they use the same room? | Each service is checked on its own. | Gilan |
| 3 | **Halls have no deposit** (HAL question 2), but STU-08's "Confirmed" is "confirmed with a deposit". How is a hall booking confirmed? | The STU-08 statuses apply to halls too, so a hall booking without a deposit stays Tentative until Completed. | Owner / Nour |
| 4 | **The halls' data**: names, capacities, equipment and prices are blank in the requirements (HAL-01). | No resource made; entered by the owner or the accountant. | Nour |
| 5 | **The booking's total**: hours × the item's price, or the agreed amount (packages, per reel, STU-05; price by customer category, HAL-03; rental models, HAL-12)? | Typed on the booking; nothing priced in code. | Owner |
| 6 | **The booking's payment in the accounts** (ACC-01, STU-10): through a Sales Invoice of the service item into the business's cash box, or a Payment Entry? | Total and paid are recorded on the booking only; nothing is posted. | Accountant |
| 7 | **Status changes**: may a Completed, No Show or Cancelled booking be changed back? | Allowed, with the same checks as a new booking (a cancelled one taken back must not overlap); every change is in the history. | Owner |
| 8 | **The booking system's import** (STU-11, STU-09, STU-10): its access, its status names, how changes and cancellations are taken over, and whether a customer not found is created. | Import ready for rows in this system's statuses; changes listed, never overwritten; an unknown customer fails the row. | Studio booking team |
| 9 | **Bookings past midnight.** | Not possible: a booking ends on its own day. | Nour / Gilan |
| 10 | **Same resource, same moment, no overlap**: the second save is asked to save again (the protection against overlaps, see README). | Accepted: it happens only when two people save the same resource within the same second. | — |
