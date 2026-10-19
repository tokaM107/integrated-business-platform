# Daily import: data standard and unique identifiers (INT-02, INT-03, INT-05, INT-06, INT-14)

**Status: proposal for the team to approve.** Nothing here is built yet: no import job, and no source-ID fields
on the documents. The existing systems have not yet said how their data is reached or what identifier each record
carries (requirements v1.2, open questions 27, 28 and INT question 2). This document fixes the shape of the daily
files and the rules for identifiers, so the import can be built once those answers come, and so a file sent twice
never records anything twice.

Sample files, one per record type, are in [`docs/import/`](import/). Their single row is marked `EXAMPLE`; it
shows the format only and is not real data.

## Rules for every record type

| Rule | What it means |
|---|---|
| **Source of truth** (INT-01) | A record imported from a system is changed only in that system. The ERP never edits it. |
| **Unique identifier** (INT-06) | Every record carries the identifier the source system gave it (`source_id`), and every line its own (`source_line_id`). Together with the name of the system (`source_system`), it is unique: the same record sent again is recognised. |
| **Never a made-up identifier** | The key is never a random value or a row number in the file, which change every time the file is made. If a system has no identifier, the key is built from fields that never change for that record (e.g. `branch + receipt number + receipt date`), and that rule is written here before the first import. |
| **Insert, never overwrite** | A new key is inserted. A key already imported and unchanged is skipped. A key already imported but changed in the source is **not** edited (a posted invoice cannot be, ACC-07): it is listed for the accountant, who cancels and re-enters it. |
| **Cancelled in the source** | Listed for the accountant, who cancels it in the ERP with the reason "cancelled in the source system" (ACC-06). How each system shows a cancellation (deleted or a status) is still to be answered (INT question 6). |
| **Missing or invalid field** | The record is not imported. It goes to the error list with the field and the reason; the rest of the file goes on (INT-07). Nothing is guessed or filled in. |
| **Source marked** (INT-14) | Every imported record keeps `source_system`, so screens and reports can tell imported records from ones entered by hand. |
| **Audit** (INT-12, SEC-01) | Imports run as one integration user per system, never as a person, so the history of every record shows where it came from. Each run logs: file, time, records read, inserted, skipped as already imported, failed. |
| **Re-running** | Running the same file again inserts nothing (every key is already there) and logs the run as all skipped. |

**Proposed fields** (to add when the import is built, after approval; no existing record changes): `source_system`
(Select) and `source_id` (Data) on Sales Invoice, Stock Entry and App Subscription, unique together;
`source_line_id` (Data) on Sales Invoice Item and Stock Entry Detail. The doctor's accrual already keys each
sale line by its invoice line (Doctor Ledger Entry `invoice_item`, `imederp/doctor_accrual.py`), so an imported
sale line is counted for the doctor once, also by the daily safety-net job.

## 1. Library sales (INT-02, LIB-11): `import/library_sales.csv`

One row per receipt line. Becomes a submitted **Sales Invoice** (one per receipt), the same document the ERP's
own point of sale makes, so the revenue account, cash box, paper use, edition and doctor's amount follow.

