# Library (Tanmya Market) → IMED ERP: SQL Server integration analysis

> 26 Oct 2026. Sources: `Db2BDoctorNew_GenerateScriptReport_20261026_024842.html` (the SQL Server "Generate
> Scripts" report, object names only), `AppTanmyaMarket_123915.exe` and `AppTanmyaMarket1_124429.exe` (two
> .NET builds of 21–22 Sep 2022, inspected statically with `strings` and a UTF-16 string scan, never run),
> `AppTanmyaMarket_124222.rar` (RAR5 holding a 2021 build; p7zip 17.05 on this Mac cannot extract RAR5, so it
> was not read; the two 2022 builds are newer anyway). The library's database was **not** reachable.
>
> **Confirmed** = read from these files. **Assumed** = a reading of the names that the next on-site session must
> verify. Nothing below was taken from a running database.

## 1. What the files say (confirmed)

- **The application.** VB.NET WinForms ("AppTanmyaMarketV1", copyright 2013, assembly 1.0.0.0), Crystal Reports,
  Excel interop, `System.Data.SqlClient` and an Entity Framework reference. Every data access goes through
  **stored procedures**: the string heap holds 1,599 distinct procedure names and only 9 inline SQL
  statements (a test `UPDATE TblTest`, `Select * From TblAccNumberTreeInfo`, four WMI `Win32_*` queries for the
  machine fingerprint, three UI strings). Connection strings are built at run time from parts (`Server=`,
  `;Database=DbAlexMarket;User Id=`, `Data Source=…;Initial Catalog=…`, `,1433;Network Library=DBMSSOCN`): the
  database name is a setting, and the one you connected to is `Db2BDoctorNew` (your confirmation, not the exe).
  The two 2022 builds differ only in one form name and garbage; same data layer.
- **The database** (the Generate-Scripts report): 83 tables, 12 views, 53 scalar functions, 1,588 procedures,
  4 other objects, all in `dbo`. The report lists names only: **no columns, no types, no keys, no row counts.**
- **Naming convention** (consistent across the 1,740 objects and the exe): `Tbl…` tables, `Viw…` views, `Fun…`
  functions, `SPr<Form><Action>` procedures where `<Form>` is the WinForms form: `FSSS` sales small stock
  (retail), `FSBS` sales big stock (wholesale), `FRSSS`/`FRSBS` their returns, `FPS` purchase, `FRPS` purchase
  return, `FOBS` opening balance, `FAPS`/`FANS` stock adjustment plus/minus, `FTS` store transfer, `FOP` price
  offer, `FCashR`/`FCashP` cash receipt/payment, `FJournalE` journal entry, `FCusI`/`FVenI`/`FPI`/`FCDI`/`FSI`/
  `FBI`/`FUI`/`FDI` the master files (customer, vendor, product, cash desk, store, branch, user, doctor),
  `FR…` reports. Procedure parameters are `@P` + the UI control name + the form suffix
  (`@PTxtRegDateRefStockFSSS`); result columns the app reads are the control names without prefix
  (`TxtNumberRefStock`). The Arabic captions confirm the forms: فاتورة مبيعات التجزئة, فاتورة مبيعات الجملة,
  مرتجع التجزئة/الجملة, فاتورة المشتريات, مردودات المشتريات, إيصال إستلام نقدية, إذن صرف نقدية, قيد اليومية,
  تحويل بين مخازن, تسوية كميات بالإضافة/بالخصم, الفواتير المعلقة (held invoices), إصدار (issue, F10),
  إلغاء (cancel, ctrl+C), تعليق (hold, ctrl+H).

## 2. The data model (confirmed names, assumed roles)

