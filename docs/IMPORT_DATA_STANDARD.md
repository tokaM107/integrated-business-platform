# Daily import: data standard and unique identifiers (INT-02, INT-03, INT-05, INT-06, INT-14)

**Status: proposal for the team to approve.** Built so far: the BA Plus import (part 3, `imederp/app_import.py`) and
the shared run log (*Integration Import Log*); the booking import's logic (part 4). Not built: the libraries' sales
and stock (parts 1 and 2). The existing systems have not yet said how their data is reached or what identifier each record
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
| **Audit** (INT-12, SEC-01) | Imports run as one integration user per system, never as a person, so the history of every record shows where it came from. Each run writes an **Integration Import Log** (INT-07): the system, the file and its SHA-256, when, who ran it, rows read, inserted, other records made on the way, skipped as already imported, changed in the source, failed, and each row to look at with its line in the file and its reason. Only the import writes a log; nobody edits or deletes one. A run the database drops as a whole (a deadlock) keeps nothing and is logged as Failed. |
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

## 3. BA Plus: courses and subscriptions (INT-05, APP-04, APP-13): `import/app_subscriptions.csv`

**Built** (`imederp/app_import.py`, tests `imederp/test_app_import.py`). One row per student subscription. Becomes
a submitted **App Subscription** on an **App Course**, both keyed by their ids in BA Plus.

Run (the file on the server; as the integration user or an accountant; commits at the end):

```bash
docker exec frappe_docker-backend-1 bench --site frontend execute imed_erp.imederp.app_import.import_file \
  --kwargs '{"path": "/home/frappe/frappe-bench/sites/app_2026-10-22.csv"}'
```

| Column | Type | Required | Meaning and checks | Confirmed? |
|---|---|---|---|---|
| `source_system` | text | no | `ba_plus` if present; another value fails the row. | Ours |
| `subscription_id` | text | yes | The subscription's id in BA Plus. With `ba_plus`, unique (`App Subscription.import_key`): the same id again is skipped, or listed if it changed. | **Needs a real export**: is it stable, and unique across courses? |
| `subscription_date` | date `YYYY-MM-DD` | yes | Not after today; inside one ERP term (the course's). | **Needs a real export**: the format |
| `course_id` | text | yes | The course's id in BA Plus (`App Course.import_key`). The first row with a new id makes the course, in the one term the date falls in; two terms over that day, or none, fails the row. | **Needs a real export** |
| `course_name` | text | yes | The name of a new course. A known course whose name changed in BA Plus is listed, not renamed. | **Needs a real export** |
| `doctor_id` | text | yes | The doctor's id in BA Plus. Found on his submitted app agreement (*Doctor Agreement* › BA Plus Doctor ID, written once by the accountant; one agreement per id). Not found: the row fails. A known course under another doctor fails too. | **Needs a real export**, and the ids written on the agreements |
| `student_phone` | text | yes | Matched to the student (a Customer) by phone, one customer per number (CRM-04). | **Needs a real export**: are phones always given? |
| `student_name` | text | yes | Used only for a new student, made in the customer group `طالب`. | **Needs a real export** |

Not in the file: the **platform fee** (the ERP works it out from the course's students and the tiers, APP-02/03; a
`platform_fee` column is ignored), the agreement and the term (from the course), the cost center (always
`تطبيق BA Plus`, whatever the file or the user says).

What happens to a row:

| The subscription id | Result |
|---|---|
| new | The course and the student are found or made, the subscription is submitted, the course counted again and the change posted to the doctor's account (APP-03/05), as for one entered by hand. Nothing is checked less because it comes from a file: the user needs the rights to make subscriptions and courses. |
| known, the same | Skipped. Nothing posted again: no subscription, ledger entry, journal entry or fee twice. |
| known, changed (course, student phone, date), or cancelled here and still in BA Plus | Listed as *Changed in Source*, **not overwritten** (INT-01). The accountant decides, e.g. cancels it here and lets the next file bring it again. |
| anything wrong | The row fails with its line and reason; nothing of it is kept (a course made for it goes back too); the others go on. |

An imported course or subscription is changed only in BA Plus: saving it here is refused, except a course's
status (open or closed to new students), which is the ERP's own. An imported student who withdraws is ticked in
BA Plus, not here.

**Not decided, so not built** (do not guess them): how BA Plus shows a **cancelled** subscription or a **withdrawn**
student in the file (INT question 6, and whether a withdrawn student counts, `COUNT_WITHDRAWN`); whether its ids
are stable; whether it can send only the day's rows or the whole term each time (both work: known rows are
skipped); the totals check against BA Plus's own count (INT-13, APP-09).

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