| Column | Type | Required | Meaning and checks |
|---|---|---|---|
| `source_system` | text | yes | `library_pos` (name to confirm) |
| `source_id` | text | yes | The receipt's identifier in the library system. Unique per system. |
| `source_line_id` | text | yes | The line's identifier on the receipt (or the receipt id + line number, if lines have none). |
| `branch` | text | yes | `مكتبة المواساة` or `مكتبة الأزاريطة`: the cost center and the POS Profile (store, cash box). |
| `receipt_date` | date `YYYY-MM-DD` | yes | Posting date. Not in a closed month (refused, listed). |
| `receipt_time` | time `HH:MM:SS` | no | Posting time. |
| `item_code` | text | yes | The ERP item (the library system's code mapped once to it; mapping table to agree). Must exist. |
| `book_edition` | text | when the item has more than one edition on sale | The edition the copies come from (`imederp/edition_sales.py`). |
| `qty` | number > 0 | yes | In the item's stock unit (copies, sheets). |
| `rate` | number ≥ 0 | yes | The price charged per unit, as charged. Not taken from the ERP's price list. |
| `customer_phone` | text | no | Matched to the customer by phone (CRM-04, one spelling `+20…`). Blank or not found: the walk-in customer to agree. Never creates a duplicate. |
| `payment_method` | text | yes | `cash`, `instapay` or `vodafone_cash`: mapped to the branch's payment method. |
| `paid_amount` | number ≥ 0 | yes | Paid on this receipt (on its first line; 0 on the others). |
| `cashier` | text | no | Who sold, as the source names them. |

**Totals check** (INT-13): each run compares the number of receipts and their total with the source system's own
daily total and shows the difference.

## 2. Stock movements (INT-03, LIB-02, LIB-08): `import/stock_movements.csv`

One row per line moved. Becomes a submitted **Stock Entry** (one per movement): Material Transfer between stores,
Material Receipt, or Material Issue.

| Column | Type | Required | Meaning and checks |
|---|---|---|---|
| `source_system`, `source_id`, `source_line_id` | text | yes | As above, for the movement and its line. |
| `movement_date` | date | yes | Posting date. Not in a closed month. |
| `movement_type` | text | yes | `transfer`, `receipt` or `issue`. Damaged stock is not imported this way: it goes through Damaged Stock Entry (LIB-09). |
| `from_store` | text | for transfer and issue | An ERP store (not a group, not the damaged store). |
| `to_store` | text | for transfer and receipt | An ERP store (not a group, not the damaged store). |
| `item_code` | text | yes | Must exist and be a stock item. |
| `uom` | text | yes | The item's stock unit or one of its conversions (box, ream). |
| `qty` | number > 0 | yes | Whole for units that must be whole. |
| `rate` | number ≥ 0 | for receipt | Cost per unit received. |
| `received_by` | text | for transfer | Who received at the branch (LIB-08). |

A transfer that takes a store below zero is refused by ERPNext (negative stock is off) and listed.

## 3. App subscriptions (INT-05, APP-04, APP-13): `import/app_subscriptions.csv`

One row per student subscription. Becomes a submitted **App Subscription**.

| Column | Type | Required | Meaning and checks |
|---|---|---|---|
| `source_system`, `source_id` | text | yes | `ba_plus` and the subscription's id in the app. |
| `subscription_date` | date | yes | |
| `doctor_agreement` | text | yes | The doctor's App agreement in the ERP (mapped once from the app's course or doctor id). Used to find or make the *App Course*; the subscription takes its agreement, doctor and term from the course. |
| `course` | text | yes | The course name in the app. Matched to an *App Course* of the agreement in the subscription's term, made first if missing. |
| `student_phone` | text | yes | Matched to the student (a Customer) by phone, as in sales. |
| `student_name` | text | yes | Used only when the student is new. |
| ~~`platform_fee`~~ | | no | Not imported: the ERP works it out from the course's number of students and the tiers in force when its term starts (APP-02/03). A value in the file is ignored. |

## 4. Studio bookings (INT-04): the import is written, the file is not

Bookings are *Booking* documents, and `imederp/booking_import.py` (`import_bookings`) takes rows into them: a
booking's key is its source system and its id there, the customer is found by phone, a changed booking is listed
and not overwritten, and a row with an error fails alone with its reason (README, Bookings). What is still open:
the booking system's access (STU-11), the file's columns, and what runs the import every day (a scheduled job or
an upload screen) and keeps the failed rows for someone to see (INT-07).

## Master data: items and customers

Imported once at go-live (INT-08), before the daily files:

- **Items**: the library system's product code becomes the ERP item code, or is kept in a mapping table; ISBN in
  the item's barcodes (LIB-06). The catalogue is not known yet (setup_library.py keeps one generic BOOK and MEMO).
- **Customers**: by phone, one customer per number (CRM-04). Existing duplicates are listed by
  `setup/setup_customer_phones.py`, never merged automatically.

## Questions to answer before building the import

1. How is each system reached: API, a daily file, or reading its database (question 27, 28)?
2. Does each system give every record and line a stable identifier and a last-changed time (INT question 2)?
3. How does each system show a cancellation: deleted, or a status (INT question 6)?
4. The mapping of the library system's product codes and cashiers to the ERP's items and users.
5. Which customer a sale with no phone goes to.
6. How often each import runs (INT-15).
