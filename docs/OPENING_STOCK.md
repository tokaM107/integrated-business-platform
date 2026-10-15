# Opening stock

The opening balance is ERPNext's own **Stock Reconciliation** with Purpose *Opening Stock* (Count Type *Opening*),
posted against the temporary opening account `أرصدة افتتاحية مؤقتة`, one per branch (`imederp/stock_count.py`).
No other document or store is used. The quantities are the libraries' physical count and the costs are the
approved ones: nothing is invented, and the system makes **drafts only**, for the owner or the accountant to
review and submit.

## Stores (checked on the development site, 15 Oct 2026)

| Known context | In the system | Note |
|---|---|---|
| Central store in Mawasah | `المخزن المركزي بالمواساة` (group): `خامات المواساة` (raw materials), `إصدارات الأطباء — المواساة` (doctors' editions) | Both marked *Supplies Branches*. |
| It supplies Azarita | `مخزن الأزاريطة` (group): `خامات الأزاريطة`, `إصدارات الأطباء — الأزاريطة` | Supplied through branch requests (Material Request). |
| Office supplies (ink...) | `مخزن سنتر Imed — أدوات مكتبية` | Outside both branches: its opening is a reconciliation of its own. |
| Damaged stock in Mawasah | `التالف — المواساة` | Marked *Damaged Store*: counted at **zero value**. |

ERPNext's default stores (`المخزن العام`, `تحت التشغيل`, `إنتاج تام`, `بضاعة في الطريق`) are not used; no opening
is entered there. No store was created.

## The count sheet: `apps/imed_erp/imed_erp/setup/data/opening_stock_template.csv`

Copy it to `setup/data/opening_stock.csv`, one row per item and store counted. That file holds the company's
quantities and costs, so Git ignores it (`.gitignore`): the repository is public, and only the empty template is
kept in it. Keep the filled sheet with the accountant's records.

| Column | Required | Meaning |
|---|---|---|
| `warehouse` | yes | The store, as in the table above (the ` - MMG` ending may be left out). Not a group. |
| `item_code` | yes | The ERP item. |
| `item_name` | no | As written on the count, to catch a wrong code (a warning if it differs). |
| `count_uom` | yes | The unit counted in: the item's stock unit or one of its conversions (e.g. `كرتونة`, `رزمة` for paper). |
| `counted_qty` | yes | What was counted, in that unit. Not negative; whole for sheets, reams and boxes. |
| `valuation_rate` | yes, except in the damaged store | The approved cost **per counted unit** (per box if counted in boxes). Converted to the stock unit by the item's own conversion factor. |
| `cost_source` | no, recommended | Where the cost comes from (supplier invoice, approved price list). |
| `counted_by`, `count_date`, `notes` | no | Kept with the sheet for the record. |

Then run `setup/check_opening_stock.py` (README) with the count's date. It checks every row and prints the total
per store; once there is no error, `MAKE_DRAFTS = True` makes the drafts.

## What is checked

- The item exists, is a stock item, is not disabled, has no batches or serial numbers.
- The store exists, belongs to the company, and is not a group.
- The unit is one of the item's units; the quantity is a number, not negative, whole where the unit must be.
- A cost is given, above zero, except in the damaged store, which must be zero.
- The same item and store appear once.
- **No opening twice**: a store that already has an opening reconciliation (draft or submitted) is refused.
- **Stock already recorded** in the store on the count date is shown with the difference; the opening count
  replaces it, against the temporary opening account.

## Validation results on the development site (15 Oct 2026)

**No physical count has been received**, so no opening balance was prepared or posted. What the check found on
the site:

| Check | Result |
|---|---|
| Opening reconciliations already made | None. |
| Stock already recorded | Yes, test data: books, memos and paper in `خامات المواساة`, `خامات الأزاريطة` and `إصدارات الأطباء — الأزاريطة`. Must be cleared before go-live, or each row will show a difference that the opening replaces. |
| Stock items | Only `BOOK`, `MEMO` (generic) and `A4-PAPER`. No ink, binding or consumable items yet, and the real book and memo catalogue is not in the system (LIB-06, LIB-11). |
| Paper units | On this site A4 paper's stock unit is still `Nos`, not `ورقة`, and it is valued FIFO, not moving average, because stock moved before `setup_core.py` could change them. The conversions to ream (500) and box (2,500) are right. On the live site, run `setup_core.py` before any paper is received. |
| Valuation method | FIFO for every item (Stock Settings) except paper, which `setup_core.py` sets to moving average. |

## Missing inputs

1. The physical count of every store, signed by who counted.
2. The approved cost of each item counted (who approves it: owner or accountant).
3. The catalogue: every book, memo, ink and binding item, before the count can name them.
4. The go-live date (the opening's posting date).
5. Whether the test stock on the live site is cleared first.