| Table | Role (assumed from names and the forms that use it) | Evidence |
|---|---|---|
| `TblRefStockHead` / `TblRefStockSub` | **One document table for every stock movement**: retail sale, wholesale sale, both returns, purchase, purchase return, opening balance, adjustments, transfers, price offers. The head carries the document kind and state in `TxtOperationCodeRefStock` and `TxtStatusCodeRefStock`. | Every FSSS/FSBS/FRSSS/FRSBS/FPS/FRPS/FOBS/FAPS/FANS/FTS/FOP procedure passes `@PTxtOperationCode…`, `@PTxtStatusCodeRefStock…`, `@PTxtRegDateRefStock…`, `@PTxtNumberRefStock…`; `SPrF…TxtIdRefStockMaxGet`, `SPrF…TxtNumberRefStockMaxGet` per form. |
| `TblRefCashReceiptHead` / `Sub` | Cash receipts (إيصال إستلام نقدية): head with branch, cash desk, date, number, status; lines with account codes (levels 5/6/7), debit, credit, remarks. | `SPrFCashRInsert @PTxtRegDateRefCashReceiptFCashR @PTxtBranchCode… @PTxtCashDeskCode…`; `SPrFCashRAAddToDGVCashReceiptSub @PTxtAccNumberLevel7Code… @PTxtDebitValue… @PTxtCreditValue…`. |
| `TblRefCashPaymentHead` / `Sub` | Cash payments (إذن صرف نقدية), same shape. | `SPrFCashP…` family. |
| `TblRefJournalEntryHead` / `Sub` | Journal entries. | `SPrFJournalE…` family. |
| `TblLedgerMovement` | The general ledger: every issued document posts debit/credit rows here (`SPrFSSSIOAddToLedgerMovementCashDr`, `…CusCr`, `…VisaDr`, `SPrFCashRAddToLedgerMovement`, `SPrFSSSGDeleteLedgerMovement` on cancel). | procedure names |
| `TblAccNumberLevel5…9Info`, `TblAccNumberTreeInfo` | A 5-level chart of accounts; customers, vendors, cash desks, employees, banks each get an account at levels 5/6 (`SPrFCusIInsertTblAccNumberLevel5Info`). | procedure names |
| `TblCustomerInfo` | Customers: code, name, phone (3 phones), address, area, title, credit limit/period, begin balance/date, stop flag. | `TxtCustomer…` vocabulary, `SPrTxtCustomerPhoneAlreadyExist`, `SPCustomerInfoByPhone`. |
| `TblDoctorInfo` | **Doctors** (the lecturers whose books the library sells): code, name, balance; functions `FunTxtDoctorSalesValue`, `FunTxtDoctorReturnSalesValue`, `FunTxtDoctorCurrentBalance`; `SPrFSSSIOAddToLedgerMovementDoctor` posts the doctor's share on a retail sale. | functions and procedure names |
| `TblProductInfo` (+ Category/Group/Section/Origin/Unit/Managment/PriceList, `TblBarCode`) | Products with up to 9 barcodes, two units (small/big, `TxtProductUnit2Factor`), cost average, last purchase/sales price, "is stored" flag, per-product doctor (`TxtProductVendorCode`/doctor link assumed). | `TxtProduct…` vocabulary |
| `TblVendorInfo` | Suppliers. | |
| `TblCashDeskInfo`, `TblStoreInfo`, `TblBranchInfo`, `TblUserInfo` (+ `TblUser*Info` rights) | Cash desks, stores (warehouses), branches (with IP and DB name: a multi-branch replication design), users. | |
| `TblOperationInfo`, `TblOperationTypeInfo`, `TblStatusRefInfo`, `TblPaymentTypeInfo`, `TblSalesTypeInfo`, `TblRowStatusInfo`, `TblAdjustmentReson*` | **Lookup tables for the codes** the documents carry. Their rows are the key to classify documents and are **unknown** until read. | |
| `TblGSupportInfo` | "G-Support" extras on a sale (trader bonus, electronic fees, other, profit): a government-support sale mode. | `@PTxtGSupport…FSSS` |
| `TblCurrentDate`, `TblAppSetupInfo`, `TblReplicationBasicData`, `TblSendMailLog`, `TblUserLogs` | Business date, settings, replication, logs. | |

