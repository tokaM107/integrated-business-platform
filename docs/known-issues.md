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
| BA+ app subscriptions and platform fees | APP | Courses, tiers and the fee per course (APP-01/02/03); not posted to the doctor's ledger yet (APP-05) |
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

| # | Question | Until decided | Ask |
|---|---|---|---|
| 1 | **A course of exactly 100 students.** The requirements say 1–100 and "100 to 500". | 100 is in the first tier (250); the second starts at 101. One row of the schedule to change. | Owner |
| 2 | **A student who withdraws** after the term starts. | Still counted: a submitted subscription counts until it is cancelled. | Owner |
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