Views: `ViwIncomeSheet` (an income statement) and ten `Viw<Form>GetTxtProductQtyBalanceRefStockSub` (stock
balance per form). Functions: running/current/begin balances for customers, vendors, doctors, cash desks, banks,
accounts and products; sales/return values per customer, doctor and vendor; `funledgerbalance`.

### Document kind and state (assumed, to verify)

- `TxtOperationCodeRefStock` distinguishes the kinds in `TblRefStockHead`; the codes and their Arabic names live
  in `TblOperationInfo` (`TxtOperationCode`, `TxtOperationName`, `TxtOperationNameEng`) grouped by
  `TblOperationTypeInfo`. The exe does not hold the numeric values.
- `TxtStatusCodeRefStock` is the document state; names in `TblStatusRefInfo` (`TxtStatusRefCode`,
  `TxtStatusRefName`). From the UI there are at least **held** (معلق), **issued** (مصدر/إصدار) and
  **cancelled** (ملغي). Only *issued* documents post to the ledger (`SPrFSSSBtnIssueUpdate`,
  `SPrFSSSIOAddToLedgerMovement…`); a cancel deletes the ledger rows (`SPrFSSSGDeleteLedgerMovement`,
  `SPrFSSSILedgerMovementVenCancel`). **An ERP import must take issued documents only and must watch for a later
  cancel.**
- `TxtPaymentTypeCodeRefStock` (cash / credit / visa / other: the sales reports split
  `…CashCasher`, `…CreditCasher`, `…VisaCasher`, `…OtherCasher`) and `TxtSalesTypeCode` (retail / wholesale /
  G-support, assumed) are codes in their lookup tables.
- Line amounts: `TxtProductQtyOutRefStockSub` (sold / issued qty), `TxtProductQtyInRefStockSub` (bought /
  returned), `TxtProductSalesPriceSmallQtyRefStockSub` and `…BigQty…` (price per small/big unit),
  `…BDiscount` variants (before discount), `TxtDiscountPercentToRefStockSub`/`TxtDiscountValueToRefStockSub`,
  `TxtProductTotalValueDownRefStockSub` (line value out, sales) / `TxtProductTotalValueUpRefStockSub` (line value
  in, purchases), `TxtProductVatValueRefStockSub`, `TxtProductCostPriceRefStockSub`, `TxtProductCostAvgRefStockSub`.
  Head amounts: `TxtCashValueRefStock`, `TxtCreditValueRefStock`, `TxtVisaValueRefStock`, a head discount
  (`TxtDiscountPercent`/`TxtDiscountValue`), `TxtVatValue`. Whether the head stores totals or the procedures sum
  the lines (`…RefStockSubSum` names suggest the latter) is unknown.
- Dates: `TxtRegDateRefStock` is the document date; the app also keeps a business date (`TblCurrentDate`,
  `FunTxtCurrentDate`). Which one a day's sales are reported by must be checked.

**What is deliberately not assumed:** that `TblRefStockHead` is the only place sales live (a "hold" could be kept
elsewhere; the G-support mode could write `TblGSupportInfo` rows), the numeric operation and status codes, the
physical column names (the app reads `TxtNumberRefStock` from a result set; the column may be named the same or
aliased in the procedure), key and type information, and whether the doctor's share is stored per line or
derived at report time.

## 3. Target: what the ERP will take from it

The library's SQL Server stays the source of truth for its sales, returns, purchases, stock movements and cash
receipts, as XStudio does for the studio. The ERP **mirrors** issued documents read-only, posts nothing (no
invoice, payment, journal or stock entry; the owner's rule), shows them to the owner and reconciles them against
what the ERP already knows (the day's counters, the cash handover, the doctors' shares).

| Library document | ERP target | Notes |
|---|---|---|
| Retail / wholesale sale, their returns | `Library Sales Document` (new, read-only mirror) with lines | kind, number, date, branch → cost center (`مكتبة الأزاريطة` / `مكتبة المواساة` by branch code, to be mapped), store, cash desk, customer, payment type, totals, lines with product, qty, price, discount, VAT; the doctor per product when the lookup confirms it |
| Purchase, purchase return | same doctype, kind Purchase / Purchase Return | vendor instead of customer |
| Opening balance, adjustments, transfers | same doctype, their kinds | stock only, no money |
| Cash receipt / cash payment | same doctype, kind Cash Receipt / Cash Payment, lines = account rows | shown for the cash-desk reconciliation; never posted |
| Journal entries, ledger movement | **not imported** (the library's own accounting) | listed as a limitation |
| Customers, doctors, products | not created in the ERP for now; names and codes kept on the document | a later step can link doctors to Doctor Agreements by name once the owner confirms the list |

## 4. Architecture (read-only, push from a Windows connector)

The library PC runs SQL Server with Windows authentication and is not reachable from the ERP host. So the
connector runs **on the library PC** and pushes to the ERP:

```
library PC (Windows)                                        ERP (Docker, Mac today / server later)
┌────────────────────────────────┐   HTTPS, token auth     ┌──────────────────────────────────────┐
│ scripts/library_connector/     │ ───────────────────────▶│ imed_erp.imederp.library_sync.sync   │
│ tanmya_connector.py            │   POST batches of        │  .receive(batch)                     │
│  - pyodbc, Trusted_Connection  │   documents (JSON)       │  - ImportRun → Integration Import Log│
│  - SELECT only, READ COMMITTED │                          │  - upsert Library Sales Document     │
│  - incremental: id > last id,  │ ◀─────────────────────── │    by import_key (source id), hash   │
│    plus re-read of the last N  │   {ok, last_id, counts}  │  - Needs Review / Note rows          │
│    days for status changes     │                          │  - owner dashboard card              │
│  - Windows Task Scheduler      │                          └──────────────────────────────────────┘
└────────────────────────────────┘
```

- **Read-only on the library side.** The connector opens the connection with `ApplicationIntent=ReadOnly` where
  the driver allows it and runs only `SELECT` statements listed in its config; it never calls the app's
  procedures (many of them write: `…AddToLedgerMovement`, `…Update`). A SQL login with `db_datareader` only is
  the right account for production; Windows authentication of the logged-in user is acceptable for the first
  runs.
- **Incremental and idempotent.** Watermark on `TxtIdRefStock` (identity, assumed) per document family, plus a
  re-read of the last *N* days (default 7) so a document that was held and later issued, or issued and later
  cancelled, is updated. The ERP keys on `source_system:external_id` (`import_key`, unique) and skips a document
  whose payload hash is unchanged; a changed one is **updated** (the library is the source of truth) and the
  change is listed on the log as *Changed in Source*. A cancelled document stays, marked cancelled, never deleted.
- **Transport.** Frappe token auth (`Authorization: token <api_key>:<api_secret>` of a dedicated ERP user with
  the role the endpoint checks); the ERP must be reachable over HTTPS from the library (today it is on the Mac:
  the connector can only run while the Mac is on and reachable, exactly as for XStudio; the production server
  removes that).
- **Logging.** One `Integration Import Log` per batch, source `tanmya`, with the counters the other sources use;
  the Integration Status report and the owner dashboard card follow from that.
- **Failure.** A batch the ERP refuses is retried on the next run; the connector keeps its watermark only after
  the ERP acknowledged the batch. Network down: nothing is lost, the next run catches up.

## 5. Mapping specification

The connector sends each document as one JSON object whose keys are **the names the app itself reads from the
procedures' result sets** (section 2). The SELECTs that produce them are written on site, after the metadata is
collected, in `config.json` (`queries.*`): the physical column names are aliased to the contract names there, so
nothing in the ERP depends on a column name that was not verified. The contract and the mapping live in
`apps/imed_erp/imed_erp/imederp/library_sync/contract.py` and `mappers.py`; `test_library_sync.py` exercises
them on mock rows.

| Contract key (document) | Required | ERP field | Rule |
|---|---|---|---|
| `TxtIdRefStock` | yes | `external_id`, `import_key = tanmya:stock:<id>` | identity of the head row |
| `TxtOperationCodeRefStock` + `TxtOperationNameRefStock` | yes | `operation_code/name`, `document_kind` | kind from the operation-code map in the config (filled from `TblOperationInfo` on site); unknown code → kind *Other* and a Needs Review row |
| `TxtStatusCodeRefStock` + `TxtStatusNameRefStock` | yes | `status_code/name`, `is_final` | final when the code is in the config's `issued_status_codes`; held/cancelled imported with `is_final = 0`; a cancel after issue → updated, listed |
| `TxtNumberRefStock`, `TxtRegDateRefStock` | yes | `number`, `reg_date` | date as sent (SQL Server datetime, library local time; Cairo) |
| `TxtBranchCodeRefStock`/`Name` | yes | `branch_code/name`, `cost_center` | branch code → cost center map in the config |
| `TxtStoreCodeFromRefStock`/`Name`, `TxtStoreCodeToRefStock`/`Name` | no | `store_code/name`, `store_to_*` | |
| `TxtCashDeskCodeRefStock`/`Name` | no | `cash_desk_code/name` | |
| `TxtCustomerCodeRefStock`/`Name`, `TxtCustomerPhone` | no | `customer_*` | phone when the SELECT joins `TblCustomerInfo` |
| `TxtVendorCodeRefStock`/`Name` | no | `vendor_*` | |
| `TxtSalesmanCodeRefStock`/`Name`, `TxtUserCodeRefStock`/`Name` | no | `salesman_name`, `user_name` | |
| `TxtPaymentTypeCodeRefStock`/`TxtPaymentTypeName`, `TxtSalesTypeCode`/`TxtSalesTypeName` | no | `payment_type_*`, `sales_type_*` | names from the lookup join |
| `TxtCashValueRefStock`, `TxtCreditValueRefStock`, `TxtVisaValueRefStock` | no | `cash_value`, `credit_value`, `visa_value` | |
| `TxtDiscountPercent`, `TxtDiscountValue`, `TxtVatValue` | no | `discount_percent`, `discount_value`, `vat_value` | head-level |
| `TxtRemarksRefStock` | no | `remarks` | |
| `lines[]` | yes for stock kinds | child rows | see below; `total` = Σ line totals (down for sales/returns-out, up for purchases) unless the head carries a verified total |

| Contract key (line) | ERP field |
|---|---|
| `TxtIdRefStockSub` | `external_id` |
| `TxtProductCodeRefStockSub`, `TxtProductNameRefStockSub`, `TxtProductBarCode` | `product_code`, `product_name`, `barcode` |
| `TxtStoreCodeRefStockSub` | `store_code` |
| `TxtProductQtyOutRefStockSub`, `TxtProductQtyInRefStockSub`, `TxtProductQtyReturnRefStockSub` | `qty_out`, `qty_in`, `qty_return` |
| `ChkIsSmallUnit`, `TxtProductUnitCode`, `TxtProductUnit2Factor` | `is_small_unit`, `unit_code`, `unit_factor` |
| `TxtProductSalesPriceSmallQtyRefStockSub`, `…BigQty…`, `…BDiscount` | `price`, `price_before_discount` (small or big by the unit flag) |
| `TxtDiscountPercentToRefStockSub`, `TxtDiscountValueToRefStockSub` | `discount_percent`, `discount_value` |
| `TxtProductTotalValueDownRefStockSub` / `…UpRefStockSub`, `TxtProductVatValueRefStockSub` | `line_total`, `vat_value` |
| `TxtProductCostPriceRefStockSub`, `TxtProductCostAvgRefStockSub` | `cost_price`, `cost_avg` |
| `TxtDoctorCode`, `TxtDoctorName` | `doctor_code`, `doctor_name` (when the SELECT joins the product's doctor) |

Cash receipts / payments use the same shape with the `RefCashReceipt` / `RefCashPayment` names and account rows
(`TxtAccNumberLevel5/6/7Code…`, `…Name…`, `TxtDebitValue…`, `TxtCreditValue…`, `TxtRemarks…`).

## 6. What must be collected on the next authorized connection (read-only)

Run `scripts/library_connector/collect_metadata.ps1` (it calls `sqlcmd -E`, Windows authentication, and writes
text files into a folder you bring back; nothing is changed). It collects:

1. `INFORMATION_SCHEMA.COLUMNS` for every table (name, type, nullability, identity, default) and the primary and
   foreign keys (`sys.key_constraints`, `sys.foreign_keys`).
2. The full text (`sp_helptext`) of the procedures that define the documents' life: `SPrFSSSInsert`,
   `SPrFSSSUpdate`, `SPrFSSSBtnIssueUpdate`, `SPrFSSSBtnDeleteHead`, `SPrFSSSICAddToLedgerMovement*`,
   `SPrFSSSIOAddToLedgerMovementDoctor`, `SPrFSSSFillDGVSalesSmallStockSub`, `SPrFSSSSFillDGVSalesSmallStockSearch*`,
   the same four for `FSBS`, `FRSSS`, `FRSBS`, `FPS`, `FCashR`, `FCashP`, and the reports `SPrRptSalesSmallStockCashCasher`,
   `SPrFRDSSumAllSales`, `SPrFRDocMov`, `SPrFRCDMov`, `SPrRptSalesSmallStockHold`, plus the views and the
   `FunTxt*` functions: they show the real column names, the status/operation codes they filter on, and how the
   doctor's share is computed.
3. Every row of the lookup tables: `TblOperationInfo`, `TblOperationTypeInfo`, `TblStatusRefInfo`,
   `TblPaymentTypeInfo`, `TblSalesTypeInfo`, `TblRowStatusInfo`, `TblAdjustmentResonInfo`, `TblBranchInfo`,
   `TblStoreInfo`, `TblCashDeskInfo`, `TblUserInfo` (code and name only), `TblAppSetupInfo`, `TblCurrentDate`.
4. Row counts and date ranges of `TblRefStockHead`, `TblRefStockSub`, `TblRefCashReceiptHead`,
   `TblRefCashPaymentHead`, `TblLedgerMovement`, `TblCustomerInfo`, `TblDoctorInfo`, `TblProductInfo`; counts per
   operation code and status code; max ids (the watermarks).
5. The top 20 rows of `TblRefStockHead` and their `TblRefStockSub` lines, of the last 30 days, with names masked
   (the script masks customer names and phones): to validate the contract against real shapes.
6. The SQL Server version, the database collation, whether `TblRefStockHead.TxtIdRefStock` is an identity, and
   whether a `rowversion`/`ModifiedDate` column exists anywhere (it would make change detection exact).

With that folder, the remaining steps are done remotely: fill `config.json` (queries, code maps), run the
connector in `--dry-run` against the saved samples, then the first real batch.

## 7. What is done remotely now, what waits for the library PC

Done now (this branch): this analysis; the contract, mappers and the receiving endpoint with the Import Log and
idempotency reused from the XStudio and BA Plus imports; the `Library Sales Document` mirror doctype; mock-based
tests; the Windows connector with a dry-run mode; the metadata-collection scripts. Not possible until one more
on-site session: confirming the physical columns, keys and codes (section 6), writing the final SELECTs, the
first dry run on real data, and the choice of the ERP user and host the connector will push to.

Limitations to keep visible: the library's own accounting (journal entries, ledger, chart of accounts) is not
imported; a document deleted on the library side (`SPrFSSSBtnDeleteHead`) stops being returned and is listed as
"not returned", never removed here; the doctor's share is only as the library computes it; a hold/issue/cancel
after the re-read window (7 days) is not seen until the next full re-read.
